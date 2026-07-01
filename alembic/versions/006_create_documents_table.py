"""create documents table (pgvector knowledge base)

Revision ID: 0006_create_documents_table
Revises: 0005_create_qa_reviews_table
Create Date: 2026-06-30

The shared RAG knowledge base. Two write paths converge here:
- Static manual docs (scripts/seed_documents.py) -> source='manual'
- Expert-approved Q&As from qa_reviews -> source='expert_approved'

Reads go through services/knowledge/retriever_impl.py (cosine distance).
Requires the `vector` extension (pgvector).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "domain",
            postgresql.ENUM(
                "legal", "healthcare", "financial",
                name="domain_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "qa_review_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("qa_reviews.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=1536), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "source IN ('manual','expert_approved')",
            name="documents_source_check",
        ),
    )
    op.create_index("ix_documents_domain", "documents", ["domain"])
    op.create_index("ix_documents_source", "documents", ["source"])
    op.create_index("ix_documents_qa_review_id", "documents", ["qa_review_id"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_documents_embedding_hnsw "
        "ON documents USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documents_embedding_hnsw")
    op.drop_index("ix_documents_qa_review_id", table_name="documents")
    op.drop_index("ix_documents_source", table_name="documents")
    op.drop_index("ix_documents_domain", table_name="documents")
    op.drop_table("documents")
