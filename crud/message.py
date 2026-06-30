"""Message CRUD — async operations on the `messages` table.

Each inbound and outbound WhatsApp message is persisted so:
- The reflect node can attach `source_message_id` to facts it writes.
- The future short-term-memory layer (PostgresSaver migration) can read
  conversation history in normalised form.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlmodel import col

from config.db import get_session
from models.message import MessageCreate, MessageModel, MessageModality, MessageRole


async def create_message(
    *,
    user_id: UUID,
    thread_id: str,
    role: MessageRole,
    modality: MessageModality,
    content: str,
) -> MessageModel:
    """Insert one message row and return it (with id assigned by the DB)."""
    payload = MessageCreate(
        user_id=user_id,
        thread_id=thread_id,
        role=role,
        modality=modality,
        content=content,
    )
    async with get_session() as session:
        row = MessageModel(**payload.model_dump())
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return row


async def list_for_thread(
    thread_id: str,
    *,
    user_id: UUID | None = None,
    limit: int = 100,
) -> list[MessageModel]:
    """Return messages for `thread_id` in chronological order.

    Pass `user_id` to scope the lookup to a specific user (defense in depth;
    thread_id is currently derived from the user's phone, but adding a
    user_id filter keeps the function safe to call from multi-user paths).
    """
    async with get_session() as session:
        stmt = (
            select(MessageModel)
            .where(col(MessageModel.thread_id) == thread_id)
            .order_by(col(MessageModel.created_at).asc())
            .limit(limit)
        )
        if user_id is not None:
            stmt = stmt.where(col(MessageModel.user_id) == user_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["create_message", "list_for_thread"]