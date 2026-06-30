"""Pucho router agent (LangGraph StateGraph).

Flow:
    START
      → transcribe_if_voice   (calls the Sarvam STT tool when modality=="voice")
      → classify              (OpenAI structured-output picks legal/medical/financial)
      → conditional edge      (routes to the matching domain agent)
      → legal | medical | financial   (each runs its own RAG + (optional) TTS)
      → persist_message       (writes one row to `messages`, captures message_id)
      → enqueue_review        (auto-writes a `pending` row into qa_reviews)
      → reflect_<domain>      (extracts facts via structured-output → crud.memory.upsert)
      → END

State shape:
    input_question:    the user's question (after STT if the input was voice)
    language:          BCP-47 language code (e.g. "en-IN", "hi-IN")
    modality:          "text" or "voice" — the original inbound modality
    audio_bytes:       raw audio when modality=="voice", otherwise None
    decision:          one of "legal" | "medical" | "financial" after classify
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
from typing import Any, Literal
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

import crud.message as crud_message
from config.db import get_checkpointer
from models.memory import MemoryDomain
from services.memory.reflect import extract_facts_for
from services.tools.speech_to_text import speech_to_text


class Route(BaseModel):
    """Structured-output schema for the router classifier."""

    step: Literal["legal", "medical", "financial"] = Field(
        description="The domain the user's question should be routed to."
    )


class State(TypedDict, total=False):
    input_question: str
    language: str
    modality: Literal["text", "voice"]
    audio_bytes: bytes | None
    decision: Literal["legal", "medical", "financial"] | None
    output_text: str | None
    output_audio_url: str | None
    messages: list  # chat history; reflect reads latest exchange
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


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

ROUTER_SYSTEM_PROMPT = """You are the routing layer of Pucho, a WhatsApp chatbot
that dispatches user questions to a legal, medical, or financial specialist agent.

Pick exactly one domain. If the question spans multiple domains, pick the most
specific one. Do not answer the question yourself — only classify.
"""


async def transcribe_if_voice(state: State) -> dict[str, Any]:
    """If the inbound modality is voice, run STT and write the text back to state."""
    if state.get("modality") != "voice":
        return {}

    audio_bytes: bytes | None = state.get("audio_bytes")
    if not audio_bytes:
        return {"input_question": ""}

    transcribed = await speech_to_text.ainvoke(
        {"audio_bytes": audio_bytes, "language_code": state.get("language") or "unknown"}
    )
    return {"input_question": transcribed if isinstance(transcribed, str) else str(transcribed)}


async def classify(state: State) -> dict[str, Any]:
    """Pick legal/medical/financial via OpenAI structured output."""
    model = ChatOpenAI(model=os.environ.get("PUCHO_ROUTER_MODEL", "gpt-4o-mini"))
    router_model = model.with_structured_output(Route)

    decision: Route = await router_model.ainvoke(
        [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=state["input_question"]),
        ]
    )
    return {"decision": decision.step}


# ---------------------------------------------------------------------------
# Domain-agent wrappers — each takes (state, runtime) and reads user_id from
# runtime.context so the agent can pull facts from `user_memories` scoped to
# this sender.
# ---------------------------------------------------------------------------


async def legal_node(state: State, runtime: Runtime[RouterContext]) -> dict[str, Any]:
    # Lazy import breaks the router <-> domain-agent cycle: the domain modules
    # import RouterContext from here, so we can't import them at module load.
    from services.agents import legal

    return await legal.run(state, runtime)


async def medical_node(state: State, runtime: Runtime[RouterContext]) -> dict[str, Any]:
    from services.agents import medical

    return await medical.run(state, runtime)


async def financial_node(state: State, runtime: Runtime[RouterContext]) -> dict[str, Any]:
    from services.agents import financial

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

    Skips when output_text is empty (defensive — empty replies shouldn't
    pollute the audit trail).
    """
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


async def enqueue_review_legal(
    state: State, runtime: Runtime[RouterContext]
) -> dict[str, Any]:
    from services.knowledge.enqueue import create_pending_review
    return await create_pending_review(state, runtime, domain=MemoryDomain.LEGAL)


async def enqueue_review_medical(
    state: State, runtime: Runtime[RouterContext]
) -> dict[str, Any]:
    from services.knowledge.enqueue import create_pending_review
    return await create_pending_review(state, runtime, domain=MemoryDomain.MEDICAL)


async def enqueue_review_financial(
    state: State, runtime: Runtime[RouterContext]
) -> dict[str, Any]:
    from services.knowledge.enqueue import create_pending_review
    return await create_pending_review(state, runtime, domain=MemoryDomain.FINANCIAL)


async def reflect_legal(
    state: State, runtime: Runtime[RouterContext]
) -> dict[str, Any]:
    return await extract_facts_for(state, runtime, domain=MemoryDomain.LEGAL)


async def reflect_medical(
    state: State, runtime: Runtime[RouterContext]
) -> dict[str, Any]:
    return await extract_facts_for(state, runtime, domain=MemoryDomain.MEDICAL)


async def reflect_financial(
    state: State, runtime: Runtime[RouterContext]
) -> dict[str, Any]:
    return await extract_facts_for(state, runtime, domain=MemoryDomain.FINANCIAL)


def route_decision(state: State) -> str:
    """Conditional-edge function: pick the next node based on `decision`."""
    decision = state.get("decision")
    if decision == "legal":
        return "legal_agent"
    if decision == "medical":
        return "medical_agent"
    if decision == "financial":
        return "financial_agent"
    # Defensive fallback — LangGraph requires a string return.
    return END


# ---------------------------------------------------------------------------
# Build & compile the graph
# ---------------------------------------------------------------------------

router_builder = StateGraph(State, context_schema=RouterContext)

router_builder.add_node("transcribe_if_voice", transcribe_if_voice)
router_builder.add_node("classify", classify)
router_builder.add_node("legal_agent", legal_node)
router_builder.add_node("medical_agent", medical_node)
router_builder.add_node("financial_agent", financial_node)
router_builder.add_node("persist_message", persist_message)
router_builder.add_node("enqueue_review_legal", enqueue_review_legal)
router_builder.add_node("enqueue_review_medical", enqueue_review_medical)
router_builder.add_node("enqueue_review_financial", enqueue_review_financial)
router_builder.add_node("reflect_legal", reflect_legal)
router_builder.add_node("reflect_medical", reflect_medical)
router_builder.add_node("reflect_financial", reflect_financial)

router_builder.add_edge(START, "transcribe_if_voice")
router_builder.add_edge("transcribe_if_voice", "classify")
router_builder.add_conditional_edges(
    "classify",
    route_decision,
    {
        "legal_agent": "legal_agent",
        "medical_agent": "medical_agent",
        "financial_agent": "financial_agent",
    },
)
# After each domain agent: persist the assistant message → enqueue a QA review →
# run the matching reflect node (which knows its own domain's fact-key vocab).
router_builder.add_edge("legal_agent", "persist_message")
router_builder.add_edge("medical_agent", "persist_message")
router_builder.add_edge("financial_agent", "persist_message")
router_builder.add_edge("persist_message", "enqueue_review_legal")
router_builder.add_edge("persist_message", "enqueue_review_medical")
router_builder.add_edge("persist_message", "enqueue_review_financial")
router_builder.add_edge("enqueue_review_legal", "reflect_legal")
router_builder.add_edge("enqueue_review_medical", "reflect_medical")
router_builder.add_edge("enqueue_review_financial", "reflect_financial")
router_builder.add_edge("reflect_legal", END)
router_builder.add_edge("reflect_medical", END)
router_builder.add_edge("reflect_financial", END)


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