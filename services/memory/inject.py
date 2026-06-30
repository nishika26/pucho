"""Inject long-term memories into a domain agent's system prompt.

Pure formatting — no DB access, no LangGraph imports. Takes the list of
`UserMemoryModel` rows that `crud.memory.list_for_user_domain` returned and
turns them into a string block the agent's `SYSTEM_PROMPT` can append.

The output is meant to be read by an LLM, not by humans. Keys are stable
identifiers so the model can refer back to them across turns ("given the
user's `chronic_conditions` …").
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from models.memory import UserMemoryModel


def format_memories_for_prompt(memories: Iterable[UserMemoryModel]) -> str:
    """Render memories as a system-prompt section.

    Empty input → empty string, so callers can concatenate unconditionally:
        system_prompt = SYSTEM_PROMPT + format_memories_for_prompt(memories)
    """
    rows = list(memories)
    if not rows:
        return ""

    lines = ["Known facts about this user (from prior turns, persisted):"]
    for row in rows:
        value_str = json.dumps(row.value, ensure_ascii=False, sort_keys=True)
        confidence = (
            f", confidence={row.confidence:.2f}"
            if row.confidence < 1.0
            else ""
        )
        lines.append(f"- {row.domain}.{row.key}{confidence}: {value_str}")
    return "\n".join(lines)


__all__ = ["format_memories_for_prompt"]