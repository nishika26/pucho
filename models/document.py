"""documents model — the RAG knowledge base (single table per the senior-engineer doc).

Two write paths converge here:
- `source='manual'` from `scripts/seed_documents.py` (deferred; uses the same
  `embed()` helper as the ingest pipeline).
- `source='expert_approved'` from `services/knowledge/ingest.py` (the dashboard's
  Approve button).

Reads go through `services/knowledge/retriever_impl.py`, which queries by
embedding <=> (cosine distance). v1 is pgvector-only; a future migration
adds a tsvector column + GIN index for hybrid search.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from pydantic import ConfigDict
from sqlalchemy import CheckConstraint, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from models.enums import DocumentSourceLiteral, pg_enum
from models.memory import MemoryDomain, MemoryDomainLiteral


def _sa_str_col(length: int = 16) -> Any:
    """Helper: SQLAlchemy String so SQLModel doesn't introspect a Literal."""
    return String(length=length)


class DocumentBase(SQLModel):
    """Fields shared by DocumentModel and DocumentCreate."""

    model_config = ConfigDict(from_attributes=True)

    domain: MemoryDomain = Field(sa_type=pg_enum(MemoryDomain, "domain_enum"), index=True)
    source: DocumentSourceLiteral = Field(sa_type=_sa_str_col(32), index=True)
    qa_review_id: UUID | None = Field(
        default=None,
        foreign_key="qa_reviews.id",
        ondelete="SET NULL",
        description="Provenance for source='expert_approved' rows",
    )
    title: str = Field(max_length=256)
    content: str = Field(description="The chunk text")
    embedding: list[float] | None = Field(
        default=None,
        sa_type=Vector(dim=1536),
        description="OpenAI text-embedding-3-small (1536 dims)",
    )
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"name": "metadata"},
        description="JSONB; arbitrary provenance / chunking info",
    )


class DocumentModel(DocumentBase, table=True):
    """ORM table for `documents`."""

    __tablename__ = "documents"
    __table_args__ = (
        # `domain` is a native enum; only `source` needs a CHECK.
        CheckConstraint(
            "source IN ('manual','expert_approved')",
            name="documents_source_check",
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


class DocumentCreate(SQLModel):
    """Fields the ingest pipeline sets per chunk."""

    model_config = ConfigDict(from_attributes=True)

    domain: MemoryDomainLiteral
    source: DocumentSourceLiteral
    qa_review_id: UUID | None = None
    title: str
    content: str
    embedding: list[float] | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"name": "metadata"},
    )


__all__ = ["DocumentModel", "DocumentCreate"]