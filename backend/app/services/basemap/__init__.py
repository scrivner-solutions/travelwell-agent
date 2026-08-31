"""Cached street geometry for the Explore map.

Deliberately not part of `app.services.places`, which is the seam for venue
providers. The two look similar -- both cache an area, both have a fetch gate
-- but `places.policy` exists entirely to bound *spend*, and applying its
reasoning to a free provider would import a ceiling that is not there. What
bounds this one is politeness to a donated server, which is a different rule
with a different number.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BasemapArea

from . import overpass
from .geometry import (
    ATTRIBUTION,
    EMPTY,
    Area,
    Basemap,
    bucket_radius,
    fetch_enabled,
    normalize,
    ttl,
)
from .overpass import BasemapUnavailable

__all__ = [
    "ATTRIBUTION",
    "EMPTY",
    "Area",
    "Basemap",
    "BasemapUnavailable",
    "basemap_for",
    "bucket_radius",
    "fetch_enabled",
    "normalize",
]

_LAYERS = ("roads_major", "roads_minor", "water", "parks", "buildings")


def _to_basemap(row: BasemapArea) -> Basemap:
    return Basemap(**{layer: getattr(row, layer) for layer in _LAYERS})


async def _cached(session: AsyncSession, area: Area) -> BasemapArea | None:
    result = await session.execute(
        select(BasemapArea).where(BasemapArea.area_key == area.key)
    )
    return result.scalar_one_or_none()


async def _store(session: AsyncSession, area: Area, drawn: Basemap) -> None:
    now = datetime.now(UTC)
    values = {layer: getattr(drawn, layer) for layer in _LAYERS}
    stmt = insert(BasemapArea).values(area_key=area.key, fetched_at=now, **values)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[BasemapArea.area_key],
            set_={**{layer: stmt.excluded[layer] for layer in _LAYERS},
                  "fetched_at": stmt.excluded.fetched_at},
        )
    )
    # Committed here rather than left to the caller because the only caller is
    # a GET: nothing else in that request has anything to commit, and a cache
    # fill that is rolled back with the response refetches forever.
    await session.commit()


async def basemap_for(
    session: AsyncSession, lat: float, lng: float, radius_m: float
) -> Basemap:
    """Geometry for the area around a point, from cache where possible.

    Never raises. The basemap is an enrichment: an unreachable provider must
    leave Explore rendering on plain ground, not failing. That is also why a
    stale row beats an empty one on error -- streets did not move because a
    donated server timed out.
    """
    area = normalize(lat, lng, radius_m)
    row = await _cached(session, area)
    if row is not None and datetime.now(UTC) - row.fetched_at < ttl():
        return _to_basemap(row)
    if not fetch_enabled():
        return _to_basemap(row) if row is not None else EMPTY
    try:
        drawn = await overpass.fetch(area)
    except BasemapUnavailable:
        return _to_basemap(row) if row is not None else EMPTY
    await _store(session, area, drawn)
    return drawn
