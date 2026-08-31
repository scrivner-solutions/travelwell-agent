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

import enum
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AreaFillOutcome, AreaFillRecord, Place, PlaceKind
from app.services.places import policy
from app.services.places.ports import (
    NearbyQuery,
    PlacesProvider,
    ProviderError,
    ProviderPlace,
    ProviderUnavailable,
)

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
        # None stays None: unknown is a value the column now holds.
        "amenities": None if place.amenities is None else list(place.amenities),
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

    A provider that reports no amenities field overwrites with NULL, not `{}`.
    Refreshing from a provider that cannot see amenities must not be able to
    convert a known list into a claim that the venue has none.
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


class FillSource(enum.StrEnum):
    """Why the area looks the way it does, from the caller's point of view."""

    fetched = "fetched"
    cache_fresh = "cache_fresh"
    policy_declined = "policy_declined"


@dataclass(frozen=True)
class AreaFill:
    """The answer to "do we actually know what is here?"

    `authoritative` is the field worth reading. It is False whenever the area's
    coverage rests on something other than a successful look at the provider,
    which is the distinction `runs.py` needs before it can say "N places nearby"
    honestly.

    It is per AREA. A consumer reading a radius that spans several areas has to
    combine several of these, and the combination is an AND: one unlooked-at
    area makes the whole answer non-authoritative.
    """

    area_key: str
    source: FillSource
    outcome: AreaFillOutcome | None
    result_count: int
    authoritative: bool


def outcome_for(exc: ProviderError) -> AreaFillOutcome:
    """The one place an exception becomes an outcome.

    Order matters and is the whole reason this is a function rather than a
    mapping written at each call site: `ProviderUnavailable` SUBCLASSES
    `ProviderError`, so testing the base class first would quietly record a
    missing credential as an outage and collapse three outcomes into two.
    """
    if isinstance(exc, ProviderUnavailable):
        return AreaFillOutcome.unavailable
    return AreaFillOutcome.error


def area_key(query: NearbyQuery) -> str:
    """The identity of an area, and the only thing allowed to build one.

    Coordinates round to ~1km so that two overlapping requests are one area.
    Kinds are part of the key: a fetch for gyms tells us nothing about whether
    anyone has looked for restaurants here, and treating it as if it did would
    make an unlooked-at area read as covered. A superset fetch deliberately does
    not satisfy a subset request -- that costs an occasional extra call and can
    never invent coverage we do not have.
    """
    kinds = tuple(query.kinds) or tuple(PlaceKind)
    names = ",".join(sorted(k.value for k in kinds))
    return f"{query.lat:.2f},{query.lng:.2f},{query.radius_m},{names}"


def _window(outcome: AreaFillOutcome, ttl: timedelta) -> timedelta | None:
    """How long an attempt with this outcome suppresses the next one.

    `unavailable` returns None, meaning it suppresses nothing. That is not an
    oversight: an unusable provider raises before any request leaves the
    process, so retrying costs no billed call, and a timer here would instead
    mean that fixing the credentials never took effect until someone deleted a
    database row.
    """
    if outcome is AreaFillOutcome.ok:
        return ttl
    if outcome is AreaFillOutcome.error:
        return policy.error_backoff()
    return None


async def _last_fill(session: AsyncSession, key: str) -> AreaFillRecord | None:
    return (
        await session.execute(
            select(AreaFillRecord).where(AreaFillRecord.area_key == key)
        )
    ).scalar_one_or_none()


def _covers(record: AreaFillRecord, ttl: timedelta, now: datetime) -> bool:
    window = _window(record.outcome, ttl)
    if window is None:
        return False
    fetched = record.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return now - fetched <= window


async def _record(
    session: AsyncSession,
    key: str,
    outcome: AreaFillOutcome,
    count: int,
    now: datetime,
) -> None:
    stmt = insert(AreaFillRecord).values(
        area_key=key, outcome=outcome, result_count=count, fetched_at=now
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[AreaFillRecord.area_key],
            set_={
                "outcome": stmt.excluded.outcome,
                "result_count": stmt.excluded.result_count,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
    )


def _from_record(key: str, record: AreaFillRecord) -> AreaFill:
    return AreaFill(
        area_key=key,
        source=FillSource.cache_fresh,
        outcome=record.outcome,
        result_count=record.result_count,
        # Inside the error backoff we also decline to fetch, and that is still
        # "recent knowledge" -- but what we know recently is that Google failed.
        authoritative=record.outcome is AreaFillOutcome.ok,
    )


async def ensure_area_fresh(
    session: AsyncSession,
    provider: PlacesProvider,
    query: NearbyQuery,
    *,
    ttl: timedelta | None = None,
    allow_fetch: bool = True,
    now: datetime | None = None,
) -> AreaFill:
    """Fill an area only if it needs filling, and say what actually happened.

    This is what callers should use. `refresh_area()` below is unconditional:
    it bills one `searchNearby` every time it is called, consults neither
    `is_stale` nor `DEFAULT_TTL`, and has no idea whether anyone already asked.

    `allow_fetch=False` and a longer `ttl` both push toward fewer calls. Neither
    direction is symmetric on purpose -- see `policy.resolve_ttl`.
    """
    now = now or datetime.now(UTC)
    key = area_key(query)
    ttl = policy.resolve_ttl(ttl)
    may_fetch = allow_fetch and policy.fetch_enabled()

    record = await _last_fill(session, key)
    if record is not None and _covers(record, ttl, now):
        return _from_record(key, record)

    if not may_fetch:
        return AreaFill(
            area_key=key,
            source=FillSource.policy_declined,
            outcome=None,
            result_count=0,
            authoritative=False,
        )

    # Two planning runs over the same city race here. `upsert_places` is
    # idempotent, so the race is correct -- and billed twice, which is the part
    # worth preventing. Transaction-scoped, so it releases with the commit.
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(key))))
    record = await _last_fill(session, key)
    if record is not None and _covers(record, ttl, now):
        return _from_record(key, record)

    try:
        found = await provider.search_nearby(query)
    except ProviderError as exc:
        outcome = outcome_for(exc)
        await _record(session, key, outcome, 0, now)
        return AreaFill(
            area_key=key,
            source=FillSource.fetched,
            outcome=outcome,
            result_count=0,
            authoritative=False,
        )

    await upsert_places(session, found)
    await _record(session, key, AreaFillOutcome.ok, len(found), now)
    return AreaFill(
        area_key=key,
        source=FillSource.fetched,
        outcome=AreaFillOutcome.ok,
        result_count=len(found),
        authoritative=True,
    )
