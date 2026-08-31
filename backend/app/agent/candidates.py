"""Which places could go in which window, and the order code thinks they go in.

The determinism ledger splits this cleanly. Hard filters are boolean, so they
are code's: open at the time, inside the day-pass cap, inside the price level,
and for a meal, meeting a dietary requirement. What is left - which of the
survivors, where in the window, in what order, and why in the user's words - has
no closed form, and this module never touches it.

The pre-rank exists for exactly one reason. `candidates` is the only elastic
section of the context budget, so when the budget bites, truncation has to drop
the *worst* candidates rather than arbitrary ones. It is not a recommendation:
the model still does the ranking only it can do, which is the tradeoff among
candidates that all passed the same hard filters.

Distance and hours are computed here rather than asked of the model, because
`places` is already authoritative for both and a model that can write them is a
model that can get them wrong invisibly.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Sequence

from app.agent.schemas import Candidate, ContextPreferences, ContextWindow
from app.db.models import Place

# Brisk city walking. One constant, so a route service replacing it later has
# one call site rather than a scattering of magic numbers.
WALK_METRES_PER_MINUTE = 80.0

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Places we treat as somewhere you eat; everything else is somewhere you move.
_FOOD_KINDS = frozenset({"food", "restaurant"})

# Tokens for `Candidate.unknown` and the `meta.degraded` counts. Named after the
# constraint that could not be checked, not after the missing column, because
# the reader cares which promise is unverified.
UNKNOWN_DAY_PASS = "day_pass"
UNKNOWN_PRICE_LEVEL = "price_level"
UNKNOWN_DIETARY = "dietary"


def haversine_metres(
    lat_a: float, lng_a: float, lat_b: float, lng_b: float
) -> float:
    radius = 6_371_000.0
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lambda = math.radians(lng_b - lng_a)
    h = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(h))


def walk_minutes(
    origin: tuple[float, float] | None, place: Place
) -> int | None:
    """Straight-line walking minutes, or None when either end has no location.

    Straight line rather than routed: it is a pre-rank input and a display
    figure, not a promise, and every routed alternative is a network call per
    candidate per window.
    """
    if origin is None or place.lat is None or place.lng is None:
        return None
    metres = haversine_metres(origin[0], origin[1], place.lat, place.lng)
    return max(1, round(metres / WALK_METRES_PER_MINUTE))


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _day_hours(place: Place, window: ContextWindow) -> tuple[int, int] | None:
    hours = place.hours or {}
    span = hours.get(_WEEKDAYS[window.day.weekday()])
    if not span or len(span) != 2:
        return None
    opens, closes = int(span[0]), int(span[1])
    return (opens, closes) if closes > opens else None


def is_open_during(place: Place, window: ContextWindow) -> bool:
    """Open for the whole window. Unknown hours count as open.

    Unknown means the cache has not been filled for that place yet, and
    excluding it would silently shrink the decision space for a reason that has
    nothing to do with the place.
    """
    span = _day_hours(place, window)
    if span is None:
        return True
    opens, closes = span
    return opens <= _to_minutes(window.start) and _to_minutes(window.end) <= closes


def open_label(place: Place, window: ContextWindow) -> str | None:
    span = _day_hours(place, window)
    if span is None:
        return None
    opens, closes = span
    return f"{opens // 60:02d}:{opens % 60:02d}-{closes // 60:02d}:{closes % 60:02d}"


def dietary_unknown(place: Place) -> bool:
    """Whether this place's dietary tags are absent rather than known-absent.

    `places.amenities` is NOT NULL with a `'{}'` default, so the column cannot
    say "we never learned this" - an empty list means both "checked, has none"
    and "never filled". Under decision 8 the tie breaks toward unknown, because
    reading a never-filled row as known-none is what silently empties every meal
    slot for anyone with a dietary preference. When the column gains a real
    unknown, this is the one predicate that changes.
    """
    return not place.amenities


def unknown_constraints(place: Place, prefs: ContextPreferences) -> tuple[str, ...]:
    """Which hard constraints this place's data cannot answer.

    Only constraints the user actually set: a missing price on a place nobody
    asked to price-cap is not an unknown, it is an irrelevance.
    """
    unknown: list[str] = []
    if prefs.day_pass_max_cents is not None and place.day_pass_cents is None:
        unknown.append(UNKNOWN_DAY_PASS)
    if prefs.price_level_max is not None and place.price_level is None:
        unknown.append(UNKNOWN_PRICE_LEVEL)
    if str(place.kind) in _FOOD_KINDS and prefs.dietary and dietary_unknown(place):
        unknown.append(UNKNOWN_DIETARY)
    return tuple(unknown)


def passes_hard_filters(place: Place, prefs: ContextPreferences) -> bool:
    """Budget, price level, dietary. Mirrors `_hard_preference_violations`.

    The two are deliberately the same three checks: this one builds the
    candidate set, that one asserts the model stayed inside it, and if they ever
    disagree the verifier says so instead of a bad plan shipping.

    **A hard filter fails only on known-bad** (decision 8). Unknown is admitted
    and carried in `Candidate.unknown` so a surface can say "price not listed",
    because a filter that excludes on missing data removes exactly the rows a
    half-filled cache is missing - silently, and with no way to tell an empty
    result from a genuinely empty city.
    """
    if (
        prefs.day_pass_max_cents is not None
        and place.day_pass_cents is not None
        and place.day_pass_cents > prefs.day_pass_max_cents
    ):
        return False
    if (
        prefs.price_level_max is not None
        and place.price_level is not None
        and place.price_level > prefs.price_level_max
    ):
        return False
    if (
        str(place.kind) in _FOOD_KINDS
        and prefs.dietary
        and not dietary_unknown(place)
        and not set(prefs.dietary) & set(place.amenities)
    ):
        return False
    return True


def preference_matches(place: Place, prefs: ContextPreferences) -> int:
    """How many of the user's soft signals this place carries.

    Soft on purpose: a hotel gym with a treadmill is still worth offering to
    someone who asked for a pool, it just ranks below the pool.
    """
    wanted = {*prefs.facilities, *prefs.workout_kinds, *prefs.dietary}
    return len(wanted & set(place.amenities or ()))


def _prerank_key(
    place: Place, prefs: ContextPreferences, minutes: int | None
) -> tuple[int, int, int]:
    # Negated match count so a plain ascending sort puts the best first.
    return (
        -preference_matches(place, prefs),
        minutes if minutes is not None else 999,
        place.day_pass_cents if place.day_pass_cents is not None else 0,
    )


def build_candidates(
    places: Iterable[Place],
    windows: Sequence[ContextWindow],
    prefs: ContextPreferences,
    origin: tuple[float, float] | None,
) -> tuple[list[Candidate], dict[str, uuid.UUID]]:
    """Projected candidates in pre-rank order, plus the id map Bind resolves.

    A place eligible for no window is dropped rather than carried with an empty
    `window_ids`: the model cannot use it, so it is pure context budget.
    """
    scored: list[tuple[tuple[int, int, int], Place, list[str], int | None]] = []
    for place in places:
        if not passes_hard_filters(place, prefs):
            continue
        minutes = walk_minutes(origin, place)
        window_ids = [w.id for w in windows if is_open_during(place, w)]
        if not window_ids:
            continue
        scored.append((_prerank_key(place, prefs, minutes), place, window_ids, minutes))

    scored.sort(key=lambda row: row[0])

    candidates: list[Candidate] = []
    id_map: dict[str, uuid.UUID] = {}
    for index, (_, place, window_ids, minutes) in enumerate(scored, start=1):
        candidate_id = f"c{index}"
        id_map[candidate_id] = place.place_id
        first = next(w for w in windows if w.id == window_ids[0])
        candidates.append(
            Candidate(
                id=candidate_id,
                kind="meal" if str(place.kind) in _FOOD_KINDS else "activity",
                window_ids=window_ids,
                name=place.name,
                summary=place.summary,
                walk_minutes=minutes,
                day_pass_cents=place.day_pass_cents,
                price_level=place.price_level,
                amenities=list(place.amenities or ()),
                unknown=list(unknown_constraints(place, prefs)),
                open=open_label(place, first),
            )
        )
    return candidates, id_map
