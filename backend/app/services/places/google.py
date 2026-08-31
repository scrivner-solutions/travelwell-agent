"""Google as a places provider: Places API (New) plus the Geocoding API.

Async httpx throughout, because the app is async and the prototype's
synchronous `requests` calls blocked the event loop for the length of a Google
round trip.

Two limits worth knowing before trusting a live-filled cache, both stated here
rather than discovered later:

  amenities   Google has no field for "has a pool, has a sauna". Our matcher
              leans on amenities harder than on anything else, so rows filled
              from here start with none and match fewer preferences than the
              hand-written seed rows do.
  day_pass    Nothing in the API prices a day pass. Left null, which the
              matcher reads as unknown rather than as free.
"""

from __future__ import annotations

import os

import httpx

from app.db.models import PlaceKind
from app.services.places.ports import (
    GeocodeResult,
    NearbyQuery,
    ProviderError,
    ProviderPlace,
    ProviderUnavailable,
)

_PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_TIMEOUT = httpx.Timeout(8.0)

# Only what we map. Sending a narrow list is also what keeps the bill down:
# Places (New) charges per request, not per result.
_KIND_TYPES: dict[PlaceKind, tuple[str, ...]] = {
    PlaceKind.workout: ("gym", "fitness_center", "swimming_pool", "sports_complex"),
    PlaceKind.food: ("restaurant", "cafe"),
    PlaceKind.outdoor: ("park", "hiking_area"),
    PlaceKind.recovery: ("spa", "wellness_center"),
    PlaceKind.lodging: ("hotel", "lodging"),
}
_TYPE_KIND = {t: k for k, types in _KIND_TYPES.items() for t in types}

# Google's own ordering, 0 = Sunday.
_DAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")

_PRICE_LEVELS = {
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}

_FIELD_MASK = ",".join((
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.types",
    "places.priceLevel",
    "places.regularOpeningHours",
    "places.editorialSummary",
))


def api_key() -> str:
    """One name only. The prototype fell back to GOOGLE_API_KEY, which made a
    missing Maps key look like a working Vertex key."""
    return os.getenv("GOOGLE_MAPS_API_KEY", "")


def _opening_hours(payload: dict) -> dict[str, list[int]] | None:
    """Google periods -> {"mon": [open_minute, close_minute]}, local minutes.

    The shape the seed writes and the planner reads. A venue open past
    midnight closes at 1440 rather than wrapping, because a negative-length
    day would read as closed.
    """
    periods = payload.get("periods") or []
    hours: dict[str, list[int]] = {}
    for period in periods:
        opens, closes = period.get("open"), period.get("close")
        if not opens or not closes:
            continue
        day = _DAYS[opens.get("day", 0) % 7]
        start = opens.get("hour", 0) * 60 + opens.get("minute", 0)
        end = closes.get("hour", 0) * 60 + closes.get("minute", 0)
        hours[day] = [start, end if end > start else 1440]
    return hours or None


def _to_place(payload: dict) -> ProviderPlace | None:
    """One Google place, or None when it is not something we can place."""
    location = payload.get("location") or {}
    lat, lng = location.get("latitude"), location.get("longitude")
    ref = payload.get("id")
    name = (payload.get("displayName") or {}).get("text")
    if lat is None or lng is None or not ref or not name:
        return None

    kind = next(
        (_TYPE_KIND[t] for t in payload.get("types", ()) if t in _TYPE_KIND), None
    )
    if kind is None:
        return None

    return ProviderPlace(
        provider_ref=ref,
        name=name,
        kind=kind,
        lat=lat,
        lng=lng,
        address=payload.get("formattedAddress"),
        summary=(payload.get("editorialSummary") or {}).get("text"),
        price_level=_PRICE_LEVELS.get(payload.get("priceLevel", "")),
        hours=_opening_hours(payload.get("regularOpeningHours") or {}),
    )


class GooglePlaces:
    """The live provider. Holds no state beyond its client."""

    name = "google"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _request(self, method: str, url: str, **kw) -> dict:
        key = api_key()
        if not key:
            raise ProviderUnavailable("GOOGLE_MAPS_API_KEY is not set")
        try:
            if self._client is not None:
                response = await self._client.request(method, url, **kw)
            else:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    response = await client.request(method, url, **kw)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Google request failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError("Google returned a body we cannot parse") from exc

    async def geocode(self, query: str) -> GeocodeResult | None:
        payload = await self._request(
            "GET", _GEOCODE_URL, params={"address": query, "key": api_key()}
        )
        status = payload.get("status")
        if status == "ZERO_RESULTS":
            return None
        if status != "OK":
            # A non-OK status is the provider telling us the call failed;
            # treating it as "no such place" would cache an outage as absence.
            raise ProviderError(f"Geocoding returned {status!r}")
        results = payload.get("results") or []
        if not results:
            return None
        best = results[0]
        point = (best.get("geometry") or {}).get("location") or {}
        if "lat" not in point or "lng" not in point:
            raise ProviderError("Geocoding result carried no location")
        return GeocodeResult(
            query=query,
            name=best.get("formatted_address") or query,
            lat=point["lat"],
            lng=point["lng"],
        )

    async def search_nearby(self, query: NearbyQuery) -> list[ProviderPlace]:
        kinds = query.kinds or tuple(_KIND_TYPES)
        included = [t for k in kinds for t in _KIND_TYPES[k]]
        payload = await self._request(
            "POST",
            _PLACES_URL,
            headers={
                "X-Goog-Api-Key": api_key(),
                "X-Goog-FieldMask": _FIELD_MASK,
                "Content-Type": "application/json",
            },
            json={
                "includedTypes": included,
                "maxResultCount": query.max_results,
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": query.lat, "longitude": query.lng},
                        "radius": float(query.radius_m),
                    }
                },
            },
        )
        found = (_to_place(p) for p in payload.get("places") or [])
        return [p for p in found if p is not None]
