"""Pucho multi-agent package.

Re-exports the public surface used by the WhatsApp adapter, the dashboard,
and any local entrypoints. Domain agents live as siblings; the router
compiles them into a single LangGraph StateGraph with a PostgresSaver
checkpointer attached (compiled lazily at app startup).
"""

from services.agents import financial, legal, medical, retriever

# `router_workflow` is `None` at import time; `compile_router()` (called from
# FastAPI's lifespan) assigns the compiled graph with its checkpointer.
# Importers that need the graph read it lazily:
#     from services.agents import router_workflow
# ...but they should always check `if router_workflow is None: raise ...`
# at the call site, since uncompiled access raises from LangGraph internals.
from services.agents.router import (
    RouterContext,
    State,
    compile_router,
    make_thread_id,
    router_workflow,
)

__all__ = [
    "financial",
    "legal",
    "medical",
    "retriever",
    "RouterContext",
    "State",
    "router_workflow",
    "compile_router",
    "make_thread_id",
]