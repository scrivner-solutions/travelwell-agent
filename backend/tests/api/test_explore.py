"""GET /explore: anchor choice, radius, category chips, and profile matching.

Places are placed at deliberate offsets from one anchor rather than reused from
the seed, so a distance assertion says what it means. 0.01 degrees of latitude
is about 1.1 km; 0.2 is about 22 km and sits outside the default radius.
"""

from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.asyncio

ANCHOR_LAT, ANCHOR_LNG = 41.8924, -87.6252


async def _make_trip(user, *, hotel: bool = True, located: bool = True):
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
            destination_lat=ANCHOR_LAT if located else None,
            destination_lng=ANCHOR_LNG if located else None,
            hotel_name="The Gwen" if hotel else None,
            hotel_lat=ANCHOR_LAT if hotel else None,
            hotel_lng=ANCHOR_LNG if hotel else None,
        )
        session.add(trip)
        await session.commit()
        return trip.trip_id


async def _make_places():
    import app.db.engine as db
    from app.db.models import Place, PlaceKind

    async with db.SessionFactory() as session:
        session.add_all([
            Place(
                name="Corner Pool", kind=PlaceKind.workout,
                lat=ANCHOR_LAT + 0.005, lng=ANCHOR_LNG,
                amenities=["pool", "sauna"], day_pass_cents=1500,
            ),
            Place(
                name="Basement Gym", kind=PlaceKind.workout,
                lat=ANCHOR_LAT + 0.01, lng=ANCHOR_LNG,
                amenities=["weights"], day_pass_cents=0,
            ),
            Place(
                name="Spendy Club", kind=PlaceKind.workout,
                lat=ANCHOR_LAT + 0.008, lng=ANCHOR_LNG,
                amenities=["pool", "sauna"], day_pass_cents=6000,
            ),
            Place(
                name="Green Plate", kind=PlaceKind.food,
                lat=ANCHOR_LAT, lng=ANCHOR_LNG + 0.006,
                amenities=["vegetarian"], price_level=2,
            ),
            Place(
                name="Riverwalk", kind=PlaceKind.outdoor,
                lat=ANCHOR_LAT + 0.002, lng=ANCHOR_LNG, amenities=[],
            ),
            Place(
                name="The Gwen", kind=PlaceKind.lodging,
                lat=ANCHOR_LAT, lng=ANCHOR_LNG, amenities=["gym"],
            ),
            Place(
                name="Far Suburb Y", kind=PlaceKind.workout,
                lat=ANCHOR_LAT + 0.2, lng=ANCHOR_LNG,
                amenities=["pool"], day_pass_cents=1000,
            ),
        ])
        await session.commit()


async def test_requires_auth(client, user):
    trip_id = await _make_trip(user)
    r = await client.get("/api/v1/explore", params={"trip_id": str(trip_id)})
    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"


async def test_someone_elses_trip_is_not_found(authed_client, other_user):
    trip_id = await _make_trip(other_user)
    r = await authed_client.get("/api/v1/explore", params={"trip_id": str(trip_id)})
    assert r.status_code == 404
    assert r.json()["code"] == "trip_not_found"


async def test_anchor_is_the_hotel_when_the_trip_has_one(authed_client, user):
    trip_id = await _make_trip(user)
    await _make_places()
    r = await authed_client.get("/api/v1/explore", params={"trip_id": str(trip_id)})
    assert r.status_code == 200, r.text
    anchor = r.json()["anchor"]
    assert anchor["name"] == "The Gwen"
    assert anchor["is_hotel"] is True


async def test_anchor_falls_back_to_the_destination_centre(authed_client, user):
    trip_id = await _make_trip(user, hotel=False)
    await _make_places()
    r = await authed_client.get("/api/v1/explore", params={"trip_id": str(trip_id)})
    anchor = r.json()["anchor"]
    assert anchor["name"] == "Chicago"
    assert anchor["is_hotel"] is False


async def test_a_trip_with_no_coordinates_returns_nothing_rather_than_guessing(
    authed_client, user
):
    trip_id = await _make_trip(user, hotel=False, located=False)
    await _make_places()
    r = await authed_client.get("/api/v1/explore", params={"trip_id": str(trip_id)})
    body = r.json()
    # ApiRoute omits nulls rather than sending them, so an absent anchor is the
    # shape the frontend sees.
    assert "anchor" not in body
    assert body["places"] == []
    assert body["kinds"] == []


async def test_lodging_is_the_anchor_and_never_a_card(authed_client, user):
    trip_id = await _make_trip(user)
    await _make_places()
    body = (
        await authed_client.get("/api/v1/explore", params={"trip_id": str(trip_id)})
    ).json()
    assert "lodging" not in {k["kind"] for k in body["kinds"]}
    assert all(p["kind"] != "lodging" for p in body["places"])


async def test_the_radius_excludes_the_far_place_and_widening_it_admits_it(
    authed_client, user
):
    trip_id = await _make_trip(user)
    await _make_places()
    default = (
        await authed_client.get("/api/v1/explore", params={"trip_id": str(trip_id)})
    ).json()
    assert "Far Suburb Y" not in {p["name"] for p in default["places"]}

    wide = (
        await authed_client.get(
            "/api/v1/explore", params={"trip_id": str(trip_id), "radius_m": 40000}
        )
    ).json()
    assert "Far Suburb Y" in {p["name"] for p in wide["places"]}


async def test_chip_counts_do_not_move_when_a_chip_is_selected(authed_client, user):
    trip_id = await _make_trip(user)
    await _make_places()
    all_kinds = (
        await authed_client.get("/api/v1/explore", params={"trip_id": str(trip_id)})
    ).json()["kinds"]
    filtered = (
        await authed_client.get(
            "/api/v1/explore", params={"trip_id": str(trip_id), "category": "food"}
        )
    ).json()
    assert filtered["kinds"] == all_kinds
    assert {p["kind"] for p in filtered["places"]} == {"food"}


async def test_chips_come_from_the_users_own_preferences(authed_client, user):
    trip_id = await _make_trip(user)
    await _make_places()
    await authed_client.patch(
        "/api/v1/me/preferences",
        json={"activities": ["swim"], "amenities": ["sauna"], "day_pass_budget_cents": 2000},
    )
    body = (
        await authed_client.get(
            "/api/v1/explore", params={"trip_id": str(trip_id), "category": "workout"}
        )
    ).json()
    by_name = {p["name"]: p for p in body["places"]}
    assert by_name["Corner Pool"]["matched_preferences"] == [
        "Swim",
        "Sauna",
        "Within your day-pass budget",
    ]
    assert by_name["Basement Gym"]["matched_preferences"] == [
        "Within your day-pass budget"
    ]


async def test_an_over_budget_place_is_returned_last_with_its_reason(
    authed_client, user
):
    trip_id = await _make_trip(user)
    await _make_places()
    await authed_client.patch(
        "/api/v1/me/preferences",
        json={"activities": ["swim"], "day_pass_budget_cents": 2000},
    )
    places = (
        await authed_client.get(
            "/api/v1/explore", params={"trip_id": str(trip_id), "category": "workout"}
        )
    ).json()["places"]
    assert places[-1]["name"] == "Spendy Club"
    assert places[-1]["over_budget_reason"] == "$60 day pass, above the $20 you set"
    # Still a real suggestion, still explained -- just not offered first.
    assert places[-1]["matched_preferences"] == ["Swim"]


async def test_distance_is_reported_from_the_anchor(authed_client, user):
    trip_id = await _make_trip(user)
    await _make_places()
    body = (
        await authed_client.get(
            "/api/v1/explore", params={"trip_id": str(trip_id), "category": "workout"}
        )
    ).json()
    by_name = {p["name"]: p for p in body["places"]}
    # 0.005 deg of latitude is ~556 m, so the meters are checkable independently
    # of the walking-pace constant the minutes are derived from.
    assert 500 < by_name["Corner Pool"]["distance_meters"] < 600
    assert (
        by_name["Corner Pool"]["walk_minutes"] < by_name["Basement Gym"]["walk_minutes"]
    )


async def test_free_text_matches_the_fields_the_card_shows(authed_client, user):
    trip_id = await _make_trip(user)
    await _make_places()
    body = (
        await authed_client.get(
            "/api/v1/explore", params={"trip_id": str(trip_id), "query": "pool"}
        )
    ).json()
    # "Corner Pool" by name. "Spendy Club" has a pool amenity but shows nothing
    # saying so, and a hit the user cannot see on the card reads as a bug.
    assert [p["name"] for p in body["places"]] == ["Corner Pool"]


async def test_free_text_is_case_insensitive(authed_client, user):
    trip_id = await _make_trip(user)
    await _make_places()
    body = (
        await authed_client.get(
            "/api/v1/explore", params={"trip_id": str(trip_id), "query": "GREEN"}
        )
    ).json()
    assert [p["name"] for p in body["places"]] == ["Green Plate"]


# --- GET /geocode ------------------------------------------------------------


def _swap_provider(monkeypatch, provider):
    from app.services import places

    monkeypatch.setattr(places, "default_provider", lambda: provider)
    monkeypatch.setattr("app.api.explore.default_provider", lambda: provider)


async def test_geocode_requires_auth(client):
    r = await client.get("/api/v1/geocode", params={"query": "Chicago"})
    assert r.status_code == 401


async def test_geocode_resolves_a_known_place(authed_client, monkeypatch):
    from app.services.places.fake import FakePlaces
    from app.services.places.ports import GeocodeResult

    _swap_provider(
        monkeypatch,
        FakePlaces(
            geocodes={"chicago": GeocodeResult("Chicago", "Chicago, IL", 41.88, -87.62)}
        ),
    )
    r = await authed_client.get("/api/v1/geocode", params={"query": "Chicago"})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "query": "Chicago",
        "name": "Chicago, IL",
        "lat": 41.88,
        "lng": -87.62,
    }


async def test_an_unknown_place_is_404_not_a_guess(authed_client, monkeypatch):
    """The prototype answered with hardcoded Skokie coordinates here."""
    from app.services.places.fake import FakePlaces

    _swap_provider(monkeypatch, FakePlaces())
    r = await authed_client.get("/api/v1/geocode", params={"query": "Atlantis"})
    assert r.status_code == 404
    assert r.json()["code"] == "location_not_found"


async def test_missing_credentials_is_503_and_says_so(authed_client, monkeypatch):
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    from app.services.places import google as google_provider
    from app.services.places.google import GooglePlaces

    monkeypatch.setattr(google_provider, "_credentials", None)
    monkeypatch.setattr(
        google.auth,
        "default",
        lambda **kw: (_ for _ in ()).throw(DefaultCredentialsError("none")),
    )
    _swap_provider(monkeypatch, GooglePlaces())
    r = await authed_client.get("/api/v1/geocode", params={"query": "Chicago"})
    assert r.status_code == 503
    assert r.json()["code"] == "geocoding_unavailable"


async def test_a_provider_failure_is_502_not_a_missing_place(
    authed_client, monkeypatch
):
    from app.services.places.ports import ProviderError

    class Broken:
        name = "broken"

        async def geocode(self, query):
            raise ProviderError("down")

        async def search_nearby(self, query):
            raise ProviderError("down")

    _swap_provider(monkeypatch, Broken())
    r = await authed_client.get("/api/v1/geocode", params={"query": "Chicago"})
    assert r.status_code == 502
    assert r.json()["code"] == "geocoding_failed"


# --- Unknown as a third value on the wire (OWNER.md #8) ---------------------


async def _make_unlisted_place():
    """A row as a live Google fetch would write it: no amenities field at all."""
    import app.db.engine as db
    from app.db.models import Place, PlaceKind

    async with db.SessionFactory() as session:
        session.add(
            Place(
                name="Unlisted Gym", kind=PlaceKind.workout,
                lat=ANCHOR_LAT + 0.001, lng=ANCHOR_LNG,
                amenities=None, day_pass_cents=None,
            )
        )
        await session.commit()


async def test_unknown_amenities_are_absent_from_the_wire_and_empty_ones_are_not(
    authed_client, user
):
    """The distinction has to survive serialisation or it does not exist.

    `ApiRoute` omits None, so absent means unknown and `[]` means the venue has
    none. A client that reads a missing key as an empty list rebuilds exactly
    the conflation this removed.
    """
    trip_id = await _make_trip(user)
    await _make_places()
    await _make_unlisted_place()
    # No category filter: the two rows being contrasted are different kinds.
    body = (
        await authed_client.get("/api/v1/explore", params={"trip_id": str(trip_id)})
    ).json()
    by_name = {p["name"]: p for p in body["places"]}
    assert "amenities" not in by_name["Unlisted Gym"]
    assert by_name["Riverwalk"]["amenities"] == []


async def test_a_place_we_know_nothing_about_says_so_rather_than_ranking_silently(
    authed_client, user
):
    trip_id = await _make_trip(user)
    await _make_places()
    await _make_unlisted_place()
    await authed_client.patch(
        "/api/v1/me/preferences",
        json={"activities": ["swim"], "day_pass_budget_cents": 2000},
    )
    body = (
        await authed_client.get(
            "/api/v1/explore", params={"trip_id": str(trip_id), "category": "workout"}
        )
    ).json()
    by_name = {p["name"]: p for p in body["places"]}
    unlisted = by_name["Unlisted Gym"]
    assert unlisted["matched_preferences"] == []
    assert unlisted["unknown_notes"] == [
        "Facilities not listed",
        "Day-pass price not listed",
    ]
    # Said, not dropped: it is still a card, and still not over budget.
    assert "over_budget_reason" not in unlisted
    assert by_name["Corner Pool"]["unknown_notes"] == []
