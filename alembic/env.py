"""Alembic environment.

Resolves the DSN from `config.settings` (which loads `.env` and accepts either
`DATABASE_URL` or the discrete `POSTGRES_*` parts), so migrations and the app
always use the same database. Alembic runs a sync engine, so the psycopg (v3)
driver is forced in `_dsn()`.

Per the senior-engineer doc, Supabase's `auth`, `storage`, and `realtime`
schemas are excluded so alembic won't try to manage tables owned by
Supabase itself.

Run from the project root:
    alembic revision --autogenerate -m "describe the change"
    alembic upgrade head
    alembic downgrade -1
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

# Make the project root importable so alembic can reach `models` even when
# invoked from a subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Importing the package registers ALL table models with SQLModel.metadata.
# (Importing only a subset would make autogenerate emit DROPs for the rest.)
import models  # noqa: F401

config = context.config


def _dsn() -> str:
    """Resolve the migration DSN from the SAME source as the app.

    `config.settings` loads `.env` and resolves either `DATABASE_URL` or the
    discrete `POSTGRES_*` parts, so migrations and runtime never drift. Alembic
    runs a *sync* engine, so we force the psycopg (v3) driver.
    """
    from config.settings import settings

    url = settings.database_url
    if not url:
        raise RuntimeError(
            "No database configured. Set DATABASE_URL (or the POSTGRES_* vars) "
            "in your .env before running migrations."
        )
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg://" + url[len("postgresql+asyncpg://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    return url


config.set_main_option("sqlalchemy.url", _dsn())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Schemas that alembic should NOT manage. Per senior-engineer doc, these are
# Supabase-owned and out of our control.
_EXCLUDED_SCHEMAS = {"auth", "storage", "realtime"}


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (for review/dry-run)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=False,
        include_object=lambda obj, name, type_, reflected, compare_to: (
            getattr(obj, "schema", None) not in _EXCLUDED_SCHEMAS
        ),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=False,
            include_object=lambda obj, name, type_, reflected, compare_to: (
                getattr(obj, "schema", None) not in _EXCLUDED_SCHEMAS
            ),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
