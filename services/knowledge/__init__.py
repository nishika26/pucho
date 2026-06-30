"""Knowledge-base services.

Three responsibilities:
- `enqueue.create_pending_review(...)` — auto-write one qa_review row per
  domain turn, called from the router graph's `enqueue_review` node.
- `ingest.ingest_qa_review(...)` — chunk + embed + write to `documents`
  when an expert approves. Called from the dashboard's Approve button.
- `retriever_impl.PgVectorRetriever` — concrete `Retriever` over pgvector;
  swapped into `services/agents/retriever.get_retriever(...)` at startup.

This is the only layer that knows about both LangChain/LangGraph and the
CRUD layer. Domain agents consume the Retriever protocol; the dashboard
calls `ingest.ingest_qa_review` and `reject_qa_review` directly.
"""

from services.knowledge.enqueue import create_pending_review
from services.knowledge.ingest import ingest_qa_review, reject_qa_review

# `PgVectorRetriever` is intentionally NOT re-exported here: importing the
# class doesn't trigger OpenAI, but having a top-level reference makes it
# easy to accidentally drag the openai client into eager paths. Importers
# should reference it directly:
#     from services.knowledge.retriever_impl import PgVectorRetriever

__all__ = [
    "create_pending_review",
    "ingest_qa_review",
    "reject_qa_review",
]
