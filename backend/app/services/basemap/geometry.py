"""Areas, and the rounding that makes two nearby requests one cache entry.

Kept apart from the fetching so the key and the geometry cannot disagree:
`normalize()` returns the centre the key is built from *and* the centre the
provider is asked about, and nothing else may construct either.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import timedelta

METERS_PER_DEGREE_LAT = 111_320.0

# ODbL. Travels with the data through every layer rather than being a string a
# renderer is trusted to remember, because the one that forgets is the one that
# ships.
ATTRIBUTION = "© OpenStreetMap contributors"

# Buckets rather than the caller's exact radius. Explore's plot radius is
# computed from its contents, so it moves whenever a category chip hides the
# furthest pin; keying the cache on it would refetch the same city on every tap.
# Roughly geometric. Coarser steps shared more areas between trips, but the
# ladder is climbed by rounding *up*: a doubling step means a 4.5 km map
# fetching an 8 km one, four times the geometry for none of the picture.
_RADIUS_BUCKETS = (750, 1_000, 1_500, 2_000, 3_000, 4_000, 5_500, 8_000, 11_000, 16_000)

# Above this, secondary and tertiary roads are not asked for at all. At 5.5 km
# the map is drawing 34 m to the pixel, where that tier stops being streets and
# becomes a grey wash -- and asking a donated server to compute a wash costs it
# minutes. The parser's own ceiling still applies below this.
MINOR_ROAD_MAX_RADIUS = 5_500

# Buildings are asked for only at the closest buckets. At 2 km the map draws
# 12.5 m to the pixel, where a footprint is a few pixels and a block reads as a
# block; one step wider they are specks that add up to a grey haze over the
# streets, which is worse than nothing and costs the most bytes of any layer.
BUILDING_MAX_RADIUS = 2_000

# Street grids do not move. The long window is the whole reason one fetch per
# city is enough, and a shorter one would only add load to a donated server.
_DEFAULT_TTL_DAYS = 180


def fetch_enabled() -> bool:
    """Deployment-wide ceiling, matching the places layer's shape.

    Off means the map falls back to plain ground rather than erroring: geography
    is an enrichment, and a basemap that could not be fetched must never be the
    reason Explore fails to render.
    """
    return os.getenv("BASEMAP_FETCH_ENABLED", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def ttl() -> timedelta:
    raw = os.getenv("BASEMAP_TTL_DAYS", "").strip()
    try:
        days = int(raw)
    except ValueError:
        days = 0
    return timedelta(days=days if days > 0 else _DEFAULT_TTL_DAYS)


def bucket_radius(radius_m: float) -> int:
    for bucket in _RADIUS_BUCKETS:
        if radius_m <= bucket:
            return bucket
    return _RADIUS_BUCKETS[-1]


# The Explore map band. Only used to pick a rounding step, so it does not have
# to track the CSS exactly -- being wrong by a factor of two costs bytes, not
# correctness.
_PLOT_PX = 320


@dataclass(frozen=True)
class Area:
    """A rounded centre and a bucketed radius: one row in `basemap_areas`."""

    lat: float
    lng: float
    radius_m: int

    @property
    def key(self) -> str:
        # Five places is a metre, far under the grid `snap()` puts centres on,
        # so two areas print the same key only when they are the same cell.
        return f"{self.lat:.5f},{self.lng:.5f},{self.radius_m}"

    def bbox(self) -> tuple[float, float, float, float]:
        """south, west, north, east -- the square that contains the circle.

        A box rather than a radius because Overpass answers a bounding box far
        more cheaply than `around:`, and the corners costing extra geometry is
        the trade that keeps a donated server fast.
        """
        dlat = self.radius_m / METERS_PER_DEGREE_LAT
        dlng = dlat / max(math.cos(math.radians(self.lat)), 0.01)
        return (self.lat - dlat, self.lng - dlng, self.lat + dlat, self.lng + dlng)

    def decimals(self) -> tuple[int, int]:
        """How many decimal places a stored coordinate is worth keeping.

        Half a pixel at the size this area is ever drawn at. Finer is bytes
        nobody can see; coarser and straight streets start to wobble. Decimal
        places rather than an arbitrary grid because the payload is almost
        entirely digits, and `41.8924` is four bytes shorter than the same
        point snapped to a 12.5 m lattice.
        """
        meters = self.radius_m / float(_PLOT_PX)
        dlat = meters / METERS_PER_DEGREE_LAT
        dlng = dlat / max(math.cos(math.radians(self.lat)), 0.01)
        # Nearest, not ceiling: ceiling always lands on the finer side of the
        # target, which is a factor of ten in bytes for a difference no screen
        # can show. Clamped because decimal places move in powers of ten and
        # the unclamped answer is wrong at both ends -- 3 places is a 111 m
        # step, over two pixels of stair-stepping on a straight avenue at the
        # widest bucket, and 6 would spend bytes on millimetres.
        return (
            min(5, max(4, round(-math.log10(dlat)))),
            min(5, max(4, round(-math.log10(dlng)))),
        )


@dataclass(frozen=True)
class Basemap:
    """The ground under the pins: what we draw, in degrees.

    Four lists rather than one tagged list because each is drawn with its own
    fill or stroke, and a renderer that had to re-derive the class per way
    would be re-doing on every frame what the fetch already worked out once.

    Each way is one flat `[lat, lng, lat, lng, ...]` run. Flat rather than
    nested pairs: the nesting cost more bytes than it explained.
    """

    roads_major: list[list[float]]
    roads_minor: list[list[float]]
    water: list[list[float]]
    parks: list[list[float]]
    buildings: list[list[float]]

    def __bool__(self) -> bool:
        return bool(
            self.roads_major
            or self.roads_minor
            or self.water
            or self.parks
            or self.buildings
        )


EMPTY = Basemap([], [], [], [], [])


def simplify(area: Area, points: list[tuple[float, float]]) -> list[float]:
    """Round to the area's resolution and drop the points that collapse.

    Most of the reduction happens here rather than in a line-simplification
    pass: at map scale an OSM way carries survey-grade vertices metres apart,
    and once they round to the same visible position all but one is noise.
    """
    lat_dp, lng_dp = area.decimals()
    out: list[float] = []
    previous: tuple[float, float] | None = None
    for lat, lng in points:
        rounded = (round(lat, lat_dp), round(lng, lng_dp))
        if rounded != previous:
            out.extend(rounded)
            previous = rounded
    return out


# The grid a centre is snapped to, as a share of the bucket radius. Half the
# radius means a view that pans across a city lands on a handful of cells per
# bucket rather than a fresh area per screen, and a 10 km city at the 2 km
# bucket is at most a hundred rows. The price is that a centre moves by up to a
# quarter of the radius, which the client allows for when it picks the bucket.
_GRID_SHARE = 0.5


def snap(lat: float, lng: float, radius_m: int) -> tuple[float, float]:
    """Nearest grid point for this bucket. Idempotent: a snapped centre snaps
    to itself, so a client that asks for the cell it was told about gets it."""
    step_lat = radius_m * _GRID_SHARE / METERS_PER_DEGREE_LAT
    snapped_lat = round(lat / step_lat) * step_lat
    # The longitude step is taken at the snapped latitude, not the requested
    # one, so every centre on a row shares one step and the rows line up.
    step_lng = step_lat / max(math.cos(math.radians(snapped_lat)), 0.01)
    return snapped_lat, round(lng / step_lng) * step_lng


def normalize(lat: float, lng: float, radius_m: float) -> Area:
    """The one place coordinates are rounded: onto a grid scaled to the bucket,
    so neighbouring views share one cached row instead of fetching it twice."""
    radius = bucket_radius(radius_m)
    snapped_lat, snapped_lng = snap(lat, lng, radius)
    return Area(snapped_lat, snapped_lng, radius)
