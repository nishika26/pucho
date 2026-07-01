"""Knowledge-base ingest pipeline.

`ingest_qa_review(review_id, expert_id)` runs when the dashboard's
Approve button is clicked. It:

1. Loads the qa_review (status='pending', with bot_answer and expert_input).
2. Concatenates bot_answer + expert_input into a single "approved" text.
3. Chunks the text via LangChain's RecursiveCharacterTextSplitter
   (1000/200 — same shape `scripts/seed_documents.py` will reuse).
4. Embeds each chunk via OpenAI text-embedding-3-small (1536 dims).
5. Writes one `documents` row per chunk with source='expert_approved',
   qa_review_id=review_id.
6. Marks the qa_review as approved with the last chunk's id.

Errors during chunking/embedding leave the qa_review row untouched
(remains 'pending'). The dashboard surfaces the error to the expert.

OpenAI clients are constructed lazily so this module imports cleanly
without OPENAI_API_KEY (the dashboard's login page doesn't need it).
"""

from __future__ import annotations

import logging
from uuid import UUID

import crud.document as crud_document
import crud.qa_review as crud_qa_review
from models.document import DocumentCreate
from models.enums import DocumentSource
from models.memory import MemoryDomainLiteral

log = logging.getLogger(__name__)

# Same constants both this pipeline AND `scripts/seed_documents.py` will use.
# Keep these in sync if you change them.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
EMBED_MODEL = "text-embedding-3-small"  # 1536 dims


def _splitter():
    # Lazy import — avoids pulling in langchain_text_splitters at module load.
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def _embeddings():
    # Lazy import — keeps this module importable without OPENAI_API_KEY.
    from langchain_openai import OpenAIEmbeddings

    from config.settings import settings

    return OpenAIEmbeddings(model=EMBED_MODEL, api_key=settings.OPENAI_API_KEY)


async def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed N texts in one OpenAI call (the SDK handles batching internally)."""
    emb = _embeddings()
    # aembed_documents accepts a list[str] and returns list[list[float]].
    return await emb.aembed_documents(texts)


async def ingest_qa_review(review_id: UUID, expert_id: UUID) -> UUID | None:
    """Approve a qa_review and ingest its content. Returns the last chunk's id.

    Returns None if the review is missing or already terminal (approved/
    rejected). Embedding failures raise so the dashboard can surface them.
    """
    review = await crud_qa_review.get_by_id(review_id)
    if review is None:
        return None
    if review.status != "pending":
        # Idempotent: already approved/rejected — nothing to do.
        return review.documents_chunk_id

    domain: MemoryDomainLiteral = review.domain  # type: ignore[assignment]

    # Ingest ONLY when the expert actually contributed new content. If they
    # accepted the bot's answer as-is (no expert_input), there is nothing new
    # to add to the knowledge base — mark approved and write no documents.
    expert_input = (review.expert_input or "").strip()
    if not expert_input:
        log.info(
            "qa_review %s approved with no expert content; nothing ingested",
            review_id,
        )
        await crud_qa_review.mark_approved(review_id, expert_id, None)
        return None

    # The new knowledge unit: the bot's answer enriched with the expert's note.
    text = f"{review.bot_answer.strip()}\n\nExpert enrichment:\n{expert_input}".strip()

    chunks = _splitter().split_text(text)
    if not chunks:
        await crud_qa_review.mark_approved(review_id, expert_id, None)
        return None

    embeddings = await _embed_batch(chunks)
    last_chunk_id: UUID | None = None
    title = f"qa_review:{review_id} ({domain}, chunk of {len(chunks)})"

    for i, (chunk_text, vec) in enumerate(zip(chunks, embeddings)):
        payload = DocumentCreate(
            domain=domain,
            source=DocumentSource.EXPERT_APPROVED,
            qa_review_id=review_id,
            title=title,
            content=chunk_text,
            embedding=vec,
            metadata_={
                "chunk_index": i,
                "chunk_count": len(chunks),
                "domain": domain,
                "approved_by": str(expert_id),
            },
        )
        row = await crud_document.create(payload)
        last_chunk_id = row.id

    await crud_qa_review.mark_approved(review_id, expert_id, last_chunk_id)
    log.info(
        "qa_review %s ingested %d chunks for domain=%s",
        review_id,
        len(chunks),
        domain,
    )
    return last_chunk_id


async def reject_qa_review(review_id: UUID, expert_id: UUID) -> bool:
    """Mark a qa_review as rejected. Returns True if status changed."""
    review = await crud_qa_review.get_by_id(review_id)
    if review is None or review.status != "pending":
        return False
    await crud_qa_review.mark_rejected(review_id, expert_id)
    return True


__all__ = ["ingest_qa_review", "reject_qa_review", "CHUNK_SIZE", "CHUNK_OVERLAP", "EMBED_MODEL"]
