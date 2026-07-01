"""Seed static RAG documents from rag_corpus/ into the `documents` table.

Stream 1 of the knowledge base (source='manual'): walks rag_corpus/<domain>/*.md,
chunks + embeds each file with the SAME splitter/embedder the expert-approval
ingest uses, and writes one `documents` row per chunk.

Usage:
    uv run python scripts/seed_documents.py            # ingest (needs DB + OPENAI_API_KEY)
    uv run python scripts/seed_documents.py --dry-run   # just chunk + count, no DB/OpenAI

Idempotent: a real run first deletes existing source='manual' rows so re-seeding
doesn't duplicate. Expert-approved rows are never touched.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make the repo root importable when run as a plain script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

CORPUS_DIR = _REPO_ROOT / "rag_corpus"
VALID_DOMAINS = {"legal", "healthcare", "financial"}


def _domain_for(dir_name: str) -> str | None:
    """Map a corpus subfolder name to a domain (tolerates stray whitespace/case)."""
    normalised = dir_name.strip().lower()
    return normalised if normalised in VALID_DOMAINS else None


def _iter_corpus() -> list[tuple[str, Path]]:
    """Return (domain, markdown_path) pairs for every ingestable file."""
    pairs: list[tuple[str, Path]] = []
    for sub in sorted(CORPUS_DIR.iterdir()):
        if not sub.is_dir():
            continue
        domain = _domain_for(sub.name)
        if domain is None:
            print(f"  ! skipping '{sub.name}/' — not a known domain")
            continue
        for md in sorted(sub.glob("*.md")):
            pairs.append((domain, md))
    return pairs


async def _clear_manual() -> None:
    from sqlalchemy import text

    from config.db import get_session

    async with get_session() as session:
        await session.execute(text("DELETE FROM documents WHERE source = 'manual'"))


async def seed(dry_run: bool = False) -> None:
    from services.knowledge.ingest import CHUNK_OVERLAP, CHUNK_SIZE, _splitter

    splitter = _splitter()
    pairs = _iter_corpus()
    if not pairs:
        print("No corpus files found under", CORPUS_DIR)
        return

    print(
        f"{'DRY RUN — ' if dry_run else ''}seeding {len(pairs)} files "
        f"(chunk {CHUNK_SIZE}/{CHUNK_OVERLAP})\n"
    )

    if not dry_run:
        print("Clearing existing source='manual' rows…")
        await _clear_manual()

    # Imports needed only for a real run.
    if not dry_run:
        import crud.document as crud_document
        from models.document import DocumentCreate
        from models.enums import DocumentSource
        from services.knowledge.ingest import _embed_batch

    total_chunks = 0
    per_domain: dict[str, int] = {}
    for domain, md in pairs:
        content = md.read_text(encoding="utf-8").strip()
        if not content:
            print(f"  [{domain}] {md.name}: empty, skipped")
            continue
        chunks = splitter.split_text(content)
        if not chunks:
            continue

        if not dry_run:
            embeddings = await _embed_batch(chunks)
            for i, (chunk_text, vec) in enumerate(zip(chunks, embeddings)):
                await crud_document.create(
                    DocumentCreate(
                        domain=domain,
                        source=DocumentSource.MANUAL,
                        title=md.stem,
                        content=chunk_text,
                        embedding=vec,
                        metadata_={
                            "source_file": f"{md.parent.name}/{md.name}",
                            "chunk_index": i,
                            "chunk_count": len(chunks),
                        },
                    )
                )

        total_chunks += len(chunks)
        per_domain[domain] = per_domain.get(domain, 0) + len(chunks)
        print(f"  [{domain}] {md.name}: {len(chunks)} chunks")

    print("\nPer-domain chunk totals:")
    for d in sorted(per_domain):
        print(f"  {d:12} {per_domain[d]}")
    verb = "would ingest" if dry_run else "ingested"
    print(f"\nDone. {verb} {total_chunks} chunks from {len(pairs)} files.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed rag_corpus into documents.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk + count only; no OpenAI embedding and no DB writes.",
    )
    args = parser.parse_args()
    asyncio.run(seed(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
