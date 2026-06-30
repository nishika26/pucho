"""Concrete Retriever impl over the `documents` table.

Implements the `Retriever` Protocol declared in `services/agents/retriever.py`.
Cosine-distance ANN search via pgvector's `<=>` operator; v1 has no FTS or
hybrid scoring — a future migration adds a tsvector column + GIN index and
this file gets the rerank/merge step.

OpenAI embeddings are constructed lazily inside `_embed_query` so this
module can be imported in environments without `OPENAI_API_KEY` (e.g. the
dashboard's login screen during dev/tests).
"""

from __future__ import annotations

from langchain_core.documents import Document
from sqlalchemy import text

from config.db import get_session

EMBED_MODEL = "text-embedding-3-small"  # 1536 dims; matches `ingest.py`.


class PgVectorRetriever:
    """Per-domain retriever over `documents` using pgvector cosine distance.

    One instance per (domain, k). The factory in services/agents/retriever.py
    caches these per domain at module load.
    """

    def __init__(self, domain: str, *, default_k: int = 4) -> None:
        self._domain = domain
        self._default_k = default_k
        self._embeddings = None  # built lazily on first retrieve()

    def _ensure_embeddings(self):
        if self._embeddings is None:
            # Local import — keeps this module importable without OPENAI_API_KEY.
            from langchain_openai import OpenAIEmbeddings

            self._embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
        return self._embeddings

    async def _embed_query(self, query: str) -> list[float]:
        embeddings = self._ensure_embeddings()
        return await embeddings.aembed_query(query)

    async def retrieve(self, query: str, *, k: int | None = None) -> list[Document]:
        embedding = await self._embed_query(query)
        # The vector literal in pgvector is `[v1,v2,...]`. SQLAlchemy's bind
        # param doesn't auto-format Python lists; we cast the JSON list to a
        # Postgres array literal string and use ::vector.
        vec_literal = "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"
        stmt = text(
            """
            SELECT id, title, content, metadata, source, qa_review_id,
                   embedding <=> :emb AS distance
            FROM documents
            WHERE domain = :domain
            ORDER BY embedding <=> :emb
            LIMIT :k
            """
        )
        async with get_session() as session:
            result = await session.execute(
                stmt,
                {"emb": vec_literal, "domain": self._domain, "k": k or self._default_k},
            )
            rows = result.mappings().all()
        return [
            Document(
                page_content=r["content"],
                metadata={
                    "id": str(r["id"]),
                    "title": r["title"],
                    "source": r["source"],
                    "qa_review_id": str(r["qa_review_id"]) if r["qa_review_id"] else None,
                    "distance": float(r["distance"]),
                    "domain": self._domain,
                    **(r["metadata"] or {}),
                },
            )
            for r in rows
        ]


__all__ = ["PgVectorRetriever", "EMBED_MODEL"]
