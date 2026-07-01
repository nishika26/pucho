"""qa_reviews CRUD.

The approval queue per the senior-engineer doc:
- Every domain turn inserts one row with status='pending' (via
  `services/knowledge/enqueue.create_pending_review`).
- Volunteers append `local_input` via `set_local_input`.
- Experts append `expert_input` via `set_expert_input`, then either
  `mark_approved` (which kicks off `services/knowledge/ingest`) or
  `mark_rejected`.

Cross-table invariants enforced by callers:
- mark_approved(id, expert_id) only valid if expert_id refers to a row in
  domain_experts whose domain matches the qa_review's domain.
- mark_approved is paired with `services.knowledge.ingest.ingest_qa_review`
  which writes documents rows and stamps `documents_chunk_id`.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlmodel import col

from config.db import get_session
from models.enums import QAReviewStatus
from models.memory import MemoryDomainLiteral
from models.qa_review import QAReviewCreate, QAReviewModel, QAReviewUpdate


async def create(payload: QAReviewCreate) -> QAReviewModel:
    async with get_session() as session:
        row = QAReviewModel(**payload.model_dump())
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return row


async def get_by_id(review_id: UUID) -> QAReviewModel | None:
    async with get_session() as session:
        return await session.get(QAReviewModel, review_id)


async def list_pending(
    *,
    domain: MemoryDomainLiteral | None = None,
    limit: int = 50,
) -> list[QAReviewModel]:
    """Default dashboard view — newest-first, optionally domain-scoped."""
    async with get_session() as session:
        stmt = (
            select(QAReviewModel)
            .where(col(QAReviewModel.status) == QAReviewStatus.PENDING)
            .order_by(col(QAReviewModel.created_at).desc())
            .limit(limit)
        )
        if domain is not None:
            stmt = stmt.where(col(QAReviewModel.domain) == domain)
        return list((await session.execute(stmt)).scalars().all())


async def list_by_status(
    status: QAReviewStatus,
    *,
    domain: MemoryDomainLiteral | None = None,
    limit: int = 100,
) -> list[QAReviewModel]:
    async with get_session() as session:
        stmt = (
            select(QAReviewModel)
            .where(col(QAReviewModel.status) == status)
            .order_by(col(QAReviewModel.created_at).desc())
            .limit(limit)
        )
        if domain is not None:
            stmt = stmt.where(col(QAReviewModel.domain) == domain)
        return list((await session.execute(stmt)).scalars().all())


async def update(review_id: UUID, patch: QAReviewUpdate) -> QAReviewModel | None:
    async with get_session() as session:
        row = await session.get(QAReviewModel, review_id)
        if row is None:
            return None
        data = patch.model_dump(exclude_unset=True)
        for k, v in data.items():
            # Enum → plain str so the SQL column (VARCHAR) accepts it.
            if hasattr(v, "value"):
                v = v.value
            setattr(row, k, v)
        await session.flush()
        await session.refresh(row)
        return row


async def set_local_input(
    review_id: UUID, local_input: str, volunteer_id: UUID
) -> QAReviewModel | None:
    return await update(
        review_id,
        QAReviewUpdate(local_input=local_input, local_volunteer_id=volunteer_id),
    )


async def set_expert_input(
    review_id: UUID, expert_input: str, expert_id: UUID
) -> QAReviewModel | None:
    return await update(
        review_id,
        QAReviewUpdate(expert_input=expert_input, expert_id=expert_id),
    )


async def mark_approved(
    review_id: UUID, expert_id: UUID, documents_chunk_id: UUID | None
) -> QAReviewModel | None:
    return await update(
        review_id,
        QAReviewUpdate(
            status=QAReviewStatus.APPROVED,
            expert_id=expert_id,
            documents_chunk_id=documents_chunk_id,
        ),
    )


async def mark_rejected(review_id: UUID, expert_id: UUID) -> QAReviewModel | None:
    return await update(
        review_id,
        QAReviewUpdate(status=QAReviewStatus.REJECTED, expert_id=expert_id),
    )


__all__ = [
    "create",
    "get_by_id",
    "list_pending",
    "list_by_status",
    "update",
    "set_local_input",
    "set_expert_input",
    "mark_approved",
    "mark_rejected",
]