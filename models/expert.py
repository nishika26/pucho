"""Domain-expert model.

An expert is a dashboard user with `users.role='expert'` plus one
`domain_experts` row per domain they're qualified to review (one row per
`(user_id, domain)` — UNIQUE constraint at the DB level).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import CheckConstraint, String, text
from sqlmodel import Field, SQLModel

from models.memory import MemoryDomainLiteral


def _sa_str_col() -> Any:
    """Helper: SQLAlchemy String(16) so SQLModel doesn't introspect a Literal."""
    return String(length=16)


class DomainExpertBase(SQLModel):
    """Fields shared by DomainExpertModel and DomainExpertCreate."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID = Field(
        foreign_key="users.id",
        index=True,
        ondelete="CASCADE",
        description="FK to the login user row (with role='expert')",
    )
    domain: MemoryDomainLiteral = Field(
        sa_type=_sa_str_col(),
        description="legal | medical | financial",
    )
    display_name: str = Field(max_length=128)
    active: bool = Field(default=True)


class DomainExpertModel(DomainExpertBase, table=True):
    """ORM table for `domain_experts`."""

    __tablename__ = "domain_experts"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('legal','medical','financial')",
            name="domain_experts_domain_check",
        ),
    )

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


class DomainExpertCreate(DomainExpertBase):
    """Fields the app sets when registering an expert for a domain."""


__all__ = ["DomainExpertModel", "DomainExpertCreate"]