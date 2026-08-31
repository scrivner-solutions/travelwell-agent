"""Google as a places provider: Places API (New), authenticated with ADC.

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

import asyncio

import google.auth
import google.auth.transport.requests
import httpx
from google.auth.exceptions import DefaultCredentialsError, GoogleAuthError

from app.db.models import PlaceKind
from app.services.places.ports import (
    GeocodeResult,
    NearbyQuery,
    ProviderError,
    ProviderPlace,
    ProviderUnavailable,
)

_PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
# Geocoding v3 accepts an API key and nothing else, and v4 is a different host
# and a different service to enable, so free text resolves through Places.
_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
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

# editorialSummary prices the whole request at the top tier; trimming it is a
# three-file change, not one. See ARCHITECTURE.md, "Places provider".
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

# Two fields only, which keeps text search in the cheapest SKU tier.
_GEOCODE_FIELD_MASK = "places.formattedAddress,places.location"


# Application Default Credentials, not an API key. Resolved once per process
# and refreshed in place; google-auth is synchronous, so both the lookup and the
# refresh go through a thread to keep them off the event loop.
_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)
_credentials = None
_credentials_lock = asyncio.Lock()


async def auth_headers() -> dict[str, str]:
    """Bearer token for Maps Platform, plus the quota project when ADC has one.

    A laptop needs `gcloud auth application-default login` first; there is no
    key to paste into .env any more.
    """
    global _credentials
    async with _credentials_lock:
        try:
            if _credentials is None:
                _credentials, _ = await asyncio.to_thread(
                    google.auth.default, scopes=_SCOPES
                )
            if not _credentials.valid:
                await asyncio.to_thread(
                    _credentials.refresh, google.auth.transport.requests.Request()
                )
        except DefaultCredentialsError as exc:
            raise ProviderUnavailable(
                "No Google credentials: run `gcloud auth application-default login`"
            ) from exc
        except GoogleAuthError as exc:
            # Credentials exist but would not mint a token. That is an outage,
            # not an unconfigured install, and the two must not read alike.
            raise ProviderError(f"Google credentials would not refresh: {exc}") from exc

        headers = {"Authorization": f"Bearer {_credentials.token}"}
        # Only user ADC carries a quota project. On Cloud Run it is None and the
        # header must stay off, because sending it needs serviceusage.services.use.
        if project := getattr(_credentials, "quota_project_id", None):
            headers["X-Goog-User-Project"] = project
        return headers


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
        headers = {**(kw.pop("headers", None) or {}), **await auth_headers()}
        try:
            if self._client is not None:
                response = await self._client.request(
                    method, url, headers=headers, **kw
                )
            else:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    response = await client.request(
                        method, url, headers=headers, **kw
                    )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Google request failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError("Google returned a body we cannot parse") from exc

    async def geocode(self, query: str) -> GeocodeResult | None:
        """Free text to a point, via Places text search.

        An outage still cannot read as absence: it arrives as a non-2xx and
        becomes a ProviderError before this sees a body. Only a 200 carrying no
        place means no such place.
        """
        payload = await self._request(
            "POST",
            _TEXT_SEARCH_URL,
            headers={
                "X-Goog-FieldMask": _GEOCODE_FIELD_MASK,
                "Content-Type": "application/json",
            },
            # We read the first result regardless, so the cap is a courtesy.
            json={"textQuery": query, "maxResultCount": 1},
        )
        results = payload.get("places") or []
        if not results:
            return None
        best = results[0]
        point = best.get("location") or {}
        if "latitude" not in point or "longitude" not in point:
            raise ProviderError("Geocoding result carried no location")
        return GeocodeResult(
            query=query,
            name=best.get("formattedAddress") or query,
            lat=point["latitude"],
            lng=point["longitude"],
        )

    async def search_nearby(self, query: NearbyQuery) -> list[ProviderPlace]:
        kinds = query.kinds or tuple(_KIND_TYPES)
        included = [t for k in kinds for t in _KIND_TYPES[k]]
        payload = await self._request(
            "POST",
            _PLACES_URL,
            headers={
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
