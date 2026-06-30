"""Memory-bridge services.

Two responsibilities:
- `reflect.extract_facts_for(...)` — turn the latest exchange into structured
  facts and write them via `crud.memory.upsert`. Runs as a LangGraph node.
- `inject.format_memories_for_prompt(...)` — render the user's facts into a
  string the domain agent can drop into its system prompt.

This module is the only place that knows about both the LangGraph/LangChain
side and the CRUD side. Domain-agent `run()` calls `inject`; the router's
post-domain node calls `reflect`. Neither has to know about the other's layer.
"""

from services.memory.inject import format_memories_for_prompt
from services.memory.reflect import extract_facts_for

__all__ = ["extract_facts_for", "format_memories_for_prompt"]