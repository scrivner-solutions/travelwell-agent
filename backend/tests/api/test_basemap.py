"""GET /explore/basemap, and the shaping behind it.

The endpoint's contract is unusual and worth stating: it must never be the
reason Explore fails. Geography is an enrichment on top of a map that already
worked without it, so every failure here -- no coordinates, provider down,
fetching switched off -- has to come back 200 with empty layers.

The provider is stubbed throughout. `tests/conftest.py` pins
BASEMAP_FETCH_ENABLED off for the whole suite; the tests that exercise the
fetch path turn it on for themselves and replace the network call, which is the
same two-part arrangement the places layer uses.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.basemap import geometry, overpass
from app.services.basemap.geometry import Basemap, bucket_radius, normalize, simplify

pytestmark = pytest.mark.asyncio

ANCHOR_LAT, ANCHOR_LNG = 41.8924, -87.6252


def _area(radius_m: int = 2000):
    return normalize(ANCHOR_LAT, ANCHOR_LNG, radius_m)


def _way(*points):
    return {"geometry": [{"lat": lat, "lon": lng} for lat, lng in points]}


async def _make_trip(user, *, located: bool = True):
    from datetime import date

    import app.db.engine as db
    from app.db.models import Trip, TripOrigin, TripState

    async with db.SessionFactory() as session:
        trip = Trip(
            user_id=user.user_id,
            destination_city="Chicago",
            timezone="America/Chicago",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
            state=TripState.active,
            origin=TripOrigin.manual,
            hotel_name="The Gwen" if located else None,
            hotel_lat=ANCHOR_LAT if located else None,
            hotel_lng=ANCHOR_LNG if located else None,
        )
        session.add(trip)
        await session.commit()
        return trip.trip_id


async def _seed_area(radius_m: int = 2000, *, age: timedelta = timedelta(0)):
    import app.db.engine as db
    from app.db.models import BasemapArea

    async with db.SessionFactory() as session:
        session.add(
            BasemapArea(
                area_key=_area(radius_m).key,
                roads_major=[[41.89, -87.62, 41.90, -87.63]],
                roads_minor=[],
                water=[],
                parks=[],
                buildings=[],
                fetched_at=datetime.now(UTC) - age,
            )
        )
        await session.commit()


# --- shaping -------------------------------------------------------------


def test_simplify_drops_points_that_round_to_the_same_place():
    """Most of the size reduction is here: OSM ways carry survey-grade
    vertices metres apart, and at map scale all but one of them is noise."""
    area = _area()
    way = simplify(area, [(41.89241, -87.62523), (41.89242, -87.62524), (41.9, -87.63)])
    assert way == [41.8924, -87.6252, 41.9, -87.63]


def test_a_way_that_collapses_to_one_point_is_not_a_line():
    area = _area()
    payload = {"elements": [{"tags": {"highway": "primary"},
                             **_way((41.89241, -87.62523), (41.89242, -87.62524))}]}
    assert overpass.parse(area, payload).roads_major == []


def test_only_the_named_road_classes_are_kept():
    """Residential streets are deliberately absent. At 320 px a full street
    grid is a grey wash, and the classes below are what still reads as shape."""
    area = _area()
    payload = {"elements": [
        {"tags": {"highway": h}, **_way((41.89, -87.62), (41.90, -87.63))}
        for h in ("motorway", "primary", "secondary", "tertiary", "residential", "footway")
    ]}
    drawn = overpass.parse(area, payload)
    assert len(drawn.roads_major) == 2
    assert len(drawn.roads_minor) == 2


def test_a_ring_smaller_than_a_few_pixels_is_dropped():
    area = _area()
    payload = {"elements": [
        {"tags": {"leisure": "park"},
         **_way((41.89, -87.62), (41.8901, -87.6201), (41.89, -87.62))},
        {"tags": {"leisure": "park"},
         **_way((41.89, -87.62), (41.90, -87.63), (41.89, -87.62))},
    ]}
    assert len(overpass.parse(area, payload).parks) == 1


def test_minor_roads_go_whole_when_the_area_is_too_dense(monkeypatch):
    """Dropped as a layer rather than truncated. Half a road network drawn to
    an arbitrary cut-off looks like missing data; one tier fewer looks coarse."""
    monkeypatch.setattr(overpass, "_MAX_POINTS", 3)
    area = _area()
    payload = {"elements": [
        {"tags": {"highway": "primary"}, **_way((41.89, -87.62), (41.90, -87.63))},
        {"tags": {"highway": "secondary"}, **_way((41.88, -87.61), (41.91, -87.64))},
    ]}
    drawn = overpass.parse(area, payload)
    assert drawn.roads_major and drawn.roads_minor == []


def test_water_and_parks_are_separate_layers():
    area = _area()
    ring = _way((41.89, -87.62), (41.90, -87.63), (41.89, -87.62))
    payload = {"elements": [
        {"tags": {"natural": "water"}, **ring},
        {"tags": {"waterway": "riverbank"}, **ring},
        {"tags": {"leisure": "park"}, **ring},
    ]}
    drawn = overpass.parse(area, payload)
    assert len(drawn.water) == 2
    assert len(drawn.parks) == 1


# --- area keys -----------------------------------------------------------


def test_a_category_filter_sized_radius_change_reuses_one_area():
    """The property the bucketing exists for. Explore's plot radius is computed
    from what is on screen, so it moves on every chip tap; if that reached the
    cache key each tap would fetch a near-identical city."""
    assert normalize(ANCHOR_LAT, ANCHOR_LNG, 1600).key == normalize(
        ANCHOR_LAT, ANCHOR_LNG, 1950
    ).key
    assert bucket_radius(1600) == bucket_radius(1950) == 2000


def test_two_hotels_in_one_district_share_an_area():
    # 3dp is about 110 m.
    assert normalize(41.8924, -87.6252, 2000).key == normalize(
        41.89249, -87.62518, 2000
    ).key


def test_a_bounding_box_widens_in_longitude_away_from_the_equator():
    """Without the cosine correction a northern city's box is too narrow and
    the map loses its eastern and western edges.

    The ratio is asserted rather than "wider than tall". At latitude 60 the two
    spans are subtracted at different magnitudes, so an uncorrected box makes
    that comparison come out true on floating-point noise alone -- it passed
    against a deliberately broken projection before this was tightened.
    """
    import math

    south, west, north, east = normalize(60.0, 10.0, 2000).bbox()
    assert (east - west) == pytest.approx(
        (north - south) / math.cos(math.radians(60.0)), rel=1e-9
    )


# --- the endpoint --------------------------------------------------------


async def test_requires_auth(client, user):
    trip_id = await _make_trip(user)
    r = await client.get("/api/v1/explore/basemap", params={"trip_id": str(trip_id)})
    assert r.status_code == 401


async def test_someone_elses_trip_is_not_found(authed_client, other_user):
    trip_id = await _make_trip(other_user)
    r = await authed_client.get(
        "/api/v1/explore/basemap", params={"trip_id": str(trip_id)}
    )
    assert r.status_code == 404


async def test_a_trip_with_no_coordinates_draws_nothing(authed_client, user):
    """Still 200. There is no honest area to draw, and guessing one would put
    a stranger's streets under this trip's pins."""
    trip_id = await _make_trip(user, located=False)
    r = await authed_client.get(
        "/api/v1/explore/basemap", params={"trip_id": str(trip_id)}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["roads_major"] == [] and body["parks"] == []
    assert body["attribution"] == geometry.ATTRIBUTION


async def test_a_cached_area_is_served_without_asking_the_provider(
    authed_client, user, monkeypatch
):
    monkeypatch.setenv("BASEMAP_FETCH_ENABLED", "1")

    async def _refuse(area):
        raise AssertionError("fetched an area that was already cached")

    monkeypatch.setattr(overpass, "fetch", _refuse)
    trip_id = await _make_trip(user)
    await _seed_area()
    r = await authed_client.get(
        "/api/v1/explore/basemap", params={"trip_id": str(trip_id)}
    )
    assert r.status_code == 200, r.text
    assert r.json()["roads_major"] == [[41.89, -87.62, 41.9, -87.63]]


async def test_fetching_switched_off_draws_nothing_rather_than_failing(
    authed_client, user
):
    trip_id = await _make_trip(user)
    r = await authed_client.get(
        "/api/v1/explore/basemap", params={"trip_id": str(trip_id)}
    )
    assert r.status_code == 200, r.text
    assert r.json()["roads_major"] == []


async def test_a_fetch_is_stored_so_the_next_request_is_free(
    authed_client, user, monkeypatch
):
    monkeypatch.setenv("BASEMAP_FETCH_ENABLED", "1")
    calls: list[str] = []

    async def _once(area):
        calls.append(area.key)
        return Basemap([[41.0, -87.0, 41.1, -87.1]], [], [], [], [])

    monkeypatch.setattr(overpass, "fetch", _once)
    trip_id = await _make_trip(user)
    params = {"trip_id": str(trip_id)}
    first = await authed_client.get("/api/v1/explore/basemap", params=params)
    second = await authed_client.get("/api/v1/explore/basemap", params=params)
    assert first.json()["roads_major"] == second.json()["roads_major"]
    assert calls == [_area().key]


async def test_a_provider_failure_keeps_the_stale_area(
    authed_client, user, monkeypatch
):
    """Streets did not move because a donated server timed out, so old
    geography beats none. The alternative -- storing the outage -- would leave
    the map blank until someone deleted the row by hand."""
    monkeypatch.setenv("BASEMAP_FETCH_ENABLED", "1")

    async def _down(area):
        raise overpass.BasemapUnavailable("timeout")

    monkeypatch.setattr(overpass, "fetch", _down)
    trip_id = await _make_trip(user)
    await _seed_area(age=timedelta(days=400))
    r = await authed_client.get(
        "/api/v1/explore/basemap", params={"trip_id": str(trip_id)}
    )
    assert r.status_code == 200, r.text
    assert r.json()["roads_major"] == [[41.89, -87.62, 41.9, -87.63]]


async def test_the_served_radius_is_the_bucket_not_the_request(authed_client, user):
    trip_id = await _make_trip(user)
    r = await authed_client.get(
        "/api/v1/explore/basemap", params={"trip_id": str(trip_id), "radius_m": 1400}
    )
    assert r.json()["radius_m"] == 1500


def test_a_wide_area_does_not_ask_for_roads_it_would_throw_away():
    """At 5.5 km the map draws 34 m to the pixel, where secondary and tertiary
    roads stop being streets and become a wash. Asking anyway costs a donated
    server minutes of work to compute something we would drop."""
    close = overpass.build_query(normalize(ANCHOR_LAT, ANCHOR_LNG, 2000))
    wide = overpass.build_query(normalize(ANCHOR_LAT, ANCHOR_LNG, 9000))
    assert "secondary" in close and "tertiary" in close
    assert "secondary" not in wide and "tertiary" not in wide
    assert "motorway" in wide


def test_the_bucket_ladder_does_not_double():
    """A doubling step is climbed by rounding up, so a 4.5 km map would fetch
    an 8 km one: four times the geometry for none of the picture."""
    from app.services.basemap.geometry import _RADIUS_BUCKETS

    for smaller, larger in zip(_RADIUS_BUCKETS, _RADIUS_BUCKETS[1:], strict=False):
        assert larger / smaller < 1.75


async def test_a_busy_overpass_is_retried_rather_than_treated_as_empty(monkeypatch):
    """A refused slot is weather, not an answer. Recording it as "no streets
    here" would blank the map for the length of the cache TTL."""
    monkeypatch.setattr(overpass, "_BACKOFF_SECONDS", 0.0)
    attempts: list[str] = []

    async def _busy_then_fine(query):
        attempts.append(query)
        if len(attempts) < 3:
            raise overpass.BasemapBusy("overpass returned 504")
        return {"elements": [{"tags": {"highway": "primary"},
                              **_way((41.89, -87.62), (41.90, -87.63))}]}

    monkeypatch.setattr(overpass, "_request", _busy_then_fine)
    drawn = await overpass.fetch(_area())
    assert len(attempts) == 3
    assert drawn.roads_major


async def test_a_permanently_busy_overpass_gives_up(monkeypatch):
    monkeypatch.setattr(overpass, "_BACKOFF_SECONDS", 0.0)

    async def _always_busy(query):
        raise overpass.BasemapBusy("overpass returned 429")

    monkeypatch.setattr(overpass, "_request", _always_busy)
    with pytest.raises(overpass.BasemapUnavailable):
        await overpass.fetch(_area())


async def test_a_bad_request_is_not_retried(monkeypatch):
    """Only the load-shedding statuses are weather. Retrying a 400 three times
    is three times the rudeness for the same answer."""
    monkeypatch.setattr(overpass, "_BACKOFF_SECONDS", 0.0)
    attempts: list[str] = []

    async def _broken(query):
        attempts.append(query)
        raise ValueError("not json")

    monkeypatch.setattr(overpass, "_request", _broken)
    with pytest.raises(overpass.BasemapUnavailable):
        await overpass.fetch(_area())
    assert len(attempts) == 1


def test_buildings_are_asked_for_only_when_they_would_be_legible():
    """At 2 km the map draws 12.5 m to the pixel and a footprint is a few
    pixels across. One bucket wider they are specks, and a city of specks is a
    haze over the streets -- worse than nothing, and the largest layer by far."""
    close = overpass.build_query(normalize(ANCHOR_LAT, ANCHOR_LNG, 1800))
    wide = overpass.build_query(normalize(ANCHOR_LAT, ANCHOR_LNG, 4500))
    assert '["building"]' in close
    assert '["building"]' not in wide


def test_a_building_is_a_filled_ring_not_a_line():
    area = _area()
    payload = {"elements": [{"tags": {"building": "yes"},
                             **_way((41.89, -87.62), (41.90, -87.62),
                                    (41.90, -87.63), (41.89, -87.62))}]}
    drawn = overpass.parse(area, payload)
    assert len(drawn.buildings) == 1
    assert drawn.roads_major == [] and drawn.parks == []


def test_a_building_too_small_to_see_is_dropped():
    """Subject to the same smudge test as parks: it is drawn as a ring, and a
    ring under a few pixels is a dot that reads as dirt on the screen."""
    area = _area()
    payload = {"elements": [{"tags": {"building": "house"},
                             **_way((41.89, -87.62), (41.8901, -87.6201),
                                    (41.89, -87.62))}]}
    assert overpass.parse(area, payload).buildings == []
