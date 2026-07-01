"""Sync DB helpers for the Streamlit dashboard.

Streamlit's main loop is synchronous — we use a sync SQLAlchemy engine for
reads/writes the dashboard makes directly (login, list reviews, etc.).
Anything that calls into LangChain / OpenAI / AsyncPostgresSaver (the
`ingest_qa_review` ingest pipeline) is invoked via `asyncio.run()` in a
short-lived event loop because the dashboard's UI is sync.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlmodel import Session

_engine: Engine | None = None


def _dsn_sync() -> str:
    """Sync `postgresql://` DSN for SQLAlchemy.

    Uses the same source as the rest of the app: `config.settings.database_url`,
    which resolves either `DATABASE_URL` or the discrete `POSTGRES_*` parts. The
    dashboard engine is sync, so we strip any async driver suffix and fall back
    to the default (psycopg2) driver.
    """
    from config.settings import settings

    url = settings.database_url
    if not url:
        raise RuntimeError(
            "No database configured. Set DATABASE_URL (or the POSTGRES_* vars) "
            "in your .env before starting the dashboard."
        )
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def get_engine() -> Engine:
    """Lazy-init a sync engine. Re-uses across Streamlit reruns."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _dsn_sync(),
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
            future=True,
        )
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a SQLModel Session; commit on success, rollback on error."""
    engine = get_engine()
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def run_async(coro):
    """Run an async coroutine from sync Streamlit code.

    Streamlit reruns the script top-to-bottom on each interaction, so each
    page handler is fresh and can use `run_async` to dispatch into the
    async CRUD/ingest layer without managing a long-lived event loop.
    """
    return asyncio.run(coro)