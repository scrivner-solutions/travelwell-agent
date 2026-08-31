"""OpenStreetMap geometry, over the Overpass API.

This module is the reason the Explore map can show streets at all, and it is
worth being precise about why it needs no credentials. OpenStreetMap publishes
the geometry itself -- road centrelines, water, parks -- under an open licence.
What costs money at Google or Mapbox is a *rendered tile*: someone else's
picture of that geometry, arriving pre-painted in someone else's colours. We
want the geometry and our own palette, which is the cheaper half.

Overpass is donated infrastructure, so the ceiling here is politeness rather
than budget: one bounding-box request per city per six months, a real
User-Agent, and a timeout that gives up rather than queueing.

Attribution is not optional. OSM is ODbL and the map must carry its credit;
`Basemap` reaching the client without it is a licence problem, not a polish
one, so the credit lives in the renderer beside the geometry.
"""

from __future__ import annotations

import asyncio
import os

import httpx

from .geometry import (
    BUILDING_MAX_RADIUS,
    MINOR_ROAD_MAX_RADIUS,
    Area,
    Basemap,
    simplify,
)

_MAJOR = {"motorway", "trunk", "primary"}
# Drawn as filled rings rather than strokes, and so subject to the smudge test.
_AREA_LAYERS = ("water", "parks", "buildings")
_MINOR = {"secondary", "tertiary"}

# A single request for all four layers. Splitting it would be four queue slots
# on a donated server to answer one question.
_QUERY = """[out:json][timeout:{timeout}];
(
  way["highway"~"^({roads})$"]({bbox});
  way["natural"="water"]({bbox});
  way["waterway"="riverbank"]({bbox});
  way["leisure"="park"]({bbox});{buildings}
);
out geom;"""

_BUILDINGS_CLAUSE = '\n  way["building"]({bbox});'

# Beyond this the payload stops being worth its bytes: minor roads are the
# first thing a reader stops distinguishing on a 320 px band, so they are the
# first thing dropped. Dropping the layer whole, rather than truncating it,
# keeps the map honestly coarse instead of half-drawn.
_MAX_POINTS = 60_000


_BACKOFF_SECONDS = 2.0


class BasemapUnavailable(RuntimeError):
    """The provider could not be reached or answered unusably.

    Not the same as an area with no geometry in it. Open sea really has no
    streets, and storing an outage as that fact would leave the map blank until
    someone deleted the row by hand.
    """


class BasemapBusy(BasemapUnavailable):
    """Overpass refused because it is loaded, not because the request is bad.

    A subclass so callers that only care that there is no geometry keep
    working, while the retry loop can tell the difference between "ask again in
    a moment" and "this will fail the same way every time".
    """


def endpoint() -> str:
    return os.getenv(
        "OVERPASS_URL", "https://overpass-api.de/api/interpreter"
    ).strip()


def _classify(element: dict) -> str | None:
    tags = element.get("tags") or {}
    highway = tags.get("highway")
    if highway in _MAJOR:
        return "roads_major"
    if highway in _MINOR:
        return "roads_minor"
    if tags.get("leisure") == "park":
        return "parks"
    if "building" in tags:
        return "buildings"
    if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
        return "water"
    return None


def _too_small(area: Area, way: list[float]) -> bool:
    """A ring smaller than a few pixels is a smudge, not a park."""
    lats, lngs = way[0::2], way[1::2]
    lat_dp, lng_dp = area.decimals()
    return (max(lats) - min(lats) < 3 * 10**-lat_dp) and (
        max(lngs) - min(lngs) < 3 * 10**-lng_dp
    )


def parse(area: Area, payload: dict) -> Basemap:
    """Split one Overpass answer into the four layers, simplified.

    Separated from the request so the shaping is testable without a network:
    every interesting decision here -- what counts as a major road, what is too
    small to draw -- is a judgement that deserves a test, and none of them need
    HTTP to exercise.
    """
    layers: dict[str, list[list[float]]] = {
        "roads_major": [], "roads_minor": [], "water": [], "parks": [], "buildings": [],
    }
    for element in payload.get("elements", []):
        layer = _classify(element)
        if layer is None:
            continue
        nodes = element.get("geometry") or []
        # Overpass omits geometry for ways clipped at the box edge it could not
        # resolve; a way with one end is not a line.
        points = [
            (node["lat"], node["lon"])
            for node in nodes
            if node.get("lat") is not None and node.get("lon") is not None
        ]
        if len(points) < 2:
            continue
        way = simplify(area, points)
        if len(way) < 4:
            continue
        if layer in _AREA_LAYERS and _too_small(area, way):
            continue
        layers[layer].append(way)

    total = sum(len(way) for ways in layers.values() for way in ways) // 2
    if total > _MAX_POINTS:
        layers["roads_minor"] = []
    return Basemap(**layers)


def build_query(area: Area) -> str:
    """The Overpass query for one area.

    Split out because which road classes it asks for is a real decision -- and
    one worth not getting wrong quietly, since the cost of asking for a tier
    that will be thrown away is paid by someone else's server.
    """
    south, west, north, east = area.bbox()
    classes = sorted(_MAJOR)
    if area.radius_m <= MINOR_ROAD_MAX_RADIUS:
        classes += sorted(_MINOR)
    bbox = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
    buildings = (
        _BUILDINGS_CLAUSE.format(bbox=bbox)
        if area.radius_m <= BUILDING_MAX_RADIUS
        else ""
    )
    return _QUERY.format(
        timeout=50, roads="|".join(classes), bbox=bbox, buildings=buildings
    )


# Overpass sheds load by refusing, so these are ordinary weather rather than
# faults: a slot is busy, or we asked for too much a moment ago.
_RETRY_STATUSES = frozenset({429, 502, 503, 504})
_ATTEMPTS = 3


async def _request(query: str) -> dict:
    """One POST. Separated so the retry policy above it can be tested without
    a network, and so a status we should retry cannot be mistaken here for a
    permanent failure."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            endpoint(),
            data={"data": query},
            headers={"User-Agent": "travelwell/1.0 (basemap; OSM data)"},
        )
        if response.status_code in _RETRY_STATUSES:
            raise BasemapBusy(f"overpass returned {response.status_code}")
        response.raise_for_status()
        return response.json()


async def fetch(area: Area) -> Basemap:
    query = build_query(area)
    for attempt in range(_ATTEMPTS):
        try:
            payload = await _request(query)
        except BasemapBusy:
            if attempt + 1 == _ATTEMPTS:
                raise
            # Linear, not exponential: three tries inside one request, and a
            # caller waiting on a page render will not sit through doubling.
            await asyncio.sleep(_BACKOFF_SECONDS * (attempt + 1))
        except (httpx.HTTPError, ValueError) as exc:
            raise BasemapUnavailable(str(exc)) from exc
        else:
            return parse(area, payload)
    raise BasemapUnavailable("exhausted retries")
