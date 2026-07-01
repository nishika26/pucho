"""WhatsApp-user CRUD — async operations on the `whatsapp_users` table.

The WhatsApp adapter calls `get_or_create_by_whatsapp_number` on every inbound
message; onboarding later fills in name / locality.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from config.db import get_session
from models.whatsapp_user import WhatsAppUserModel, WhatsAppUserUpdate


async def get_by_id(user_id: UUID) -> WhatsAppUserModel | None:
    async with get_session() as session:
        return await session.get(WhatsAppUserModel, user_id)


async def get_by_whatsapp_number(whatsapp_number: str) -> WhatsAppUserModel | None:
    async with get_session() as session:
        stmt = select(WhatsAppUserModel).where(
            WhatsAppUserModel.whatsapp_number == whatsapp_number
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def get_or_create_by_whatsapp_number(
    whatsapp_number: str,
) -> WhatsAppUserModel:
    """Return the user with this number, creating a bare row if missing.

    Used by the WhatsApp adapter on every inbound message: the bot learns
    about a new sender by writing a stub row, then onboarding fills in
    name / locality later.
    """
    async with get_session() as session:
        stmt = select(WhatsAppUserModel).where(
            WhatsAppUserModel.whatsapp_number == whatsapp_number
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing
        new_user = WhatsAppUserModel(whatsapp_number=whatsapp_number, onboarded=False)
        session.add(new_user)
        await session.flush()
        await session.refresh(new_user)
        return new_user


async def update(
    user_id: UUID, patch: WhatsAppUserUpdate
) -> WhatsAppUserModel | None:
    async with get_session() as session:
        row = await session.get(WhatsAppUserModel, user_id)
        if row is None:
            return None
        for k, v in patch.model_dump(exclude_unset=True).items():
            setattr(row, k, v)
        await session.flush()
        await session.refresh(row)
        return row


async def set_name(user_id: UUID, name: str) -> WhatsAppUserModel | None:
    return await update(user_id, WhatsAppUserUpdate(name=name))


async def set_locality(user_id: UUID, locality: str) -> WhatsAppUserModel | None:
    return await update(user_id, WhatsAppUserUpdate(locality=locality))


async def mark_onboarded(user_id: UUID) -> WhatsAppUserModel | None:
    return await update(user_id, WhatsAppUserUpdate(onboarded=True))


async def set_literacy_level(
    user_id: UUID, literacy_level: str
) -> WhatsAppUserModel | None:
    """Persist the running literacy profile (last-write-wins per turn)."""
    return await update(user_id, WhatsAppUserUpdate(literacy_level=literacy_level))


__all__ = [
    "get_by_id",
    "get_by_whatsapp_number",
    "get_or_create_by_whatsapp_number",
    "update",
    "set_name",
    "set_locality",
    "set_literacy_level",
    "mark_onboarded",
]
