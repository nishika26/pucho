"""Domain-expert CRUD.

An expert is identified by the pair `(user_id, domain)`. `get_for_domain`
returns the active experts for one domain; `list_for_user` returns the
expert profile rows owned by one login user (a user can be an expert for
multiple domains).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlmodel import col

from config.db import get_session
from models.enums import EducationLevelLiteral, WorkStatusLiteral
from models.expert import DomainExpertCreate, DomainExpertModel
from models.memory import MemoryDomainLiteral


async def create(
    *,
    user_id: UUID,
    domain: MemoryDomainLiteral,
    name: str,
    highest_education: EducationLevelLiteral,
    work_status: WorkStatusLiteral,
    verified: bool = False,
) -> DomainExpertModel:
    payload = DomainExpertCreate(
        user_id=user_id,
        domain=domain,
        name=name,
        highest_education=highest_education,
        work_status=work_status,
        verified=verified,
        active=True,
    )
    async with get_session() as session:
        row = DomainExpertModel(**payload.model_dump())
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return row


async def get_by_id(expert_id: UUID) -> DomainExpertModel | None:
    async with get_session() as session:
        return await session.get(DomainExpertModel, expert_id)


async def get_for_user_domain(
    user_id: UUID, domain: MemoryDomainLiteral
) -> DomainExpertModel | None:
    """Lookup the (user_id, domain) expert row used for qa_reviews.expert_id."""
    async with get_session() as session:
        stmt = select(DomainExpertModel).where(
            col(DomainExpertModel.user_id) == user_id,
            col(DomainExpertModel.domain) == domain,
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_domain(domain: MemoryDomainLiteral, *, limit: int = 100) -> list[DomainExpertModel]:
    async with get_session() as session:
        stmt = (
            select(DomainExpertModel)
            .where(
                col(DomainExpertModel.domain) == domain,
                col(DomainExpertModel.active).is_(True),
            )
            .order_by(col(DomainExpertModel.created_at).desc())
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())


async def list_for_user(user_id: UUID) -> list[DomainExpertModel]:
    async with get_session() as session:
        stmt = (
            select(DomainExpertModel)
            .where(col(DomainExpertModel.user_id) == user_id)
            .order_by(col(DomainExpertModel.domain).asc())
        )
        return list((await session.execute(stmt)).scalars().all())


async def deactivate(expert_id: UUID) -> bool:
    from datetime import datetime
    from sqlalchemy import update as sql_update
    async with get_session() as session:
        result = await session.execute(
            sql_update(DomainExpertModel)
            .where(col(DomainExpertModel.id) == expert_id)
            .values(active=False, updated_at=datetime.utcnow())
        )
        return bool(result.rowcount)


__all__ = [
    "create",
    "get_by_id",
    "get_for_user_domain",
    "list_for_domain",
    "list_for_user",
    "deactivate",
]