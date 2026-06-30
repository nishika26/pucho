"""User-memory CRUD — async operations on `user_memories`.

The reflect node calls `upsert(...)` once per fact it extracts from each
exchange; same `(user_id, domain, key)` triple converges to a single row
(via the unique constraint + ON CONFLICT). Domain-agent `run()` calls
`list_for_user_domain(...)` at the start of each turn to inject the user's
facts into the system prompt.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from config.db import get_session
from models.memory import MemoryDomain, UserMemoryCreate, UserMemoryModel


async def upsert(
    *,
    user_id: UUID,
    domain: MemoryDomain,
    key: str,
    value: dict[str, Any],
    confidence: float = 1.0,
    source_message_id: UUID | None = None,
) -> UserMemoryModel:
    """Insert a new fact, or overwrite the existing one for this (user, domain, key).

    Returns the post-write row (id, created_at, updated_at populated).
    """
    payload = UserMemoryCreate(
        user_id=user_id,
        domain=domain,
        key=key,
        value=value,
        confidence=confidence,
        source_message_id=source_message_id,
    )
    async with get_session() as session:
        return await _upsert_in_session(
            session,
            user_id=user_id,
            domain=domain,
            key=key,
            value=value,
            confidence=confidence,
            source_message_id=source_message_id,
        )


async def _upsert_in_session(
    session: AsyncSession,
    *,
    user_id: UUID,
    domain: MemoryDomain,
    key: str,
    value: dict[str, Any],
    confidence: float,
    source_message_id: UUID | None,
) -> UserMemoryModel:
    """Internal: do the upsert inside an existing session (for batched writes)."""
    # Look up first to decide INSERT vs UPDATE. The unique constraint would
    # catch duplicates anyway, but doing it explicitly lets us preserve
    # `created_at` on update (so audit trail is meaningful).
    stmt = select(UserMemoryModel).where(
        col(UserMemoryModel.user_id) == user_id,
        col(UserMemoryModel.domain) == domain,
        col(UserMemoryModel.key) == key,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is None:
        row = UserMemoryModel(
            user_id=user_id,
            domain=domain,
            key=key,
            value=value,
            confidence=confidence,
            source_message_id=source_message_id,
        )
        session.add(row)
    else:
        existing.value = value
        existing.confidence = confidence
        if source_message_id is not None:
            existing.source_message_id = source_message_id
        row = existing
    await session.flush()
    await session.refresh(row)
    return row


async def get_one(
    user_id: UUID, domain: MemoryDomain, key: str
) -> UserMemoryModel | None:
    async with get_session() as session:
        stmt = select(UserMemoryModel).where(
            col(UserMemoryModel.user_id) == user_id,
            col(UserMemoryModel.domain) == domain,
            col(UserMemoryModel.key) == key,
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_user_domain(
    user_id: UUID,
    domain: MemoryDomain,
    *,
    limit: int = 100,
) -> list[UserMemoryModel]:
    """All facts for this user in this domain, most-recently-updated first."""
    async with get_session() as session:
        stmt = (
            select(UserMemoryModel)
            .where(
                col(UserMemoryModel.user_id) == user_id,
                col(UserMemoryModel.domain) == domain,
            )
            .order_by(col(UserMemoryModel.updated_at).desc())
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())


async def list_keys_for_user(
    user_id: UUID, *, domain: MemoryDomain | None = None
) -> list[str]:
    """Distinct fact-keys the bot has stored for this user."""
    async with get_session() as session:
        stmt = select(col(UserMemoryModel.key)).where(
            col(UserMemoryModel.user_id) == user_id
        )
        if domain is not None:
            stmt = stmt.where(col(UserMemoryModel.domain) == domain)
        result = await session.execute(stmt)
        return sorted({row[0] for row in result.all()})


async def delete(user_id: UUID, domain: MemoryDomain, key: str) -> bool:
    """Delete one fact by its (user, domain, key) triple. Returns True if a row was removed."""
    async with get_session() as session:
        row = await session.get(
            UserMemoryModel,
            # Composite-key lookups in SQLModel need a tuple of PK values,
            # but our PK is `id`. Use the unique constraint columns instead.
            None,
        )
        # Fallback: explicit WHERE clause.
        from sqlalchemy import delete as sql_delete
        result = await session.execute(
            sql_delete(UserMemoryModel).where(
                col(UserMemoryModel.user_id) == user_id,
                col(UserMemoryModel.domain) == domain,
                col(UserMemoryModel.key) == key,
            )
        )
        return bool(result.rowcount)


__all__ = [
    "upsert",
    "get_one",
    "list_for_user_domain",
    "list_keys_for_user",
    "delete",
]