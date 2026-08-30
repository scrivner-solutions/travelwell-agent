"""Filling the `places` cache from a provider.

The cache is not an optimisation bolted on later: `Place`'s own docstring says
the provider stays authoritative and rows age out by TTL. Explore reads only
this table, so a slow or missing provider degrades the map to what we already
knew rather than breaking it.

Kept out of the request path on purpose. A read-through cache that filled on a
miss would make the first pan over a new neighbourhood wait on Google and bill
for it; filling is a job someone triggers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Place
from app.services.places.ports import NearbyQuery, PlacesProvider, ProviderPlace

# How long a cached venue is trusted. Hours and prices move slowly; a stale
# row is a worse failure than a missing one only if nobody ever refreshes it.
DEFAULT_TTL = timedelta(days=14)


def is_stale(place: Place, ttl: timedelta = DEFAULT_TTL, now: datetime | None = None) -> bool:
    fetched = place.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - fetched > ttl


def _row(place: ProviderPlace) -> dict:
    return {
        "provider_ref": place.provider_ref,
        "kind": place.kind,
        "name": place.name,
        "summary": place.summary,
        "address": place.address,
        "lat": place.lat,
        "lng": place.lng,
        "price_level": place.price_level,
        "day_pass_cents": place.day_pass_cents,
        "amenities": list(place.amenities),
        "hours": place.hours,
        "photo_url": place.photo_url,
        "fetched_at": datetime.now(UTC),
    }


async def upsert_places(
    session: AsyncSession, found: list[ProviderPlace]
) -> list[Place]:
    """Write provider results into the cache, keyed on `provider_ref`.

    Amenities are overwritten rather than merged. The provider is authoritative
    by design, and a merge would make a venue accumulate amenities it no longer
    has, which is exactly the kind of quiet wrongness a cache should not add.
    """
    if not found:
        return []

    rows = [_row(p) for p in found]
    stmt = insert(Place).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Place.provider_ref],
        set_={
            column: stmt.excluded[column]
            for column in (
                "kind", "name", "summary", "address", "lat", "lng",
                "price_level", "day_pass_cents", "amenities", "hours",
                "photo_url", "fetched_at",
            )
        },
    )
    await session.execute(stmt)
    await session.flush()

    refs = [p.provider_ref for p in found]
    return list(
        (await session.execute(select(Place).where(Place.provider_ref.in_(refs))))
        .scalars()
        .all()
    )


async def refresh_area(
    session: AsyncSession, provider: PlacesProvider, query: NearbyQuery
) -> list[Place]:
    """Ask the provider about one area and write what comes back.

    A ProviderError is deliberately not caught: the caller decides whether an
    outage is worth retrying, and swallowing it here would leave an empty cache
    looking like an empty neighbourhood.
    """
    return await upsert_places(session, await provider.search_nearby(query))
