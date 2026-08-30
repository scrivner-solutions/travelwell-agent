"""An in-memory provider, for tests and for running the app without a key.

Holds a fixed world and answers honestly about it: radius filtering and kind
filtering are real, so a test that asks for gyms within 500 m gets the same
shape of answer Google would give. What it must never do is invent a result
for a query it has nothing for -- the prototype's hardcoded Skokie fallback is
exactly the behaviour this replaces.
"""

from __future__ import annotations

import math

from app.services.places.ports import GeocodeResult, NearbyQuery, ProviderPlace

_METERS_PER_DEGREE = 111_320.0


class FakePlaces:
    name = "fake"

    def __init__(
        self,
        places: list[ProviderPlace] | None = None,
        geocodes: dict[str, GeocodeResult] | None = None,
    ) -> None:
        self.places = places or []
        self.geocodes = geocodes or {}
        self.calls: list[NearbyQuery] = []

    async def geocode(self, query: str) -> GeocodeResult | None:
        return self.geocodes.get(query.casefold())

    async def search_nearby(self, query: NearbyQuery) -> list[ProviderPlace]:
        self.calls.append(query)
        shrink = math.cos(math.radians(query.lat))
        out = []
        for p in self.places:
            if query.kinds and p.kind not in query.kinds:
                continue
            east = (p.lng - query.lng) * _METERS_PER_DEGREE * shrink
            north = (p.lat - query.lat) * _METERS_PER_DEGREE
            if math.hypot(east, north) <= query.radius_m:
                out.append(p)
        return out[: query.max_results]
