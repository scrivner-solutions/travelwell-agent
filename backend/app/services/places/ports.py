"""The places seam: what any venue provider must be able to do.

Two verbs, because Explore needs two things a cache cannot supply on its own:
resolve a destination to a point, and list venues around a point. Everything
else -- ranking, filtering, distance -- is ours and stays out of here.

Nothing in this file may mention Google, HTTP, or an API key. A provider that
answered from a municipal open-data dump would implement the same two methods,
and the moment the interface names one vendor it stops being a seam.

Written fresh rather than ported. `app/services/google_maps.py` is prototype
code -- one commit, synchronous `requests` inside an async app, a hardcoded
Skokie fallback when no key is set -- and it dies with the rest of the
prototype layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.db.models import PlaceKind


class ProviderError(RuntimeError):
    """The provider could not be reached or answered unusably.

    Not the same as an empty result. "No gyms within 2 km" is a successful
    call with nothing in it; this is a timeout, a 500, or a body we cannot
    parse. Only one of the two is worth retrying, and a cache that stored the
    difference away would record an outage as a fact about the neighbourhood.
    """


class ProviderUnavailable(ProviderError):
    """No credentials configured. Distinguished so a missing key reads as a
    missing key rather than as a destination with nothing in it."""


@dataclass(frozen=True)
class GeocodeResult:
    """A place name resolved to a point."""

    query: str
    name: str
    lat: float
    lng: float
    timezone: str | None = None


@dataclass(frozen=True)
class ProviderPlace:
    """One venue as the provider describes it, before it becomes a cache row.

    Deliberately not a `Place`: the ORM row carries our own `kind` taxonomy and
    a `fetched_at` the provider knows nothing about, and building the model
    here would put persistence inside the client.
    """

    provider_ref: str
    name: str
    kind: PlaceKind
    lat: float
    lng: float
    address: str | None = None
    summary: str | None = None
    price_level: int | None = None
    day_pass_cents: int | None = None
    amenities: tuple[str, ...] = ()
    # Per-weekday open/close minutes from midnight, local: {"mon": [360, 1320]}.
    # The shape the seed writes and the planner reads; a client that invents a
    # different one silently breaks candidate selection rather than failing.
    hours: dict[str, list[int]] | None = None
    photo_url: str | None = None


@dataclass(frozen=True)
class NearbyQuery:
    """Where to look and for what."""

    lat: float
    lng: float
    radius_m: int
    kinds: tuple[PlaceKind, ...] = ()
    text: str | None = None
    max_results: int = 20


@runtime_checkable
class PlacesProvider(Protocol):
    """What Explore needs from the outside world, and nothing more."""

    name: str

    async def geocode(self, query: str) -> GeocodeResult | None:
        """Resolve free text to a point, or None when nothing matches.

        None is a real answer -- "no such place" -- and is not an error.
        """
        ...

    async def search_nearby(self, query: NearbyQuery) -> list[ProviderPlace]:
        """Venues around a point. An empty list means none, not a failure."""
        ...


@dataclass
class Registry:
    """Providers by name, so adding a real one is an entry rather than a
    rewrite of every call site."""

    providers: dict[str, PlacesProvider] = field(default_factory=dict)

    def register(self, provider: PlacesProvider) -> None:
        self.providers[provider.name] = provider

    def get(self, name: str) -> PlacesProvider:
        try:
            return self.providers[name]
        except KeyError:
            raise ProviderUnavailable(f"No places provider named {name!r}") from None
