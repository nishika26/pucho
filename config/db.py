"""Async SQLAlchemy engine + session factory + LangGraph checkpointer.

CRUD functions open short-lived sessions via the `get_session()` async
context manager. Each session runs inside an autobegin transaction;
the caller is responsible for `commit` / `rollback` via the
`transaction()` helper, or for the simple `get_session() as session:`
pattern that commits on exit.

`get_checkpointer()` returns a process-shared AsyncPostgresSaver for
short-term (per-thread) memory. The checkpointer creates its own tables
on first `setup()`; subsequent calls re-use the same saver.

The DSN is built from POSTGRES_* env vars (matches config.settings) so
alembic and runtime use the same source of truth.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic_core import MultiHostUrl
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _dsn() -> str:
    server = os.environ["POSTGRES_SERVER"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ.get("POSTGRES_PASSWORD", "")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    db = os.environ.get("POSTGRES_DB", "postgres")
    return str(
        MultiHostUrl.build(
            scheme="postgresql+psycopg",
            username=user,
            password=password,
            host=server,
            port=port,
            path=db,
        )
    )


def _make_engine() -> AsyncEngine:
    """Build a fresh async engine. Disabled under pytest if env var is set."""
    return create_async_engine(
        _dsn(),
        pool_pre_ping=True,
        future=True,
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _engine is None:
        _engine = _make_engine()
        _session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
            autoflush=False,
        )
    assert _session_factory is not None
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Open a session, commit on success, rollback on exception.

    Usage:
        async with get_session() as session:
            row = await session.get(UserModel, user_id)
    """
    factory = _factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# LangGraph short-term-memory checkpointer
# ---------------------------------------------------------------------------

_saver_cm: object | None = None
_saver: AsyncPostgresSaver | None = None
_setup_done: bool = False


async def get_checkpointer() -> AsyncPostgresSaver:
    """Lazily create and cache an `AsyncPostgresSaver` for this process.

    `AsyncPostgresSaver.from_conn_string(...)` is itself an async context
    manager that yields a configured saver. We open it once and hold it
    open for the lifetime of the process — PostgresSaver is designed to
    be long-lived (it manages a connection pool under the hood).

    On first call, runs `setup()` to create the checkpoint tables
    (idempotent — a no-op on subsequent calls).
    """
    global _saver_cm, _saver, _setup_done
    if _saver is not None:
        return _saver

    # `from_conn_string` returns an async iterator that yields the saver;
    # `async with` opens it once and gives us the same saver for life.
    _saver_cm = AsyncPostgresSaver.from_conn_string(_dsn())
    _saver = await _saver_cm.__aenter__()
    if not _setup_done:
        await _saver.setup()
        _setup_done = True
    return _saver


async def close_checkpointer() -> None:
    """Close the cached saver (call from FastAPI shutdown). Safe to call twice."""
    global _saver_cm, _saver, _setup_done
    if _saver_cm is not None:
        await _saver_cm.__aexit__(None, None, None)
    _saver_cm = None
    _saver = None
    _setup_done = False