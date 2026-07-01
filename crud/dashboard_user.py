"""Dashboard-user CRUD — async operations on the `dashboard_users` table.

Holds the bcrypt password helpers used by dashboard login + the admin
user-management flow (create reviewer, reset password, list by role).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import bcrypt
from sqlalchemy import select
from sqlmodel import col

from config.db import get_session
from models.dashboard_user import DashboardUserModel, DashboardUserUpdate
from models.enums import DashboardRoleLiteral

# bcrypt work factor — 12 is the standard cost-vs-latency compromise for
# 2026-era hardware; takes ~250ms on a modern x86 core.
_BCRYPT_ROUNDS = 12


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password with bcrypt. Returns the hash as a str."""
    return bcrypt.hashpw(
        plaintext.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    ).decode("utf-8")


def verify_password(plaintext: str, password_hash: str | None) -> bool:
    """Constant-time check. Returns False on a missing hash rather than raising."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


async def get_by_id(user_id: UUID) -> DashboardUserModel | None:
    async with get_session() as session:
        return await session.get(DashboardUserModel, user_id)


async def get_by_email(email: str) -> DashboardUserModel | None:
    async with get_session() as session:
        stmt = select(DashboardUserModel).where(col(DashboardUserModel.email) == email)
        return (await session.execute(stmt)).scalar_one_or_none()


async def create_with_email(
    *,
    name: str,
    email: str,
    password: str,
    role: DashboardRoleLiteral,
) -> DashboardUserModel:
    """Create a dashboard-reviewer row (name + email + bcrypt hash + role)."""
    async with get_session() as session:
        new_user = DashboardUserModel(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        session.add(new_user)
        await session.flush()
        await session.refresh(new_user)
        return new_user


async def update(
    user_id: UUID, patch: DashboardUserUpdate
) -> DashboardUserModel | None:
    async with get_session() as session:
        row = await session.get(DashboardUserModel, user_id)
        if row is None:
            return None
        for k, v in patch.model_dump(exclude_unset=True).items():
            setattr(row, k, v)
        await session.flush()
        await session.refresh(row)
        return row


async def set_password(user_id: UUID, new_password: str) -> DashboardUserModel | None:
    """Admin-style password reset. Hashes before persisting."""
    return await update(
        user_id, DashboardUserUpdate(password_hash=hash_password(new_password))
    )


async def touch_last_login(user_id: UUID) -> None:
    """Update `last_login_at` to now(). Side-effect only — no return."""
    await update(user_id, DashboardUserUpdate(last_login_at=datetime.now(timezone.utc)))


async def list_for_role(
    role: DashboardRoleLiteral, *, limit: int = 100
) -> list[DashboardUserModel]:
    """Admin view: list dashboard users of one role (e.g. all volunteers)."""
    async with get_session() as session:
        stmt = (
            select(DashboardUserModel)
            .where(col(DashboardUserModel.role) == role)
            .order_by(col(DashboardUserModel.created_at).desc())
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "hash_password",
    "verify_password",
    "get_by_id",
    "get_by_email",
    "create_with_email",
    "update",
    "set_password",
    "touch_last_login",
    "list_for_role",
]
