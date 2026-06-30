"""RAG retriever interface for the three domain agents.

Each domain (legal / medical / financial) has its own corpus and its own
retriever. The v1 vector store is pgvector via Supabase — see
`services.knowledge.retriever_impl.PgVectorRetriever`. The factory below
caches one retriever per domain at module load.

Swap detection:
- The `get_retriever` body is the only edit needed if you migrate to a
  different Vercel-compatible vector store later (Pinecone / Qdrant Cloud /
  Upstash Vector). The `Retriever` Protocol stays the same.
"""

from __future__ import annotations

from typing import Literal, Protocol

from langchain_core.documents import Document

Domain = Literal["legal", "medical", "financial"]


class Retriever(Protocol):
    """Async-friendly retriever contract used by every domain agent."""

    async def retrieve(self, query: str, *, k: int = 4) -> list[Document]:
        """Return up to `k` relevant documents for `query`.

        Implementations should never raise on an empty corpus — return [].
        Domain agents decide how to behave when retrieval returns nothing.
        """
        ...


_cache: dict[str, Retriever] = {}


def get_retriever(domain: Domain) -> Retriever:
    """Return the retriever for `domain`. v1: pgvector via PgVectorRetriever.

    One instance is built per domain at module load and cached. If you wire
    a different vector store later, replace the body of this function — the
    Protocol above stays the same.
    """
    if domain in _cache:
        return _cache[domain]
    # Lazy import — pgvector + OpenAI need OPENAI_API_KEY to even construct.
    from services.knowledge.retriever_impl import PgVectorRetriever

    _cache[domain] = PgVectorRetriever(domain=domain)
    return _cache[domain]