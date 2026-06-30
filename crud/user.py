"""User CRUD — async operations on the `users` table.

All functions are async def, return SQLModel `UserModel`, and open their
own short-lived session via `config.db.get_session()`. No business logic
here — pure DB read/write plus the bcrypt verify wrapper for dashboard auth.
"""

from __future__ import annotations

from uuid import UUID

import bcrypt
from sqlalchemy import select
from sqlmodel import col

from config.db import get_session
from models.enums import ReviewerRoleLiteral
from models.user import UserModel, UserUpdate

# bcrypt work factor — 12 is the standard cost-vs-latency compromise for
# 2026-era hardware; takes ~250ms on a modern x86 core.
_BCRYPT_ROUNDS = 12


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password with bcrypt. Returns the hash as a str.

    Used by the dashboard's user-creation flow and password-reset.
    """
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plaintext: str, password_hash: str | None) -> bool:
    """Constant-time check. Returns False on a missing hash rather than raising."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


async def get_by_id(user_id: UUID) -> UserModel | None:
    async with get_session() as session:
        return await session.get(UserModel, user_id)


async def get_by_phone(phone_number: str) -> UserModel | None:
    async with get_session() as session:
        stmt = select(UserModel).where(UserModel.phone_number == phone_number)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_by_email(email: str) -> UserModel | None:
    async with get_session() as session:
        stmt = select(UserModel).where(col(UserModel.email) == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_or_create_by_phone(phone_number: str) -> UserModel:
    """Return the user with this phone, creating a bare row if missing.

    Used by the WhatsApp adapter on every inbound message: the bot learns
    about a new sender by writing a stub `users` row, then onboarding fills
    in display_name and preferred_language later.
    """
    async with get_session() as session:
        stmt = select(UserModel).where(UserModel.phone_number == phone_number)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        new_user = UserModel(
            phone_number=phone_number,
            onboarded=False,
        )
        session.add(new_user)
        await session.flush()
        await session.refresh(new_user)
        return new_user


async def create_with_email(
    *,
    email: str,
    password: str,
    role: ReviewerRoleLiteral,
    display_name: str | None = None,
) -> UserModel:
    """Create a dashboard-reviewer row (email + bcrypt hash + role).

    `phone_number` is left NULL — dashboard users are identified by email.
    """
    async with get_session() as session:
        new_user = UserModel(
            email=email,
            password_hash=hash_password(password),
            role=role,
            display_name=display_name,
        )
        session.add(new_user)
        await session.flush()
        await session.refresh(new_user)
        return new_user


async def update(user_id: UUID, patch: UserUpdate) -> UserModel | None:
    async with get_session() as session:
        row = await session.get(UserModel, user_id)
        if row is None:
            return None
        data = patch.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(row, k, v)
        await session.flush()
        await session.refresh(row)
        return row


async def set_display_name(user_id: UUID, display_name: str) -> UserModel | None:
    return await update(user_id, UserUpdate(display_name=display_name))


async def set_preferred_language(
    user_id: UUID, preferred_language: str
) -> UserModel | None:
    return await update(user_id, UserUpdate(preferred_language=preferred_language))


async def mark_onboarded(user_id: UUID) -> UserModel | None:
    return await update(user_id, UserUpdate(onboarded=True))


async def set_password(user_id: UUID, new_password: str) -> UserModel | None:
    """Admin-style password reset. Hashes before persisting."""
    return await update(user_id, UserUpdate(password_hash=hash_password(new_password)))


async def touch_last_login(user_id: UUID) -> None:
    """Update `last_login_at` to now(). Side-effect only — no return."""
    from datetime import datetime, timezone
    await update(user_id, UserUpdate(last_login_at=datetime.now(timezone.utc)))


async def list_for_role(role: ReviewerRoleLiteral, *, limit: int = 100) -> list[UserModel]:
    """Admin view: list dashboard users of one role (e.g. all volunteers)."""
    async with get_session() as session:
        stmt = (
            select(UserModel)
            .where(col(UserModel.role) == role)
            .order_by(col(UserModel.created_at).desc())
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "get_by_id",
    "get_by_phone",
    "get_by_email",
    "get_or_create_by_phone",
    "create_with_email",
    "update",
    "set_display_name",
    "set_preferred_language",
    "mark_onboarded",
    "set_password",
    "touch_last_login",
    "list_for_role",
    "hash_password",
    "verify_password",
]