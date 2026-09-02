"""Explore: cached places near a trip, ranked against the user's profile.

Reads the `places` cache and never calls a provider inline. A request that
went out to Google would make the map's speed depend on a third party and
would bill per pan of the map; filling the cache is a separate job.

The trip is a required parameter rather than an inferred "current trip". The
client already decides which trip is in focus (frontend/src/lib/trips.ts), and
a second definition on the server would eventually disagree with it.
"""

import math
import uuid
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import ApiRoute, CurrentUser, SessionDep
from app.api.problems import Problem
from app.api.schemas import (
    BasemapOut,
    ExploreAnchorOut,
    ExploreKindOut,
    ExploreOut,
    ExplorePlaceOut,
    ExploreRouteOut,
    ExploreRouteStopOut,
    ResolvedLocationOut,
    explore_place_to_out,
    item_face,
)
from app.api.trips import (
    HIDDEN_ITEM_STATUSES,
    current_plan,
    local_today,
    owned_trip,
)
from app.db.models import Place, PlaceKind, Trip, UserPreferences
from app.services.basemap import ATTRIBUTION, basemap_for, bucket_radius, normalize
from app.services.places import default_provider
from app.services.places.matching import (
    meters_between,
    rank_places,
    walk_minutes_between,
)
from app.services.places.ports import ProviderError, ProviderUnavailable

router = APIRouter(tags=["explore"], route_class=ApiRoute)

# Lodging is the anchor, not a suggestion: the hotel is where the user already
# is. The brief's four chips are the other four kinds.
_CARD_KINDS = tuple(k for k in PlaceKind if k is not PlaceKind.lodging)

_METRES_PER_DEGREE_LAT = 111_320.0


def _bounding_box(lat: float, lng: float, radius_m: int) -> tuple[float, float, float, float]:
    """A box that contains the circle, for the SQL prefilter.

    Cheap and index-friendly, and it over-selects at the corners; the exact
    haversine check afterwards is what actually enforces the radius.
    """
    d_lat = radius_m / _METRES_PER_DEGREE_LAT
    # Longitude degrees shrink toward the poles. Clamped so a trip near a pole
    # widens the box instead of dividing by ~zero.
    shrink = max(math.cos(math.radians(lat)), 0.01)
    d_lng = radius_m / (_METRES_PER_DEGREE_LAT * shrink)
    return lat - d_lat, lat + d_lat, lng - d_lng, lng + d_lng


def _matches_text(place: Place, query: str) -> bool:
    """Free text against the cache, not a provider search.

    Name, summary and address, because those are the three the card shows: a
    match the user cannot see in the result reads as a bug.
    """
    needle = query.casefold()
    haystack = (place.name, place.summary or "", place.address or "")
    return any(needle in field.casefold() for field in haystack)


_NO_ROUTE = ExploreRouteOut(stops=[], total_minutes=None)


async def _todays_route(
    session: SessionDep, trip: Trip, anchor: ExploreAnchorOut
) -> ExploreRouteOut:
    """Today's decided stops as a path from the anchor.

    Plotted from `item_face`, the same helper the timeline titles an item with,
    so the line cannot draw a different option than the one on the card.

    Legs are anchor-to-first then stop-to-stop, which is the order the day is
    walked; the shared straight-line pace applies, so they under-read exactly
    where the card's own walk time does.
    """
    assert anchor.lat is not None and anchor.lng is not None
    plan = await current_plan(session, trip.trip_id)
    if plan is None:
        return _NO_ROUTE

    tz = ZoneInfo(trip.timezone)
    today = local_today(trip.timezone)
    faces = [
        item_face(item)
        for item in sorted(
            (
                item
                for item in plan.items
                if item.status not in HIDDEN_ITEM_STATUSES
                and item.scheduled_start.astimezone(tz).date() == today
            ),
            key=lambda item: item.scheduled_start,
        )
    ]
    wanted = {f.place_id for f in faces if f is not None and f.place_id is not None}
    if not wanted:
        return _NO_ROUTE

    located = {
        p.place_id: p
        for p in (
            await session.execute(select(Place).where(Place.place_id.in_(wanted)))
        )
        .scalars()
        .all()
        if p.lat is not None and p.lng is not None
    }

    stops = [
        ExploreRouteStopOut(
            name=anchor.name,
            lat=anchor.lat,
            lng=anchor.lng,
            is_anchor=True,
            walk_minutes=None,
        )
    ]
    total = 0
    for face in faces:
        if face is None or face.place_id not in located:
            continue
        place = located[face.place_id]
        previous = stops[-1]
        minutes = walk_minutes_between(
            previous.lat, previous.lng, place.lat, place.lng
        )
        total += minutes
        stops.append(
            ExploreRouteStopOut(
                name=face.display_name,
                lat=place.lat,
                lng=place.lng,
                is_anchor=False,
                walk_minutes=minutes,
            )
        )

    # The anchor on its own is a point, not a route worth a line.
    if len(stops) == 1:
        return _NO_ROUTE
    return ExploreRouteOut(stops=stops, total_minutes=total)


def trip_anchor(trip: Trip) -> ExploreAnchorOut | None:
    """The point this trip's map is measured and drawn from.

    A function rather than two copies because the basemap has to be centred on
    whatever the pins are centred on. Two definitions of "where is this trip"
    would eventually disagree, and the symptom would be a city drawn next to
    its own hotel.
    """
    if trip.hotel_lat is not None and trip.hotel_lng is not None:
        return ExploreAnchorOut(
            name=trip.hotel_name or "Your hotel",
            is_hotel=True,
            lat=trip.hotel_lat,
            lng=trip.hotel_lng,
        )
    if trip.destination_lat is not None and trip.destination_lng is not None:
        return ExploreAnchorOut(
            name=trip.destination_city,
            is_hotel=False,
            lat=trip.destination_lat,
            lng=trip.destination_lng,
        )
    return None


@router.get("/explore")
async def explore(
    user: CurrentUser,
    session: SessionDep,
    trip_id: uuid.UUID,
    category: PlaceKind | None = None,
    query: str | None = Query(default=None, max_length=120),
    radius_m: int = Query(default=8000, ge=250, le=50_000),
) -> ExploreOut:
    trip = await owned_trip(session, user, trip_id)

    anchor = trip_anchor(trip)
    if anchor is None:
        # No point to measure from and no city column on `places`, so there is
        # no honest way to pick which cached rows belong to this trip.
        return ExploreOut(
            trip_id=trip.trip_id,
            anchor=None,
            radius_m=radius_m,
            kinds=[],
            places=[],
            route=_NO_ROUTE,
        )

    assert anchor.lat is not None and anchor.lng is not None
    min_lat, max_lat, min_lng, max_lng = _bounding_box(
        anchor.lat, anchor.lng, radius_m
    )
    rows = (
        await session.execute(
            select(Place).where(
                Place.kind.in_(_CARD_KINDS),
                Place.lat.is_not(None),
                Place.lng.is_not(None),
                Place.lat.between(min_lat, max_lat),
                Place.lng.between(min_lng, max_lng),
            )
        )
    ).scalars().all()

    in_radius = [
        p
        for p in rows
        if meters_between(anchor.lat, anchor.lng, p.lat, p.lng) <= radius_m
    ]

    # Counted before the kind filter, so switching chips never moves the other
    # chips' numbers under the user.
    counts = dict.fromkeys(_CARD_KINDS, 0)
    for p in in_radius:
        counts[p.kind] += 1
    kinds = [ExploreKindOut(kind=k, count=counts[k]) for k in _CARD_KINDS]

    prefs = await session.get(UserPreferences, user.user_id)
    selected = [p for p in in_radius if category is None or p.kind is category]
    if query:
        selected = [p for p in selected if _matches_text(p, query)]
    ranked = rank_places(selected, prefs, anchor.lat, anchor.lng)

    places: list[ExplorePlaceOut] = [explore_place_to_out(r) for r in ranked]
    return ExploreOut(
        trip_id=trip.trip_id,
        anchor=anchor,
        radius_m=radius_m,
        kinds=kinds,
        places=places,
        route=await _todays_route(session, trip, anchor),
    )


# How far from the trip's own anchor a basemap may be asked for. Wide enough
# for any view a user reaches by panning a city; narrow enough that the
# endpoint is not a worldwide proxy for a donated server, which is what an
# unbounded centre would make of it for anyone with a demo login.
BASEMAP_MAX_OFFSET_M = 30_000


@router.get("/explore/basemap")
async def explore_basemap(
    user: CurrentUser,
    session: SessionDep,
    trip_id: uuid.UUID,
    radius_m: int = Query(default=2000, ge=250, le=20_000),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
) -> BasemapOut:
    """Street geometry for the area this trip's map covers.

    Its own endpoint rather than a field on `/explore` for two reasons. It
    changes on a scale of years while the rest of that payload changes per tap,
    so bundling them would re-send a city every time a chip is pressed. And it
    is the one part of the surface that may legitimately arrive late or not at
    all: the map renders on plain ground without it, exactly as it did before.

    `radius_m` is the client's plot radius, which is computed from what is on
    screen. The server buckets it, so filtering a category usually reuses the
    area already cached rather than fetching a slightly different one.

    `lat`/`lng` centre the area somewhere other than the trip's anchor: the
    expanded map asks for finer geometry around wherever it has been zoomed
    to. Both or neither, and never far from the anchor.
    """
    if (lat is None) != (lng is None):
        raise Problem(422, "lat and lng go together", "basemap_centre_incomplete")

    trip = await owned_trip(session, user, trip_id)
    anchor = trip_anchor(trip)
    if anchor is None or anchor.lat is None or anchor.lng is None:
        # Same silence as `/explore` itself: with no point to centre on there
        # is no area to draw, and guessing one would draw the wrong city.
        return BasemapOut(
            radius_m=bucket_radius(radius_m),
            lat=None,
            lng=None,
            attribution=ATTRIBUTION,
            roads_major=[],
            roads_minor=[],
            water=[],
            parks=[],
            buildings=[],
        )

    if lat is not None and lng is not None:
        if meters_between(anchor.lat, anchor.lng, lat, lng) > BASEMAP_MAX_OFFSET_M:
            raise Problem(
                422, "Centre is too far from this trip", "basemap_centre_too_far"
            )
        area = normalize(lat, lng, radius_m)
    else:
        area = normalize(anchor.lat, anchor.lng, radius_m)

    drawn = await basemap_for(session, area)
    return BasemapOut(
        radius_m=area.radius_m,
        lat=area.lat,
        lng=area.lng,
        attribution=ATTRIBUTION,
        roads_major=drawn.roads_major,
        roads_minor=drawn.roads_minor,
        water=drawn.water,
        parks=drawn.parks,
        buildings=drawn.buildings,
    )


@router.get("/geocode")
async def geocode(
    user: CurrentUser,
    query: str = Query(min_length=1, max_length=200),
) -> ResolvedLocationOut:
    """Resolve free text to a point.

    Written fresh rather than ported: the prototype's /resolve_location is
    synchronous and answers with hardcoded Skokie coordinates when no key is
    configured, which is worse than an error because the caller cannot tell.
    Here the three outcomes stay distinct -- no such place is 404, no key is
    503, and a provider failure is 502 -- so nobody plans a trip around a
    fallback.
    """
    try:
        found = await default_provider().geocode(query)
    except ProviderUnavailable as exc:
        raise Problem(
            503, "Location lookup is not configured", "geocoding_unavailable"
        ) from exc
    except ProviderError as exc:
        raise Problem(502, "Location lookup failed", "geocoding_failed") from exc

    if found is None:
        raise Problem(404, "No such place", "location_not_found")

    return ResolvedLocationOut(
        query=found.query, name=found.name, lat=found.lat, lng=found.lng,
        timezone=found.timezone,
    )
