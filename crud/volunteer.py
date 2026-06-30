"""Local-volunteer CRUD.

Volunteers are dashboard users with `users.role='volunteer'`; this table
holds their profile data (display name, preferred language, active flag).
The 1:1 with `users` is enforced at the DB level via UNIQUE on `user_id`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update as sql_update
from sqlmodel import col

from config.db import get_session
from models.volunteer import LocalVolunteerCreate, LocalVolunteerModel


async def create(
    *,
    user_id: UUID,
    display_name: str,
    preferred_language: str | None = None,
) -> LocalVolunteerModel:
    payload = LocalVolunteerCreate(
        user_id=user_id,
        display_name=display_name,
        preferred_language=preferred_language,
        active=True,
    )
    async with get_session() as session:
        row = LocalVolunteerModel(**payload.model_dump())
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return row


async def get_by_id(volunteer_id: UUID) -> LocalVolunteerModel | None:
    async with get_session() as session:
        return await session.get(LocalVolunteerModel, volunteer_id)


async def get_by_user_id(user_id: UUID) -> LocalVolunteerModel | None:
    async with get_session() as session:
        stmt = select(LocalVolunteerModel).where(
            col(LocalVolunteerModel.user_id) == user_id
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def list_active(*, limit: int = 100) -> list[LocalVolunteerModel]:
    async with get_session() as session:
        stmt = (
            select(LocalVolunteerModel)
            .where(col(LocalVolunteerModel.active).is_(True))
            .order_by(col(LocalVolunteerModel.created_at).desc())
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())


async def deactivate(volunteer_id: UUID) -> bool:
    async with get_session() as session:
        result = await session.execute(
            sql_update(LocalVolunteerModel)
            .where(col(LocalVolunteerModel.id) == volunteer_id)
            .values(active=False, updated_at=datetime.utcnow())
        )
        return bool(result.rowcount)


__all__ = ["create", "get_by_id", "get_by_user_id", "list_active", "deactivate"]