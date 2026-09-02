"""What stands between a burst of map views and a donated server.

Measured on staging 2026-09-02: one person panning the expanded map sent five
concurrent Overpass queries into a limit of two slots per IP, each retried
three times, and most came back empty after 70-88 s. Nothing here is about
speed; it is about never asking the provider the same thing twice at once,
never asking it for more than it will run for us, and not asking again for a
minute after it has said no.

Per process, on purpose. Cloud Run runs one warm instance and at most two, so
a shared lock would buy little and cost a round trip. Nothing here is a
correctness guarantee -- the database upsert is what keeps two instances from
disagreeing -- it is a courtesy that happens to make the map fast.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from . import overpass
from .geometry import Area, Basemap
from .overpass import BasemapBusy, BasemapUnavailable

# overpass-api.de answers `Rate limit: 2` on /api/status: two queries at a
# time per IP, and Cloud Run's egress IP is shared with strangers. Two is the
# most we can use without turning our own second request into a refusal.
PROVIDER_SLOTS = 2

# The server itself holds a request for up to 15 s waiting for a slot before
# refusing it. Waiting longer here would only serve a view the user has left.
QUEUE_WAIT_S = 15.0

# After a refusal, a retry within the minute is what the cool-down punishes.
REFUSED_FOR_S = 60.0


@dataclass
class Gate:
    slots: asyncio.Semaphore
    inflight: dict[str, asyncio.Task[Basemap]] = field(default_factory=dict)
    refused_at: dict[str, float] = field(default_factory=dict)


_gates: dict[asyncio.AbstractEventLoop, Gate] = {}
logger = logging.getLogger(__name__)


def gate() -> Gate:
    """One gate per event loop: a semaphore binds to the loop it first waits
    on, and the test suite makes a fresh loop per test."""
    loop = asyncio.get_running_loop()
    found = _gates.get(loop)
    if found is None:
        for dead in [known for known in _gates if known.is_closed()]:
            del _gates[dead]
        found = _gates[loop] = Gate(asyncio.Semaphore(PROVIDER_SLOTS))
    return found


async def _within_slots(area: Area, this: Gate) -> Basemap:
    try:
        await asyncio.wait_for(this.slots.acquire(), QUEUE_WAIT_S)
    except TimeoutError as exc:
        raise BasemapBusy("no provider slot free within the wait") from exc
    try:
        return await overpass.fetch(area)
    finally:
        this.slots.release()


async def _lead(area: Area, this: Gate) -> Basemap:
    started = time.monotonic()
    try:
        drawn = await _within_slots(area, this)
    except BasemapUnavailable as exc:
        this.refused_at[area.key] = time.monotonic()
        logger.warning(
            "basemap %s refused after %.1fs: %s", area.key, time.monotonic() - started, exc
        )
        raise
    this.refused_at.pop(area.key, None)
    logger.info("basemap %s fetched in %.1fs", area.key, time.monotonic() - started)
    return drawn


async def fetch(area: Area) -> tuple[Basemap, bool]:
    """The provider's answer for one cell, shared with anyone else asking
    for it right now. The flag says whether this caller led the fetch, so
    the one row write happens once rather than once per waiter.

    Raises `BasemapUnavailable` exactly as `overpass.fetch` does, and also
    for a cell refused less than `REFUSED_FOR_S` ago, without a request."""
    this = gate()
    refused = this.refused_at.get(area.key)
    if refused is not None and time.monotonic() - refused < REFUSED_FOR_S:
        raise BasemapUnavailable("provider refused this cell a moment ago")
    task = this.inflight.get(area.key)
    if task is not None:
        # Shielded: a waiter whose own request is cancelled must not take
        # the leader's fetch down with it.
        return await asyncio.shield(task), False
    task = asyncio.create_task(_lead(area, this))
    this.inflight[area.key] = task
    task.add_done_callback(lambda _: this.inflight.pop(area.key, None))
    return await asyncio.shield(task), True
