"""Declarative base for all SQLAlchemy models.

No custom naming convention: the live database carries Postgres default
constraint names, so the models spell those names out where they matter and
`alembic check` stays quiet. The type_annotation_map pins plain annotations to the exact Postgres
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
