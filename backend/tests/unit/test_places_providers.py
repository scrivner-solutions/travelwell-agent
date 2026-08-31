"""The places seam: one contract both providers answer, plus Google's parsing.

The contract tests are parametrized over implementations, the way the booking
seam's are. Adding a real provider means adding it to PROVIDERS and running
this, not writing a fresh suite for it.
"""

import httpx
import pytest

from app.db.models import PlaceKind
from app.services.places.fake import FakePlaces
from app.services.places.google import GooglePlaces
from app.services.places.ports import (
    GeocodeResult,
    NearbyQuery,
    PlacesProvider,
    ProviderError,
    ProviderPlace,
    ProviderUnavailable,
    Registry,
)

pytestmark = pytest.mark.asyncio

ANCHOR = (41.8924, -87.6252)


def a_place(name: str, kind: PlaceKind, dlat: float = 0.0, dlng: float = 0.0):
    return ProviderPlace(
        provider_ref=f"ref_{name}",
        name=name,
        kind=kind,
        lat=ANCHOR[0] + dlat,
        lng=ANCHOR[1] + dlng,
    )


def google_returning(payload: dict, status: int = 200) -> GooglePlaces:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json=payload))
    return GooglePlaces(client=httpx.AsyncClient(transport=transport))


# --- the contract, over every implementation ---------------------------------

PROVIDERS = [
    pytest.param(
        lambda: FakePlaces(
            places=[
                a_place("Near Gym", PlaceKind.workout, dlat=0.002),
                a_place("Far Gym", PlaceKind.workout, dlat=0.2),
                a_place("Near Cafe", PlaceKind.food, dlat=0.002),
            ],
            geocodes={"chicago": GeocodeResult("Chicago", "Chicago, IL", *ANCHOR)},
        ),
        id="fake",
    ),
]


@pytest.mark.parametrize("build", PROVIDERS)
async def test_a_provider_satisfies_the_port(build):
    assert isinstance(build(), PlacesProvider)


@pytest.mark.parametrize("build", PROVIDERS)
async def test_nothing_matching_is_none_not_an_error(build):
    assert await build().geocode("Atlantis") is None


@pytest.mark.parametrize("build", PROVIDERS)
async def test_the_radius_is_honoured(build):
    found = await build().search_nearby(
        NearbyQuery(lat=ANCHOR[0], lng=ANCHOR[1], radius_m=1000)
    )
    assert {p.name for p in found} == {"Near Gym", "Near Cafe"}


@pytest.mark.parametrize("build", PROVIDERS)
async def test_kinds_narrow_the_search(build):
    found = await build().search_nearby(
        NearbyQuery(
            lat=ANCHOR[0], lng=ANCHOR[1], radius_m=1000, kinds=(PlaceKind.workout,)
        )
    )
    assert {p.name for p in found} == {"Near Gym"}


# --- the registry ------------------------------------------------------------


def test_an_unknown_provider_is_unavailable_not_a_key_error():
    with pytest.raises(ProviderUnavailable):
        Registry().get("nobody")


def test_a_registered_provider_comes_back_by_name():
    registry = Registry()
    fake = FakePlaces()
    registry.register(fake)
    assert registry.get("fake") is fake


# --- Google's own parsing ----------------------------------------------------


async def test_no_key_is_unavailable_rather_than_empty(monkeypatch):
    """A missing key must not read as a destination with nothing in it."""
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailable):
        await GooglePlaces().geocode("Chicago")


async def test_zero_results_is_none_but_a_bad_status_is_an_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    assert await google_returning({"status": "ZERO_RESULTS"}).geocode("Atlantis") is None
    with pytest.raises(ProviderError):
        await google_returning({"status": "REQUEST_DENIED"}).geocode("Chicago")


async def test_geocode_reads_the_first_result(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    provider = google_returning({
        "status": "OK",
        "results": [
            {
                "formatted_address": "Chicago, IL, USA",
                "geometry": {"location": {"lat": 41.88, "lng": -87.62}},
            }
        ],
    })
    got = await provider.geocode("Chicago")
    assert (got.name, got.lat, got.lng) == ("Chicago, IL, USA", 41.88, -87.62)


async def test_a_transport_failure_is_a_provider_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    with pytest.raises(ProviderError):
        await google_returning({}, status=500).geocode("Chicago")


async def test_types_become_our_kinds_and_price_levels_become_numbers(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    provider = google_returning({
        "places": [
            {
                "id": "g1",
                "displayName": {"text": "Some Gym"},
                "location": {"latitude": 41.9, "longitude": -87.6},
                "types": ["gym", "point_of_interest"],
            },
            {
                "id": "g2",
                "displayName": {"text": "Some Restaurant"},
                "location": {"latitude": 41.9, "longitude": -87.6},
                "types": ["restaurant"],
                "priceLevel": "PRICE_LEVEL_MODERATE",
            },
        ]
    })
    found = await provider.search_nearby(
        NearbyQuery(lat=41.9, lng=-87.6, radius_m=1000)
    )
    assert [(p.name, p.kind, p.price_level) for p in found] == [
        ("Some Gym", PlaceKind.workout, None),
        ("Some Restaurant", PlaceKind.food, 2),
    ]


async def test_a_place_we_cannot_place_is_dropped_rather_than_guessed(monkeypatch):
    """No coordinates, or no type we map: both mean we cannot pin it."""
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    provider = google_returning({
        "places": [
            {"id": "a", "displayName": {"text": "No location"}, "types": ["gym"]},
            {
                "id": "b",
                "displayName": {"text": "Unmapped type"},
                "location": {"latitude": 41.9, "longitude": -87.6},
                "types": ["parking"],
            },
        ]
    })
    assert await provider.search_nearby(NearbyQuery(41.9, -87.6, 1000)) == []


async def test_opening_hours_become_the_shape_the_planner_reads(monkeypatch):
    """{"mon": [open, close]} in minutes from midnight -- the seed's shape."""
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    provider = google_returning({
        "places": [
            {
                "id": "g1",
                "displayName": {"text": "Some Gym"},
                "location": {"latitude": 41.9, "longitude": -87.6},
                "types": ["gym"],
                "regularOpeningHours": {
                    "periods": [
                        {
                            "open": {"day": 1, "hour": 6, "minute": 0},
                            "close": {"day": 1, "hour": 22, "minute": 0},
                        },
                        {
                            "open": {"day": 0, "hour": 7, "minute": 30},
                            "close": {"day": 0, "hour": 20, "minute": 0},
                        },
                    ]
                },
            }
        ]
    })
    found = await provider.search_nearby(NearbyQuery(41.9, -87.6, 1000))
    assert found[0].hours == {"mon": [360, 1320], "sun": [450, 1200]}


async def test_a_venue_open_past_midnight_closes_at_the_days_end(monkeypatch):
    """Rather than wrapping to a negative-length day, which reads as closed."""
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    provider = google_returning({
        "places": [
            {
                "id": "g1",
                "displayName": {"text": "Late Bar"},
                "location": {"latitude": 41.9, "longitude": -87.6},
                "types": ["restaurant"],
                "regularOpeningHours": {
                    "periods": [
                        {
                            "open": {"day": 5, "hour": 17, "minute": 0},
                            "close": {"day": 6, "hour": 2, "minute": 0},
                        }
                    ]
                },
            }
        ]
    })
    found = await provider.search_nearby(NearbyQuery(41.9, -87.6, 1000))
    assert found[0].hours == {"fri": [1020, 1440]}
