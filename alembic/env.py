"""Alembic environment.

Reads the Postgres DSN from environment variables (`POSTGRES_*`) so the same
settings that drive the app also drive migrations. We deliberately do NOT
import `config.settings.Settings` here — its `_enforce_non_default_secrets`
validator would block `alembic upgrade head --sql` (offline mode) before the
run. The DSN vars (POSTGRES_SERVER/PORT/USER/PASSWORD/DB) are the canonical
source for both app and migrations.

Per the senior-engineer doc, Supabase's `auth`, `storage`, and `realtime`
schemas are excluded so alembic won't try to manage tables owned by
Supabase itself.

Run from the project root:
    alembic revision --autogenerate -m "describe the change"
    alembic upgrade head
    alembic downgrade -1
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

# Make the project root importable so alembic can reach `models` even when
# invoked from a subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from alembic import context
from pydantic_core import MultiHostUrl
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from models.message import MessageModel  # noqa: F401  (registers table)
from models.memory import UserMemoryModel  # noqa: F401
from models.user import UserModel  # noqa: F401

config = context.config


def _dsn() -> str:
    """Build the SQLAlchemy DSN from POSTGRES_* env vars (matches config.settings)."""
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
