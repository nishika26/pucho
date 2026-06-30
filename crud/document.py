"""documents CRUD — the RAG knowledge base.

Two write paths converge on `documents`:
- `services/knowledge/ingest.py` writes chunks here when an expert approves
  a qa_review (source='expert_approved').
- `scripts/seed_documents.py` (deferred) writes static manual docs
  (source='manual').

Reads are funnelled through `services/knowledge/retriever_impl.py`, which
calls `list_for_domain_cosine(...)` for v1 (pgvector cosine only).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlmodel import col

from config.db import get_session
from models.document import DocumentCreate, DocumentModel
from models.enums import DocumentSourceLiteral
from models.memory import MemoryDomainLiteral


async def create(payload: DocumentCreate) -> DocumentModel:
    async with get_session() as session:
        row = DocumentModel(**payload.model_dump())
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return row


async def get_by_id(doc_id: UUID) -> DocumentModel | None:
    async with get_session() as session:
        return await session.get(DocumentModel, doc_id)


async def list_for_qa_review(qa_review_id: UUID) -> list[DocumentModel]:
    """Enumerate the chunks that came out of one expert approval."""
    async with get_session() as session:
        stmt = (
            select(DocumentModel)
            .where(col(DocumentModel.qa_review_id) == qa_review_id)
            .order_by(col(DocumentModel.created_at).asc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def list_for_domain(
    domain: MemoryDomainLiteral,
    *,
    source: DocumentSourceLiteral | None = None,
    limit: int = 50,
) -> list[DocumentModel]:
    async with get_session() as session:
        stmt = (
            select(DocumentModel)
            .where(col(DocumentModel.domain) == domain)
            .order_by(col(DocumentModel.created_at).desc())
            .limit(limit)
        )
        if source is not None:
            stmt = stmt.where(col(DocumentModel.source) == source)
        return list((await session.execute(stmt)).scalars().all())


__all__ = ["create", "get_by_id", "list_for_qa_review", "list_for_domain"]