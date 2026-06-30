"""Message model.

`messages` is the audit trail for every inbound and outbound message. The
reflect node references `messages.id` via `user_memories.source_message_id`,
and the future short-term-memory layer (PostgresSaver migration) will read
from here rather than re-implementing chat history.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import text
from sqlmodel import Field, SQLModel


class MessageRole(StrEnum):
    HUMAN = "human"
    AI = "ai"


class MessageModality(StrEnum):
    TEXT = "text"
    VOICE = "voice"


class MessageBase(SQLModel):
    """Common shape for MessageModel (table) and MessageCreate."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    thread_id: str = Field(index=True, max_length=64)
    role: MessageRole
    modality: MessageModality
    content: str


class MessageModel(MessageBase, table=True):
    """ORM table for `messages`."""

    __tablename__ = "messages"

    id: UUID = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    created_at: datetime = Field(
        default=None,
        sa_column_kwargs={"server_default": text("now()")},
    )


class MessageCreate(MessageBase):
    """Fields the app sets when persisting a new message."""
