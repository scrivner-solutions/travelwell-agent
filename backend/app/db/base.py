"""Declarative base for all SQLAlchemy models.

No custom naming convention: docs/schema.sql (and therefore the live database)
uses Postgres default constraint names, and matching them keeps `alembic check`
quiet. The type_annotation_map pins plain annotations to the exact Postgres
types the DDL uses (text, timestamptz, uuid) so type comparison stays clean.
"""

import uuid
from datetime import datetime
from typing import Any, ClassVar

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        str: sa.Text(),
        datetime: sa.DateTime(timezone=True),
        uuid.UUID: pg.UUID(as_uuid=True),
    }
