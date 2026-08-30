"""Filling the places cache: upsert by provider_ref, and what staleness means."""

from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.asyncio


def a_place(ref: str, name: str, amenities=(), **kw):
    from app.db.models import PlaceKind
    from app.services.places.ports import ProviderPlace

    return ProviderPlace(
        provider_ref=ref,
        name=name,
        kind=PlaceKind.workout,
        lat=41.89,
        lng=-87.62,
        amenities=tuple(amenities),
        **kw,
    )


async def test_new_places_land_in_the_cache(db_session):
    from app.services.places.cache import upsert_places

    rows = await upsert_places(
        db_session, [a_place("g1", "Some Gym"), a_place("g2", "Other Gym")]
    )
    await db_session.commit()
    assert {r.name for r in rows} == {"Some Gym", "Other Gym"}
    assert all(r.place_id is not None for r in rows)


async def test_the_same_provider_ref_updates_rather_than_duplicating(db_session):
    import sqlalchemy as sa

    from app.db.models import Place
    from app.services.places.cache import upsert_places

    await upsert_places(db_session, [a_place("g1", "Old Name")])
    await db_session.commit()
    await upsert_places(db_session, [a_place("g1", "New Name")])
    await db_session.commit()

    names = (await db_session.execute(sa.select(Place.name))).scalars().all()
    assert names == ["New Name"]


async def test_amenities_are_replaced_not_merged(db_session):
    """The provider is authoritative; a merge accumulates amenities a venue
    no longer has, which is the quiet wrongness a cache must not add."""
    from app.services.places.cache import upsert_places

    await upsert_places(db_session, [a_place("g1", "Gym", amenities=["pool", "sauna"])])
    await db_session.commit()
    rows = await upsert_places(db_session, [a_place("g1", "Gym", amenities=["pool"])])
    await db_session.commit()
    assert rows[0].amenities == ["pool"]


async def test_an_empty_result_writes_nothing(db_session):
    from app.services.places.cache import upsert_places

    assert await upsert_places(db_session, []) == []


async def test_refreshing_an_area_writes_what_the_provider_returns(db_session):
    from app.db.models import PlaceKind
    from app.services.places.cache import refresh_area
    from app.services.places.fake import FakePlaces
    from app.services.places.ports import NearbyQuery

    provider = FakePlaces(places=[a_place("g1", "Near Gym")])
    rows = await refresh_area(
        db_session, provider, NearbyQuery(lat=41.89, lng=-87.62, radius_m=1000)
    )
    await db_session.commit()
    assert [r.name for r in rows] == ["Near Gym"]
    assert provider.calls[0].kinds == ()
    assert rows[0].kind is PlaceKind.workout


async def test_a_provider_outage_is_raised_not_cached_as_emptiness(db_session):
    from app.services.places.cache import refresh_area
    from app.services.places.ports import NearbyQuery, ProviderError

    class Broken:
        name = "broken"

        async def geocode(self, query):
            raise ProviderError("down")

        async def search_nearby(self, query):
            raise ProviderError("down")

    with pytest.raises(ProviderError):
        await refresh_area(db_session, Broken(), NearbyQuery(41.89, -87.62, 1000))


async def test_staleness_is_measured_against_fetched_at(db_session):
    from app.services.places.cache import DEFAULT_TTL, is_stale, upsert_places

    rows = await upsert_places(db_session, [a_place("g1", "Gym")])
    await db_session.commit()
    place = rows[0]

    assert is_stale(place) is False
    later = datetime.now(UTC) + DEFAULT_TTL + timedelta(minutes=1)
    assert is_stale(place, now=later) is True
