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


# --- ensure_area_fresh: when we are allowed to spend money -------------------


class StubProvider:
    """Counts calls, because "did this bill?" is the property under test."""

    name = "stub"

    def __init__(self, result=(), raises: Exception | None = None):
        self.result = list(result)
        self.raises = raises
        self.calls = 0

    async def search_nearby(self, query):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return list(self.result)

    async def geocode(self, query):
        return None


def a_query(**kw):
    from app.services.places.ports import NearbyQuery

    return NearbyQuery(lat=41.8924, lng=-87.6252, radius_m=3000, **kw)


async def test_a_first_look_fetches_and_is_authoritative(db_session):
    from app.services.places.cache import FillSource, ensure_area_fresh

    provider = StubProvider([a_place("g1", "Some Gym")])
    fill = await ensure_area_fresh(db_session, provider, a_query())
    await db_session.commit()

    assert (fill.source, fill.authoritative, fill.result_count) == (
        FillSource.fetched, True, 1
    )
    assert provider.calls == 1


async def test_a_second_look_inside_the_ttl_does_not_bill(db_session):
    from app.services.places.cache import FillSource, ensure_area_fresh

    provider = StubProvider([a_place("g1", "Some Gym")])
    await ensure_area_fresh(db_session, provider, a_query())
    await db_session.commit()
    fill = await ensure_area_fresh(db_session, provider, a_query())
    await db_session.commit()

    assert fill.source is FillSource.cache_fresh
    assert fill.authoritative is True
    assert provider.calls == 1


async def test_an_area_that_is_genuinely_empty_is_not_refetched_forever(db_session):
    """The expensive case. No rows land, so any "is there a fresh row nearby"
    proxy would refetch this area on every planning run. That is Portland."""
    from app.services.places.cache import FillSource, ensure_area_fresh

    provider = StubProvider([])
    first = await ensure_area_fresh(db_session, provider, a_query())
    await db_session.commit()
    second = await ensure_area_fresh(db_session, provider, a_query())
    await db_session.commit()

    assert (first.source, first.result_count) == (FillSource.fetched, 0)
    assert first.authoritative is True
    assert second.source is FillSource.cache_fresh
    assert provider.calls == 1


async def test_a_caller_may_decline_to_fetch_and_leaves_no_record(db_session):
    import sqlalchemy as sa

    from app.db.models import AreaFillRecord
    from app.services.places.cache import FillSource, ensure_area_fresh

    provider = StubProvider([a_place("g1", "Some Gym")])
    fill = await ensure_area_fresh(
        db_session, provider, a_query(), allow_fetch=False
    )
    await db_session.commit()

    assert fill.source is FillSource.policy_declined
    assert fill.authoritative is False
    assert fill.outcome is None
    assert provider.calls == 0
    # A row is a claim about the provider. We never asked, so there is nothing
    # to claim.
    rows = (await db_session.execute(sa.select(AreaFillRecord))).scalars().all()
    assert rows == []


async def test_the_deployment_can_veto_a_caller_that_asks_to_fetch(
    db_session, monkeypatch
):
    from app.services.places.cache import FillSource, ensure_area_fresh

    monkeypatch.setenv("PLACES_FETCH_ENABLED", "0")
    provider = StubProvider([a_place("g1", "Some Gym")])
    fill = await ensure_area_fresh(db_session, provider, a_query(), allow_fetch=True)
    await db_session.commit()

    assert fill.source is FillSource.policy_declined
    assert provider.calls == 0


async def test_a_caller_cannot_shorten_the_ttl_into_more_fetching(db_session):
    """Overrides are asymmetric: less fetching is allowed, more is not."""
    from app.services.places.cache import FillSource, ensure_area_fresh

    provider = StubProvider([a_place("g1", "Some Gym")])
    await ensure_area_fresh(db_session, provider, a_query())
    await db_session.commit()

    fill = await ensure_area_fresh(
        db_session, provider, a_query(), ttl=timedelta(seconds=0)
    )
    await db_session.commit()
    assert fill.source is FillSource.cache_fresh
    assert provider.calls == 1


async def test_a_missing_credential_records_unavailable_not_error(db_session):
    """ProviderUnavailable subclasses ProviderError, so a base-class check would
    record "we have no credentials" as "Google had an outage". Nothing else in
    the suite would notice: both are failures and both return no places."""
    from app.db.models import AreaFillOutcome
    from app.services.places.cache import ensure_area_fresh
    from app.services.places.ports import ProviderUnavailable

    provider = StubProvider(raises=ProviderUnavailable("no credentials"))
    fill = await ensure_area_fresh(db_session, provider, a_query())
    await db_session.commit()

    assert fill.outcome is AreaFillOutcome.unavailable
    assert fill.authoritative is False


async def test_an_unusable_provider_suppresses_nothing(db_session):
    """A provider that raises before sending a request costs no billed call, so
    a backoff would only mean that fixing credentials needed a row deleted."""
    from app.services.places.cache import ensure_area_fresh
    from app.services.places.ports import ProviderUnavailable

    provider = StubProvider(raises=ProviderUnavailable("no credentials"))
    await ensure_area_fresh(db_session, provider, a_query())
    await db_session.commit()
    await ensure_area_fresh(db_session, provider, a_query())
    await db_session.commit()

    assert provider.calls == 2


async def test_an_outage_backs_off_briefly_and_never_earns_the_full_ttl(
    db_session, monkeypatch
):
    from app.db.models import AreaFillOutcome
    from app.services.places.cache import FillSource, ensure_area_fresh
    from app.services.places.ports import ProviderError

    monkeypatch.setenv("PLACES_ERROR_BACKOFF_MINUTES", "30")
    failing = StubProvider(raises=ProviderError("Google request failed"))
    start = datetime.now(UTC)
    fill = await ensure_area_fresh(db_session, failing, a_query(), now=start)
    await db_session.commit()
    assert fill.outcome is AreaFillOutcome.error
    assert fill.authoritative is False

    # Inside the backoff: the area reads as recently-known, but what we know is
    # that the call failed, so it is not authoritative.
    inside = await ensure_area_fresh(
        db_session, failing, a_query(), now=start + timedelta(minutes=5)
    )
    await db_session.commit()
    assert inside.source is FillSource.cache_fresh
    assert inside.authoritative is False
    assert failing.calls == 1

    # Past the backoff, and long before a successful fetch's TTL would expire.
    working = StubProvider([a_place("g1", "Some Gym")])
    after = await ensure_area_fresh(
        db_session, working, a_query(), now=start + timedelta(hours=2)
    )
    await db_session.commit()
    assert after.source is FillSource.fetched
    assert after.authoritative is True


async def test_looking_for_gyms_does_not_make_restaurants_look_covered(db_session):
    """Kinds are part of the area key. Without that, one fetch would claim
    coverage for questions nobody has asked."""
    from app.db.models import PlaceKind
    from app.services.places.cache import FillSource, ensure_area_fresh

    provider = StubProvider([a_place("g1", "Some Gym")])
    await ensure_area_fresh(
        db_session, provider, a_query(kinds=(PlaceKind.workout,))
    )
    await db_session.commit()
    fill = await ensure_area_fresh(
        db_session, provider, a_query(kinds=(PlaceKind.food,))
    )
    await db_session.commit()

    assert fill.source is FillSource.fetched
    assert provider.calls == 2
