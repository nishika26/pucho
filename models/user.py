"""User model.

`users` is the umbrella identity table. Two distinct populations share it:

1. **WhatsApp senders** (the bot's users): identified by `phone_number`,
   `role` is NULL, `password_hash` is NULL, `email` is NULL.
2. **Dashboard reviewers** (volunteers / experts / admins): identified by
   `email` + `password_hash`, `role` is one of 'volunteer'/'expert'/'admin'.
   `phone_number` is NULL.

A single user *could* in principle be both, but in practice the two
populations don't overlap — a WhatsApp sender doesn't usually log in to the
dashboard, and a dashboard reviewer isn't usually a WhatsApp sender.

`display_name` + `preferred_language` are filled during onboarding for the
bot population; set manually by an admin for dashboard users.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import String, text
from sqlmodel import Field, SQLModel

from models.enums import ReviewerRoleLiteral


def _sa_str_col() -> Any:
    """Helper: SQLAlchemy String(16) so SQLModel doesn't introspect a Literal."""
    return String(length=16)


class UserBase(SQLModel):
    """Fields shared by UserModel (table) and UserCreate/UserUpdate."""

    model_config = ConfigDict(from_attributes=True)

    phone_number: str | None = Field(
        default=None,
        unique=True,
        index=True,
        description="E.164 for WhatsApp senders; NULL for dashboard-only users",
        max_length=32,
    )
    display_name: str | None = Field(default=None, max_length=128)
    preferred_language: str | None = Field(
        default=None,
        description="BCP-47 code from onboarding, e.g. 'en-IN' or 'hi-IN'",
        max_length=16,
    )
    onboarded: bool = Field(default=False)
    # Dashboard-auth fields. All nullable so existing WhatsApp rows validate.
    email: str | None = Field(
        default=None,
        unique=True,
        index=True,
        description="Login identity for dashboard reviewers; NULL for bot users",
        max_length=255,
    )
    password_hash: str | None = Field(
        default=None,
        description="bcrypt hash; never logged or returned over the API",
        max_length=255,
    )
    role: ReviewerRoleLiteral | None = Field(
        default=None,
        sa_type=_sa_str_col(),
        description="volunteer | expert | admin | NULL (WhatsApp sender)",
    )
    last_login_at: datetime | None = Field(default=None)


class UserModel(UserBase, table=True):
    """ORM table for `users`."""

    __tablename__ = "users"

    id: UUID = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    created_at: datetime = Field(
        default=None,
        sa_column_kwargs={"server_default": text("now()")},
    )
    updated_at: datetime = Field(
        default=None,
        sa_column_kwargs={
            "server_default": text("now()"),
            "onupdate": text("now()"),
        },
    )


class UserCreate(UserBase):
    """Fields the app sets when inserting a new user row."""


class UserUpdate(SQLModel):
    """Mutable subset — every field optional for partial updates."""

    model_config = ConfigDict(from_attributes=True)

    display_name: str | None = None
    preferred_language: str | None = None
    onboarded: bool | None = None
    email: str | None = None
    password_hash: str | None = None
    role: ReviewerRoleLiteral | None = None
    last_login_at: datetime | None = None


__all__ = ["UserModel", "UserCreate", "UserUpdate"]