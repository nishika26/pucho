"""Domain-expert model.

An expert is a dashboard user with `users.role='expert'` plus one
`domain_experts` row per domain they're qualified to review (one row per
`(user_id, domain)` — UNIQUE constraint at the DB level).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import text
from sqlmodel import Field, SQLModel

from models.enums import EducationLevel, WorkStatus, pg_enum
from models.memory import MemoryDomain


class DomainExpertBase(SQLModel):
    """Fields shared by DomainExpertModel and DomainExpertCreate."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID = Field(
        foreign_key="dashboard_users.id",
        index=True,
        ondelete="CASCADE",
        description="FK to the dashboard_users row (role='expert')",
    )
    domain: MemoryDomain = Field(
        sa_type=pg_enum(MemoryDomain, "domain_enum"),
        description="legal | healthcare | financial",
    )
    name: str = Field(max_length=128)
    highest_education: EducationLevel = Field(
        sa_type=pg_enum(EducationLevel, "education_level"),
        description="high_school | diploma | bachelors | masters | doctorate",
    )
    work_status: WorkStatus = Field(
        sa_type=pg_enum(WorkStatus, "work_status"),
        description="working | student",
    )
    verified: bool = Field(
        default=False,
        description="Admin-verified credential check before the expert can approve",
    )
    active: bool = Field(default=True)


class DomainExpertModel(DomainExpertBase, table=True):
    """ORM table for `domain_experts`."""

    __tablename__ = "domain_experts"
    # `domain` is a native enum, so no CHECK constraint is needed.

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