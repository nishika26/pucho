"""Reflect-node body — extract facts from the latest exchange and persist them.

`extract_facts_for(state, runtime)` is wired into the router graph as a
post-domain node (one per domain). It looks at the most recent Human/AI
messages, calls a structured-output LLM to propose facts, and writes each
proposed fact via `crud.memory.upsert`. The graph's `State` is not mutated
beyond `last_message_id` (already set by `persist_message`); writes are
side-effects against the DB, not the graph state.

Why eager (not lazy)?
The reflect step runs every turn, so facts converge immediately. A user who
mentions their diabetes on turn 3 has it available on turn 4 without any
explicit "remember this" command.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime

import crud.memory as crud_memory
from models.memory import FactsToMemorize, MemoryDomain
from services.memory.vocab import keys_for_domain

_SYSTEM_PROMPT_TEMPLATE = """You are an information-extraction step for a personal-assistant chatbot.
Given the latest user message and assistant reply, identify any durable facts worth remembering about the user.

Domain scope (you only extract within ONE of these domains per fact):
{domain_block}

Rules:
- Only facts the USER revealed, not generic knowledge or assistant claims.
- Skip ephemeral context (current mood, what they had for lunch today).
- Skip anything the assistant inferred but the user didn't actually state.
- Reuse the canonical `key` from the vocabulary when one fits; invent a new
  snake_case key only if nothing in the vocabulary covers it.
- `confidence`: 1.0 if the user explicitly stated it; 0.7-0.9 if mentioned
  in passing or hedged ("I think I have…"); never above 1.0.
- `value` must be JSON-serialisable: prefer arrays for lists, objects for
  structured records, strings for scalar facts.

If there is nothing worth remembering, return {{"facts": []}} — do not force facts.
"""


def _domain_block(domain: MemoryDomain) -> str:
    keys = keys_for_domain(domain.value)
    bullets = "\n".join(f"  - {domain.value}.{k}" for k in keys)
    return f"Domain: {domain.value}\nRecognised keys:\n{bullets}"


def _extract_messages(state: dict[str, Any]) -> tuple[str, str]:
    """Return (user question, bot answer) for this turn.

    Prefer the reliable state keys: the user's question is in `input_question`
    and the reply in `output_text`. We do NOT depend on `state["messages"]`,
    because the domain node replaces that channel with only its AIMessage — so
    the user's turn (where the facts actually come from) isn't there.
    """
    human = state.get("input_question") or ""
    ai = state.get("output_text") or ""
    if human or ai:
        return str(human), str(ai)

    # Fallback: parse the message list if the keys are somehow empty.
    messages = state.get("messages", [])
    human = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )
    ai = next(
        (m.content for m in reversed(messages) if isinstance(m, AIMessage)), ""
    )
    return str(human or ""), str(ai or "")


async def extract_facts_for(
    state: dict[str, Any],
    runtime: Runtime,
    *,
    domain: MemoryDomain,
) -> dict[str, Any]:
    """Reflect-node body for one domain.

    Reads `runtime.context.user_id` (set by the router's `context_schema`)
    and `state["last_message_id"]` (set by the preceding persist_message node),
    extracts facts, writes them via the CRUD layer. Returns an empty state
    delta — persistence is a side-effect of running this node, not a graph
    state mutation.
    """
    user_id: UUID | None = getattr(runtime.context, "user_id", None)
    if user_id is None:
        # Adapter forgot to wire context — fail loudly rather than silently
        # write facts against the wrong user.
        raise RuntimeError(
            "extract_facts_for called without runtime.context.user_id; "
            "router must declare context_schema=RouterContext"
        )

    source_message_id: UUID | None = state.get("last_message_id")
    human, ai = _extract_messages(state)
    if not human and not ai:
        # Nothing to reflect on (shouldn't happen in normal flow).
        return {}

    from config.settings import settings

    # method="function_calling" because FactsToMemorize has a `value: Any` field,
    # which OpenAI's strict structured-output mode rejects (every property needs
    # a type). Function-calling mode is lenient about arbitrary-JSON fields.
    llm = ChatOpenAI(
        model="gpt-4o-mini", temperature=0, api_key=settings.OPENAI_API_KEY
    ).with_structured_output(FactsToMemorize, method="function_calling")
    proposed = await llm.ainvoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE.format(
                domain_block=_domain_block(domain),
            )},
            {"role": "user", "content": f"User: {human}\n\nAssistant: {ai}"},
        ]
    )
    if not proposed.facts:
        return {}

    for fact in proposed.facts:
        # Only persist facts whose domain matches the node we're running.
        # Cross-domain facts (rare) get handled by the matching node on a
        # future turn, so we don't drop them — we just defer them.
        if fact.domain != domain.value:
            continue
        await crud_memory.upsert(
            user_id=user_id,
            domain=domain,
            key=fact.key,
            value=fact.value,
            confidence=fact.confidence,
            source_message_id=source_message_id,
        )
    return {}


__all__ = ["extract_facts_for"]