"""Alembic environment.

Runs psycopg3 in sync mode; the app runs the same driver asynchronously, so
DATABASE_URL is shared verbatim and app.db.engine owns the driver and the
per-target connect args.

Drift policy (ADR-001 point 5): models cover a subset of the schema while
vertical slices land, so autogenerate/check comparison is limited to the
tables present in Base.metadata. The include filters below shrink to a no-op
as model coverage grows.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.db import models  # noqa: F401  registers tables on Base.metadata
from app.db.base import Base
from app.db.engine import connect_args, database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    if type_ == "table":
        return name in target_metadata.tables
    return True


def include_object(obj, name, type_, reflected, compare_to):
    # A modeled table may hold an FK to a not-yet-modeled table (for example
    # trips.hotel_place_id -> places); keep the DB-side constraint out of the
    # comparison instead of proposing to drop it.
    if type_ == "foreign_key_constraint" and reflected:
        referred = obj.referred_table.name
        if referred not in target_metadata.tables:
            return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=database_url().render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        include_object=include_object,
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
            include_name=include_name,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
