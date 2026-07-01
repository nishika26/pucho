"""User-memory models.

`user_memories` is the long-term-memory table. Each row is one structured
fact about a user, scoped by `(user_id, domain, key)`. The reflect node in
`services/memory/reflect.py` calls `crud.memory.upsert(...)` against this
table; the domain-agent `run()` reads via `crud.memory.list_for_user_domain`.

The `FactsToMemorize` Pydantic schema is the structured-output shape the
reflect node uses; it's intentionally separate from `UserMemoryModel` so we
can evolve the LLM extraction schema without touching the table shape.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field as SQLField, SQLModel

from models.enums import pg_enum


class MemoryDomain(StrEnum):
    LEGAL = "legal"
    healthcare = "healthcare"
    FINANCIAL = "financial"


MemoryDomainLiteral = Literal["legal", "healthcare", "financial"]


class UserMemoryBase(SQLModel):
    """Shared shape between UserMemoryModel and the Create/Update variants."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID = SQLField(
        foreign_key="whatsapp_users.id", index=True, ondelete="CASCADE"
    )
    # Native Postgres enum (`domain` type), shared with qa_reviews/documents/experts.
    domain: MemoryDomain = SQLField(sa_type=pg_enum(MemoryDomain, "domain_enum"), index=True)
    key: str = SQLField(max_length=128, description="Stable per (user, domain) — e.g. 'chronic_conditions'")
    value: Any = SQLField(sa_type=JSONB, description="JSONB — any JSON: dict, list, or scalar")
    confidence: float = SQLField(default=1.0, ge=0.0, le=1.0)
    source_message_id: UUID | None = SQLField(
        default=None,
        foreign_key="messages.id",
        ondelete="SET NULL",
        description="Provenance — which message did we learn this from",
    )


class UserMemoryModel(UserMemoryBase, table=True):
    """ORM table for `user_memories`."""

    __tablename__ = "user_memories"
    __table_args__ = (
        # `domain` is a native enum, so no CHECK needed for it.
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="user_memories_confidence_check",
        ),
    )

    id: UUID = SQLField(
        default=None,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    created_at: datetime = SQLField(
        default=None,
        sa_column_kwargs={"server_default": text("now()")},
    )
    updated_at: datetime = SQLField(
        default=None,
        sa_column_kwargs={
            "server_default": text("now()"),
            "onupdate": text("now()"),
        },
    )


class UserMemoryCreate(UserMemoryBase):
    """Fields the app sets when upserting a fact."""


class UserMemoryUpdate(SQLModel):
    """Mutable subset — only fields that change across re-saves."""

    model_config = ConfigDict(from_attributes=True)

    value: Any = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_message_id: UUID | None = None


# ---------------------------------------------------------------------------
# LLM-side structured-output schema (deliberately separate from the table)
# ---------------------------------------------------------------------------


class FactToMemorize(BaseModel):
    """One fact the reflect node proposes to write."""

    domain: MemoryDomainLiteral = Field(description="Which domain does this fact belong to?")
    key: str = Field(description="Stable snake_case identifier (see services/memory/vocab.py)")
    value: Any = Field(
        description="JSON-serialisable payload — scalars (str/int/bool), arrays, "
        "or objects. Use objects for structured records, arrays for lists."
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="1.0 if the user stated it; 0.7-0.9 if they mentioned it in passing",
    )


class FactsToMemorize(BaseModel):
    """The reflect node's structured-output response."""

    facts: list[FactToMemorize] = Field(
        default_factory=list,
        description="All facts worth persisting from this exchange; empty list if nothing new",
    )
