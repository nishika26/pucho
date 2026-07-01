"""WhatsApp-user model.

`whatsapp_users` is the bot's end-user identity table — one row per WhatsApp
sender. A bare row is created on first inbound message (keyed by
`whatsapp_number`); `name` and `locality` are filled during onboarding.
Reply language is auto-detected per message (Sarvam STT for voice; the LLM
mirrors the question's language for text), so it isn't stored here.

`messages.user_id` and `user_memories.user_id` reference this table. Dashboard
reviewers live in a separate `dashboard_users` table.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import text
from sqlmodel import Field, SQLModel

from models.enums import LiteracyLevel, pg_enum


class WhatsAppUserBase(SQLModel):
    """Fields shared by WhatsAppUserModel and the Create/Update variants."""

    model_config = ConfigDict(from_attributes=True)

    whatsapp_number: str = Field(
        unique=True,
        index=True,
        max_length=32,
        description="E.164 WhatsApp number (without the 'whatsapp:' prefix)",
    )
    name: str | None = Field(default=None, max_length=128)
    locality: str | None = Field(
        default=None,
        max_length=128,
        description="Free-text location (village / town / district) from onboarding",
    )
    literacy_level: LiteracyLevel | None = Field(
        default=None,
        sa_type=pg_enum(LiteracyLevel, "literacy_level"),
        description="Running read/write-comfort profile; refined per message",
    )
    onboarded: bool = Field(default=False)


class WhatsAppUserModel(WhatsAppUserBase, table=True):
    """ORM table for `whatsapp_users`."""

    __tablename__ = "whatsapp_users"

    id: UUID = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    created_at: datetime = Field(
        default=None, sa_column_kwargs={"server_default": text("now()")}
    )
    updated_at: datetime = Field(
        default=None,
        sa_column_kwargs={
            "server_default": text("now()"),
            "onupdate": text("now()"),
        },
    )


class WhatsAppUserCreate(WhatsAppUserBase):
    """Fields the adapter sets when registering a new WhatsApp sender."""


class WhatsAppUserUpdate(SQLModel):
    """Mutable subset — onboarding fills these in over time."""

    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    locality: str | None = None
    literacy_level: LiteracyLevel | None = None
    onboarded: bool | None = None


__all__ = [
    "WhatsAppUserModel",
    "WhatsAppUserCreate",
    "WhatsAppUserUpdate",
]
