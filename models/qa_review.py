"""qa_reviews model — the approval queue.

Created one-per-domain-turn by `services/knowledge/enqueue.py`. The
dashboard reads `list_pending(...)`; volunteers add `local_input`; experts
add `expert_input` and either approve (which triggers
`services/knowledge/ingest.py`) or reject.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import CheckConstraint, String, text
from sqlmodel import Field, SQLModel

from models.enums import QAReviewStatus, QAReviewStatusLiteral, pg_enum
from models.memory import MemoryDomain, MemoryDomainLiteral


def _sa_str_col() -> Any:
    """Helper: SQLAlchemy String(16) so SQLModel doesn't introspect a Literal."""
    return String(length=16)


class QAReviewBase(SQLModel):
    """Fields shared by QAReviewModel and the Create variant."""

    model_config = ConfigDict(from_attributes=True)

    # Native `domain` enum (shared type); status stays VARCHAR + CHECK.
    domain: MemoryDomain = Field(sa_type=pg_enum(MemoryDomain, "domain_enum"), index=True)
    user_question: str = Field(description="The bot's incoming WhatsApp message")
    bot_answer: str = Field(description="The domain agent's reply")
    source_message_id: UUID | None = Field(
        default=None,
        foreign_key="messages.id",
        index=True,
        ondelete="SET NULL",
    )
    local_input: str | None = Field(default=None)
    local_volunteer_id: UUID | None = Field(
        default=None,
        foreign_key="local_volunteers.id",
        ondelete="SET NULL",
    )
    expert_input: str | None = Field(default=None)
    expert_id: UUID | None = Field(
        default=None,
        foreign_key="domain_experts.id",
        ondelete="SET NULL",
    )
    status: QAReviewStatus = Field(
        default=QAReviewStatus.PENDING,
        sa_type=_sa_str_col(),
        index=True,
        description="pending | approved | rejected",
    )
    # Set by ingest.py after writing one or more `documents` rows. Carries
    # the last chunk's id; `crud/document.list_for_qa_review(qa_review_id)`
    # enumerates them. Nullable: pending reviews don't have documents yet.
    documents_chunk_id: UUID | None = Field(default=None)


class QAReviewModel(QAReviewBase, table=True):
    """ORM table for `qa_reviews`."""

    __tablename__ = "qa_reviews"
    __table_args__ = (
        # `domain` is a native enum; only `status` needs a CHECK.
        CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="qa_reviews_status_check",
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


class QAReviewCreate(SQLModel):
    """Fields the auto-enqueue node sets; everything else starts NULL/default."""

    model_config = ConfigDict(from_attributes=True)

    domain: MemoryDomainLiteral
    user_question: str
    bot_answer: str
    source_message_id: UUID | None = None


class QAReviewUpdate(SQLModel):
    """Mutable subset — volunteer/expert actions go through this."""

    model_config = ConfigDict(from_attributes=True)

    local_input: str | None = None
    local_volunteer_id: UUID | None = None
    expert_input: str | None = None
    expert_id: UUID | None = None
    status: QAReviewStatusLiteral | None = None
    documents_chunk_id: UUID | None = None


__all__ = ["QAReviewModel", "QAReviewCreate", "QAReviewUpdate"]