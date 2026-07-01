"""Pucho router agent (LangGraph StateGraph).

Flow:
    START
      → transcribe_if_voice   (calls the Sarvam STT tool when modality=="voice")
      → classify              (OpenAI structured-output picks legal/healthcare/financial)
      → conditional edge      (routes to the matching domain agent)
      → legal | healthcare | financial   (each runs its own RAG + (optional) TTS)
      → persist_message       (writes one row to `messages`, captures message_id)
      → enqueue_review        (auto-writes a `pending` row into qa_reviews)
      → reflect_<domain>      (extracts facts via structured-output → crud.memory.upsert)
      → END

State shape:
    input_question:    the user's question (after STT if the input was voice)
    language:          BCP-47 language code (e.g. "en-IN", "hi-IN")
    modality:          "text" or "voice" — the original inbound modality
    audio_bytes:       raw audio when modality=="voice", otherwise None
    decision:          one of "legal" | "healthcare" | "financial" after classify
    output_text:       the domain agent's text reply
    output_audio_url:  Vercel Blob URL if the reply was voice, else None
    messages:          chat history (HumanMessage/AIMessage) for the reflect node
    last_message_id:   id of the AI message row just persisted by persist_message

Context (passed via `ainvoke(..., context=RouterContext(...))`):
    user_id:           UUID of the `users` row for this WhatsApp sender
    phone_number:      E.164 of the sender (for logging / thread_id derivation)
    inbound_message_id: UUID of the inbound message row (already persisted by adapter)

Compilation:
    `compile_router()` returns the compiled graph with `AsyncPostgresSaver`
    wired in. Called from `api/main.py`'s FastAPI lifespan. Imports of this
    module stay cheap; the DSN-touching side effects happen lazily.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

import crud.message as crud_message
import crud.whatsapp_user as crud_whatsapp_user
from config.db import get_checkpointer
from models.memory import MemoryDomain
from services.memory.reflect import extract_facts_for
from services.tools.speech_to_text import speech_to_text


class Route(BaseModel):
    """Structured-output schema for the router classifier.

    One LLM call does routing AND personalisation profiling, so literacy/tone
    cost no extra round-trip.
    """

    step: Literal["legal", "healthcare", "financial"] = Field(
        description="The domain the user's question should be routed to."
    )
    literacy_level: Literal["low", "medium", "high"] = Field(
        description="How comfortably this person reads/writes, judged from the "
        "message's vocabulary and complexity (plus the modality prior).",
    )
    emotional_tone: Literal[
        "neutral", "worried", "distressed", "frustrated", "hopeful"
    ] = Field(description="The dominant feeling in the user's message.")
    search_query: str = Field(
        description="An ENGLISH, search-optimised rewrite of the user's question, "
        "used only to retrieve documents from the English corpus. Keep the key "
        "entities/terms; this is NOT the reply (the reply stays in the user's "
        "language).",
    )


class State(TypedDict, total=False):
    input_question: str
    language: str
    modality: Literal["text", "voice"]
    audio_bytes: bytes | None
    decision: Literal["legal", "healthcare", "financial"] | None
    literacy_level: Literal["low", "medium", "high"] | None  # set by classify
    emotional_tone: str | None  # set by classify; per-turn, not persisted
    search_query: str | None  # set by classify; English query for retrieval
    onboarding_handled: bool  # set by onboard node when it sent a welcome
    output_text: str | None
    output_audio_url: str | None
    # Short-term memory: append-only chat history kept in the checkpointer across
    # the user's turns (thread_id == wa-<phone>). The add_messages reducer means a
    # node returning {"messages": [...]} APPENDS to the running history instead of
    # replacing it — so each turn's user question and bot reply accumulate, and a
    # domain agent can see the last few turns. Without the reducer the channel is
    # overwritten every turn and only the last message survives.
    messages: Annotated[list, add_messages]
    last_message_id: UUID | None  # set by persist_message, read by reflect + enqueue


@dataclass
class RouterContext:
    """Per-invocation context, supplied via `ainvoke(..., context=RouterContext(...))`.

    Built by the WhatsApp adapter from the inbound Twilio form. Required for
    persist_message, enqueue_review, and reflect nodes (they all read user_id).
    """

    user_id: UUID
    phone_number: str
    inbound_message_id: UUID | None = None
    onboarded: bool = False
    name: str | None = None


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

ROUTER_SYSTEM_PROMPT = """You are the routing + profiling layer of Pucho, a
WhatsApp helpline for low-income urban communities in India. For each user
message, output four things — do NOT answer the question itself:

1. step — the specialist domain: legal, healthcare, or financial. If it spans
   several, pick the most central one.
2. literacy_level — how comfortably this person reads/writes (low | medium |
   high), judged from their vocabulary, sentence complexity, and phrasing.
   {literacy_prior}
3. emotional_tone — the dominant feeling in the message: neutral, worried,
   distressed, frustrated, or hopeful.
4. search_query — an ENGLISH, keyword-rich rewrite of the question for searching
   an English document corpus. Translate from Hindi/Marathi/Hinglish if needed
   and keep the key entities (scheme names, body parts, legal terms). This is
   used ONLY for retrieval; the user's reply still comes back in their own
   language.
"""


def _literacy_prior(state: State) -> str:
    """A hint that biases the literacy judgement before reading the message."""
    prior = state.get("literacy_level")
    if prior:
        return (
            f"This person was previously assessed as '{prior}' literacy — keep "
            "that unless this message clearly indicates otherwise."
        )
    if state.get("modality") == "voice":
        return (
            "This message was SPOKEN (a voice note), which usually means the "
            "person is not comfortable reading/writing — lean towards 'low' "
            "unless the phrasing is clearly sophisticated."
        )
    return "This message was TYPED."


async def transcribe_if_voice(state: State) -> dict[str, Any]:
    """If the inbound modality is voice, run STT and write the text back to state.

    We always auto-detect the language (`language_code="unknown"`) and write the
    detected code into state so the domain agent's TTS reply comes back in the
    same language the caller spoke — no stored language preference.
    """
    if state.get("modality") != "voice":
        return {}

    audio_bytes: bytes | None = state.get("audio_bytes")
    if not audio_bytes:
        return {"input_question": ""}

    result = await speech_to_text.ainvoke(
        {"audio_bytes": audio_bytes, "language_code": "unknown"}
    )
    if isinstance(result, dict):
        transcript = result.get("transcript") or ""
        detected_language = result.get("language_code")
    else:
        # Defensive: older tool shape returned a bare string.
        transcript = str(result)
        detected_language = None

    out: dict[str, Any] = {"input_question": transcript}
    if detected_language:
        out["language"] = detected_language
    return out


async def onboard(state: State, runtime: Runtime[RouterContext]) -> dict[str, Any]:
    """First-contact welcome for new users; passthrough once onboarded.

    When the user isn't onboarded, the onboarding module sends a warm welcome
    (and persists it) and we short-circuit to END for this turn. Otherwise we
    return nothing and the graph continues to `classify`.
    """
    if runtime.context.onboarded:
        # Reset the one-shot flag. It lives in the checkpointed state, so a
        # stale True left over from the first-contact turn would otherwise make
        # `route_after_onboard` send THIS turn straight to END (replaying the
        # old welcome) instead of continuing to `classify`.
        return {"onboarding_handled": False}
    # Lazy import keeps router import cheap and avoids the audio<->router cycle.
    from services.agent import onboarding

    return await onboarding.run(state, runtime)


def route_after_onboard(state: State) -> str:
    """Skip the rest of the graph on the turn we sent a welcome."""
    return "end" if state.get("onboarding_handled") else "classify"


async def classify(state: State) -> dict[str, Any]:
    """Route to a domain AND profile literacy + tone in one structured call."""
    from config.settings import settings

    model = ChatOpenAI(
        model=os.environ.get("PUCHO_ROUTER_MODEL", "gpt-4o-mini"),
        api_key=settings.OPENAI_API_KEY,
    )
    router_model = model.with_structured_output(Route)

    system_prompt = ROUTER_SYSTEM_PROMPT.format(literacy_prior=_literacy_prior(state))
    route: Route = await router_model.ainvoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=state["input_question"]),
        ]
    )
    return {
        "decision": route.step,
        "literacy_level": route.literacy_level,
        "emotional_tone": route.emotional_tone,
        "search_query": route.search_query,
    }


# ---------------------------------------------------------------------------
# Domain-agent wrappers — each takes (state, runtime) and reads user_id from
# runtime.context so the agent can pull facts from `user_memories` scoped to
# this sender.
# ---------------------------------------------------------------------------


async def legal_node(state: State, runtime: Runtime[RouterContext]) -> dict[str, Any]:
    # Lazy import breaks the router <-> domain-agent cycle: the domain modules
    # import RouterContext from here, so we can't import them at module load.
    from services.RAG import legal

    return await legal.run(state, runtime)


async def healthcare_node(state: State, runtime: Runtime[RouterContext]) -> dict[str, Any]:
    from services.RAG import healthcare

    return await healthcare.run(state, runtime)


async def financial_node(state: State, runtime: Runtime[RouterContext]) -> dict[str, Any]:
    from services.RAG import financial

    return await financial.run(state, runtime)


# ---------------------------------------------------------------------------
# Post-domain persistence + enqueue + reflect
# ---------------------------------------------------------------------------


def make_thread_id(phone_number: str) -> str:
    """Stable per-sender thread id used both for messages.thread_id and
    for the LangGraph checkpointer's configurable.thread_id.
    """
    return f"wa-{phone_number}"


async def persist_message(
    state: State, runtime: Runtime[RouterContext]
) -> dict[str, Any]:
    """Write the AI's reply to the `messages` table; record id in state.

    Also persists the running literacy profile so personalisation deepens
    across the user's week. Skips the message write when output_text is empty
    (defensive — empty replies shouldn't pollute the audit trail).
    """
    # Persist the latest literacy read regardless of whether a reply was sent.
    literacy = state.get("literacy_level")
    if literacy:
        await crud_whatsapp_user.set_literacy_level(runtime.context.user_id, literacy)

    output_text = state.get("output_text") or ""
    if not output_text:
        return {}

    modality = state.get("modality") or "text"
    row = await crud_message.create_message(
        user_id=runtime.context.user_id,
        thread_id=make_thread_id(runtime.context.phone_number),
        role="ai",
        modality=modality,
        content=output_text,
    )
    return {"last_message_id": row.id}


async def enqueue_review(
    state: State, runtime: Runtime[RouterContext]
) -> dict[str, Any]:
    """Enqueue ONE pending review for the domain that actually answered.

    The domain is whatever `classify` decided; we must not fan out to all
    three domains (that would write three reviews per turn).
    """
    from services.knowledge.enqueue import create_pending_review

    decision = state.get("decision")
    if decision is None:
        return {}
    return await create_pending_review(state, runtime, domain=MemoryDomain(decision))


async def reflect(
    state: State, runtime: Runtime[RouterContext]
) -> dict[str, Any]:
    """Extract facts scoped to the domain that answered this turn.

    Best-effort: memory extraction must never break the user's reply, so any
    failure here is logged and swallowed (the answer was already generated and
    persisted by the earlier nodes).
    """
    decision = state.get("decision")
    if decision is None:
        return {}
    try:
        return await extract_facts_for(state, runtime, domain=MemoryDomain(decision))
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "reflect failed; skipping memory extraction for this turn"
        )
        return {}


def route_decision(state: State) -> str:
    """Conditional-edge function: pick the next node based on `decision`."""
    decision = state.get("decision")
    if decision == "legal":
        return "legal_agent"
    if decision == "healthcare":
        return "healthcare_agent"
    if decision == "financial":
        return "financial_agent"
    # Defensive fallback — LangGraph requires a string return.
    return END


# ---------------------------------------------------------------------------
# Build & compile the graph
# ---------------------------------------------------------------------------

router_builder = StateGraph(State, context_schema=RouterContext)

router_builder.add_node("transcribe_if_voice", transcribe_if_voice)
router_builder.add_node("onboard", onboard)
router_builder.add_node("classify", classify)
router_builder.add_node("legal_agent", legal_node)
router_builder.add_node("healthcare_agent", healthcare_node)
router_builder.add_node("financial_agent", financial_node)
router_builder.add_node("persist_message", persist_message)
router_builder.add_node("enqueue_review", enqueue_review)
router_builder.add_node("reflect", reflect)

router_builder.add_edge(START, "transcribe_if_voice")
# New users get a welcome and the turn ends; onboarded users continue to classify.
router_builder.add_edge("transcribe_if_voice", "onboard")
router_builder.add_conditional_edges(
    "onboard",
    route_after_onboard,
    {"classify": "classify", "end": END},
)
router_builder.add_conditional_edges(
    "classify",
    route_decision,
    {
        "legal_agent": "legal_agent",
        "healthcare_agent": "healthcare_agent",
        "financial_agent": "financial_agent",
    },
)
# After each domain agent: persist the assistant message → enqueue a QA review →
# reflect. enqueue_review and reflect both read state["decision"] so they act
# on the ONE domain that answered (no per-domain fan-out).
router_builder.add_edge("legal_agent", "persist_message")
router_builder.add_edge("healthcare_agent", "persist_message")
router_builder.add_edge("financial_agent", "persist_message")
router_builder.add_edge("persist_message", "enqueue_review")
router_builder.add_edge("enqueue_review", "reflect")
router_builder.add_edge("reflect", END)


async def compile_router():
    """Compile the graph with the AsyncPostgresSaver checkpointer attached.

    Called from FastAPI's lifespan at app startup; the compiled graph is
    stored in `router_workflow` (mutable) so the rest of the codebase can
    keep importing `from services.agents import router_workflow` and the
    app module can hand the same reference into the webhook handler.
    """
    global router_workflow
    checkpointer = await get_checkpointer()
    router_workflow = router_builder.compile(checkpointer=checkpointer)
    return router_workflow


# Mutable; assigned by `compile_router()` at startup. Imported as
# `from services.agents import router_workflow` elsewhere.
router_workflow = None