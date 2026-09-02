"""Why a place suits this user, and how far away it is.

Pure functions over a Place and a UserPreferences row: no session, no network,
no clock. Explore ranks with them, and the planner writes the same
`matched_preferences` onto its options, so they live here rather than inside
either caller.

`UserPreferences` has always claimed to drive "Explore filters, plan ranking,
and the 'Matched from your profile' provenance chips". Until this module
nothing read it for any of the three: every `matched_preferences` value in the
database was hand-written in the demo seed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.db.models import Place, PlaceKind, UserPreferences

# Slug -> the label the user sees. Mirrors the chip labels in
# frontend/src/features/profile/ProfileScreen.tsx, because the contract carries
# rendered strings: ProvenanceSheet.tsx prints matched_preferences verbatim.
PREFERENCE_LABELS = {
    "vegetarian": "Vegetarian",
    "vegan": "Vegan",
    "gluten_free": "Gluten free",
    "swim": "Swim",
    "running": "Running",
    "strength": "Strength",
    "yoga": "Yoga",
    "pool": "Pool",
    "treadmill": "Treadmill",
    "weights": "Weights",
    "sauna": "Sauna",
    "showers": "Showers",
}

# An activity is what the user does; an amenity is what a venue has. The seed
# credits the YMCA with "Swim" because it has a pool, so the two vocabularies
# need this bridge rather than a shared namespace.
ACTIVITY_AMENITIES = {
    "swim": ("pool",),
    "running": ("treadmill", "track"),
    "strength": ("weights", "gym"),
    "yoga": ("studio",),
}

# Straight-line meters per minute at an unhurried walk. Deliberately a single
# constant: it is a placeholder for the Routes API, and one obvious number is
# easier to replace than a model that looks authoritative.
_METERS_PER_MINUTE = 75.0
_EARTH_RADIUS_M = 6_371_000.0

# Kinds where a day pass is a thing to have a price for. A restaurant with no
# day-pass price is not missing data, it is a restaurant, and saying so on its
# card would be noise dressed as honesty.
_DAY_PASS_KINDS = (PlaceKind.workout, PlaceKind.recovery)

# The words for a field the provider never filled in. DRAFT, pending
# ratification with the planner: Explore and the plan must describe the same
# missing field identically, or one venue reads as two different venues on two
# screens. Constants rather than literals so both surfaces import the string
# instead of each writing its own version of it.
# "Amenities" is our column, not the user's concern, so the note names what
# they actually asked about. Which one applies is decided by kind, because the
# same column answers a different question for a restaurant and for a gym.
UNKNOWN_DIETARY_OPTIONS = "Dietary options not listed"
UNKNOWN_FACILITIES = "Facilities not listed"
UNKNOWN_DAY_PASS = "Day-pass price not listed"
UNKNOWN_PRICE = "Price not listed"


def _label(slug: str) -> str:
    return PREFERENCE_LABELS.get(slug, slug.replace("_", " ").capitalize())


def price_label(price_level: int) -> str:
    """'$$ or less' for 2. The user set a ceiling, so the label says so."""
    return f"{'$' * price_level} or less"


def match_preferences(place: Place, prefs: UserPreferences | None) -> list[str]:
    """The profile chips this place earns, in the order the user set them.

    Order follows the preference lists rather than the place's amenities: the
    chips read as "what you asked for", so the user's own ordering is the one
    that makes sense to them.
    """
    if prefs is None:
        return []

    # `None` and `()` both credit nothing, which is correct here and is not the
    # whole story: an unknown must also be *said*, and that is `unknown_notes`.
    amenities = set(place.amenities or ())
    matched: list[str] = []

    def add(label: str) -> None:
        if label not in matched:
            matched.append(label)

    for slug in prefs.dietary or ():
        if slug in amenities:
            add(_label(slug))

    for slug in prefs.activities or ():
        if any(a in amenities for a in ACTIVITY_AMENITIES.get(slug, (slug,))):
            add(_label(slug))

    for slug in prefs.amenities or ():
        if slug in amenities:
            add(_label(slug))

    if prefs.price_level_max is not None and place.price_level is not None:
        if place.price_level <= prefs.price_level_max:
            add(price_label(prefs.price_level_max))

    if prefs.day_pass_budget_cents is not None and place.day_pass_cents is not None:
        if place.day_pass_cents <= prefs.day_pass_budget_cents:
            add("Within your day-pass budget")

    return matched


def unknown_notes(place: Place, prefs: UserPreferences | None) -> list[str]:
    """What could not be judged about this place, in the user's own terms.

    Only fields the user's preferences make relevant are reported. An unknown
    nobody asked about is noise rather than honesty, and a card that lists
    every absent column teaches the user to stop reading cards.

    Never a filter and never a credit: an unknown neither earns a chip nor
    removes the place from the list. `rank_places` does sort a place with no
    matches downwards, and these notes are what keeps that demotion visible
    instead of silent -- which is the whole difference between degrading and
    excluding.
    """
    if prefs is None:
        return []

    notes: list[str] = []

    # Trigger and wording are chosen together. A gym with unknown amenities is
    # not worth marking for someone who only set dietary preferences: dietary
    # never applied to a gym, so the note would name a concern the user does
    # not have here. This is the "only what their preferences make relevant"
    # rule at preference-kind grain rather than at place grain.
    if place.amenities is None:
        if place.kind is PlaceKind.food:
            if prefs.dietary:
                notes.append(UNKNOWN_DIETARY_OPTIONS)
        elif prefs.activities or prefs.amenities:
            notes.append(UNKNOWN_FACILITIES)

    if (
        prefs.day_pass_budget_cents is not None
        and place.day_pass_cents is None
        and place.kind in _DAY_PASS_KINDS
    ):
        notes.append(UNKNOWN_DAY_PASS)

    if (
        prefs.price_level_max is not None
        and place.price_level is None
        and place.kind is PlaceKind.food
    ):
        notes.append(UNKNOWN_PRICE)

    return notes


def over_budget_reason(place: Place, prefs: UserPreferences | None) -> str | None:
    """Why this place sits outside what the user said, or None.

    Returned instead of filtering the place away. The house vocabulary already
    works this way -- `plan_item_options.rejection_reason` is documented as
    "'$$$, above the budget you set'" -- and a candidate that vanishes silently
    cannot be argued with.

    Every test here is on a value we have. An unknown price is not over budget
    and not under it; it is unjudged, and it comes back from `unknown_notes`
    instead. A filter may only fail on known-bad.
    """
    if prefs is None:
        return None

    if (
        prefs.price_level_max is not None
        and place.price_level is not None
        and place.price_level > prefs.price_level_max
    ):
        return f"{'$' * place.price_level}, above the {price_label(prefs.price_level_max)} you set"

    if (
        prefs.day_pass_budget_cents is not None
        and place.day_pass_cents is not None
        and place.day_pass_cents > prefs.day_pass_budget_cents
    ):
        got = place.day_pass_cents / 100
        cap = prefs.day_pass_budget_cents / 100
        return f"${got:.0f} day pass, above the ${cap:.0f} you set"

    return None


def meters_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance. Haversine, not a route: no streets, no transit."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def distance_from(
    place: Place, anchor_lat: float | None, anchor_lng: float | None
) -> tuple[int | None, int | None]:
    """(meters, walking minutes) from the anchor, or (None, None).

    Both are reported because they answer different questions and only one of
    them is a guess: the meters are measured, the minutes assume a walking
    pace on a straight line, so they under-read where a river or a rail line
    is in the way. The Routes API replaces this function, not its callers.
    """
    if (
        anchor_lat is None
        or anchor_lng is None
        or place.lat is None
        or place.lng is None
    ):
        return None, None
    meters = meters_between(anchor_lat, anchor_lng, place.lat, place.lng)
    return round(meters), walk_minutes_between(anchor_lat, anchor_lng, place.lat, place.lng)


def walk_minutes_between(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """Straight-line walking minutes, floored at one.

    Split out so the route's leg times and a card's distance cannot end up
    assuming different paces; the same caveat as `distance_from` applies.
    """
    return max(1, round(meters_between(lat1, lng1, lat2, lng2) / _METERS_PER_MINUTE))


@dataclass(frozen=True)
class RankedPlace:
    """A cached place plus everything derived for one user and one anchor."""

    place: Place
    matched_preferences: list[str]
    # What we could not judge, alongside what we could. Both are needed to read
    # the card honestly: three chips out of five preferences means something
    # different when the other two were unanswerable.
    unknown_notes: list[str]
    over_budget_reason: str | None
    distance_meters: int | None
    walk_minutes: int | None


def rank_places(
    places: list[Place],
    prefs: UserPreferences | None,
    anchor_lat: float | None = None,
    anchor_lng: float | None = None,
) -> list[RankedPlace]:
    """Best first: most matches, then nearest, then name.

    Name last so the order is stable when a trip has no coordinates and every
    distance is None. Over-budget places sort behind everything rather than
    dropping out, so the reason stays arguable.
    """
    ranked = []
    for p in places:
        meters, minutes = distance_from(p, anchor_lat, anchor_lng)
        ranked.append(
            RankedPlace(
                place=p,
                matched_preferences=match_preferences(p, prefs),
                unknown_notes=unknown_notes(p, prefs),
                over_budget_reason=over_budget_reason(p, prefs),
                distance_meters=meters,
                walk_minutes=minutes,
            )
        )
    ranked.sort(
        key=lambda r: (
            r.over_budget_reason is not None,
            -len(r.matched_preferences),
            r.distance_meters if r.distance_meters is not None else 10**9,
            r.place.name,
        )
    )
    return ranked
