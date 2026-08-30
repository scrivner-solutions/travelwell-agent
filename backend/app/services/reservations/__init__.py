"""Reservation providers, and the one place that chooses between them.

Adding a real integration is meant to be exactly two edits: write a class
implementing ReservationPort in this package, and add it to `_BUILDERS` below.
Nothing outside this module names a provider class, so nothing outside it has
to change.

`opentable` is deliberately absent. The enum has carried the value since the
first migration and the seed labels rows with it, but nothing has ever called
OpenTable; leaving it unbuilt keeps that honest, and the error says so rather
than falling back to the simulator and quietly booking a table nobody asked
the real provider for.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime

from app.db.models import ReservationProvider
from app.services.reservations.external_link import ExternalLinkProvider
from app.services.reservations.links import booking_search_url
from app.services.reservations.ports import (
    BookingHandle,
    BookingRequest,
    BookingUpdate,
    ProviderError,
    ReservationPort,
)
from app.services.reservations.simulated import Rules, SimulatedProvider, Timings

__all__ = [
    "BookingHandle",
    "BookingRequest",
    "BookingUpdate",
    "ProviderError",
    "ReservationPort",
    "Rules",
    "SimulatedProvider",
    "Timings",
    "UnsupportedProvider",
    "booking_search_url",
    "default_provider",
    "provider_for",
]

Clock = Callable[[], datetime]

_BUILDERS: dict[ReservationProvider, Callable[[Clock | None], ReservationPort]] = {
    ReservationProvider.travelwell: lambda clock: SimulatedProvider(clock=clock),
    ReservationProvider.external_link: lambda clock: ExternalLinkProvider(clock=clock),
}


class UnsupportedProvider(LookupError):
    """No implementation is registered for that provider."""


def default_provider() -> ReservationProvider:
    """Which provider a new booking uses when the caller does not say.

    An env override rather than a constant so the external-link path can be
    demonstrated end to end, which matters: it is the only path that will still
    be correct on the day we meet a venue with no API.
    """
    raw = os.getenv("RESERVATION_PROVIDER", ReservationProvider.travelwell.value)
    try:
        return ReservationProvider(raw)
    except ValueError:
        return ReservationProvider.travelwell


def provider_for(
    provider: ReservationProvider, *, clock: Clock | None = None
) -> ReservationPort:
    builder = _BUILDERS.get(provider)
    if builder is None:
        raise UnsupportedProvider(
            f"No client is implemented for {provider.value}. "
            f"Implemented: {', '.join(sorted(p.value for p in _BUILDERS))}."
        )
    return builder(clock)
