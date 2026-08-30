"""Alembic environment.

Runs psycopg3 in sync mode; the app runs the same driver asynchronously, so
DATABASE_URL is shared verbatim and app.db.engine owns the driver and the
per-target connect args.

Drift policy (ADR-005): the models cover every table, so comparison is
unfiltered and `alembic check` sees the whole schema.
"""

from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

# Alembic has no application startup, so without this DATABASE_URL from
# backend/.env is ignored and every worktree migrates the default database.
# Must not override: the test suite sets DATABASE_URL to a *_test database it
# drops and recreates, then upgrades in-process through this file.
load_dotenv()

from app.db import models  # noqa: E402, F401  registers tables on Base.metadata
from app.db.base import Base  # noqa: E402
from app.db.engine import connect_args, database_url  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url().render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        database_url(),
        poolclass=pool.NullPool,
        connect_args=connect_args(),
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
