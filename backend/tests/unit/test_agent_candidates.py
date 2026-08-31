"""Hard filters, distance, and the pre-rank that makes truncation meaningful."""

import uuid

from app.agent.candidates import (
    UNKNOWN_DAY_PASS,
    UNKNOWN_DIETARY,
    UNKNOWN_PRICE_LEVEL,
    build_candidates,
    dietary_unknown,
    is_open_during,
    open_label,
    passes_hard_filters,
    preference_matches,
    unknown_constraints,
    walk_minutes,
)
from app.agent.schemas import ContextPreferences, ContextWindow, SessionMinutes
from app.db.models import Place

# The Gwen, and a window on a Wednesday evening.
ORIGIN = (41.8924, -87.6252)
WEEKDAY_HOURS = {
    "mon": [360, 1320], "tue": [360, 1320], "wed": [360, 1320],
    "thu": [360, 1320], "fri": [360, 1290], "sat": [420, 1200],
    "sun": [420, 1200],
}
EVENING = ContextWindow(
    id="w1", day="2026-09-09", start="17:30", end="19:00", minutes=90
)

PREFS = ContextPreferences(
    dietary=["vegetarian"],
    workout_kinds=["swim"],
    facilities=["pool"],
    day_pass_max_cents=2000,
    price_level_max=2,
    session_minutes=SessionMinutes(min=45, max=90),
)


def place(**overrides) -> Place:
    fields = {
        "place_id": uuid.uuid4(),
        "kind": "workout",
        "name": "Lakeshore Sport & Fitness",
        "lat": 41.8887,
        "lng": -87.6180,
        "amenities": ["pool", "sauna"],
        "hours": WEEKDAY_HOURS,
        "day_pass_cents": 2000,
        "price_level": None,
        "summary": "Pool + treadmill",
    }
    return Place(**{**fields, **overrides})


def test_walk_minutes_is_derived_not_asked_for():
    # ~700m straight line from The Gwen at 80 m/min. Exact because the
    # function is deterministic; a routed figure would not be.
    assert walk_minutes(ORIGIN, place()) == 9


def test_walk_minutes_is_none_without_coordinates():
    assert walk_minutes(ORIGIN, place(lat=None, lng=None)) is None
    assert walk_minutes(None, place()) is None


def test_a_place_over_the_day_pass_cap_is_filtered_out():
    assert not passes_hard_filters(place(day_pass_cents=3500), PREFS)


def test_a_place_over_the_price_level_is_filtered_out():
    assert not passes_hard_filters(place(kind="food", price_level=4, amenities=["vegetarian"]), PREFS)


def test_a_restaurant_meeting_no_dietary_requirement_is_filtered_out():
    assert not passes_hard_filters(place(kind="food", amenities=["steak"]), PREFS)


def test_dietary_only_constrains_food():
    """A gym is not required to be vegetarian."""
    assert passes_hard_filters(place(amenities=["treadmill"]), PREFS)


def test_amenity_mismatch_is_soft_not_hard():
    """A treadmill-only gym still gets offered, it just ranks below the pool."""
    treadmill = place(amenities=["treadmill"])
    assert passes_hard_filters(treadmill, PREFS)
    assert preference_matches(treadmill, PREFS) == 0
    assert preference_matches(place(), PREFS) == 1


def test_closed_during_the_window_is_not_eligible():
    closed = place(hours={"wed": [360, 1000]})  # shuts at 16:40
    assert not is_open_during(closed, EVENING)


def test_unknown_hours_count_as_open():
    """An unfilled cache row must not silently shrink the decision space."""
    assert is_open_during(place(hours=None), EVENING)
    assert open_label(place(hours=None), EVENING) is None


def test_open_label_is_the_windows_own_weekday():
    assert open_label(place(), EVENING) == "06:00-22:00"


def test_build_candidates_ranks_the_better_match_first():
    pool = place(name="Lakeshore")
    treadmill = place(name="Hotel gym", amenities=["treadmill"], day_pass_cents=0)
    candidates, id_map = build_candidates(
        [treadmill, pool], [EVENING], PREFS, ORIGIN
    )
    assert [c.name for c in candidates] == ["Lakeshore", "Hotel gym"]
    assert id_map["c1"] == pool.place_id


def test_a_place_eligible_for_no_window_is_dropped():
    closed = place(hours={"wed": [360, 1000]})
    candidates, id_map = build_candidates([closed], [EVENING], PREFS, ORIGIN)
    assert candidates == [] and id_map == {}


def test_candidates_carry_only_the_projected_fields():
    candidates, _ = build_candidates([place()], [EVENING], PREFS, ORIGIN)
    assert set(candidates[0].model_dump()) == {
        "id", "kind", "window_ids", "name", "summary", "walk_minutes",
        "day_pass_cents", "price_level", "amenities", "unknown", "open",
    }


def test_food_places_are_projected_as_meals():
    candidates, _ = build_candidates(
        [place(kind="food", amenities=["vegetarian"])], [EVENING], PREFS, ORIGIN
    )
    assert candidates[0].kind == "meal"


# ---------------------------------------------------------------------------
# Decision 8: a hard filter fails only on known-bad, and says what it could not
# check. The two halves are tested apart because they fail apart - excluding on
# unknown is silent, admitting without marking is invisible.
# ---------------------------------------------------------------------------


def test_a_restaurant_with_no_amenities_is_admitted_not_excluded():
    """The failure this rule exists for: every meal vanishing from a live cache.

    Google supplies no amenities, so a freshly filled `places` row has `{}` and
    the old predicate read that as "meets none of your dietary needs".
    """
    hungry = place(kind="food", amenities=[], name="Somewhere new")
    assert passes_hard_filters(hungry, PREFS) is True
    assert UNKNOWN_DIETARY in unknown_constraints(hungry, PREFS)


def test_a_restaurant_that_lists_amenities_without_the_one_asked_for_is_excluded():
    """Known-bad still fails. Admitting unknowns is not admitting everything."""
    steakhouse = place(kind="food", amenities=["reservations", "bar"])
    assert passes_hard_filters(steakhouse, PREFS) is False
    assert UNKNOWN_DIETARY not in unknown_constraints(steakhouse, PREFS)


def test_a_restaurant_that_matches_is_admitted_with_nothing_unknown():
    salad = place(kind="food", amenities=["vegetarian"])
    assert passes_hard_filters(salad, PREFS) is True
    assert UNKNOWN_DIETARY not in unknown_constraints(salad, PREFS)


def test_an_unpriced_venue_is_admitted_but_no_longer_silently():
    """The same bug with the opposite sign: it always passed, it just never said so."""
    unpriced = place(day_pass_cents=None, price_level=None)
    assert passes_hard_filters(unpriced, PREFS) is True
    assert set(unknown_constraints(unpriced, PREFS)) == {
        UNKNOWN_DAY_PASS,
        UNKNOWN_PRICE_LEVEL,
    }


def test_an_unknown_the_user_did_not_constrain_is_not_an_unknown():
    """A missing price on a place nobody price-capped is an irrelevance."""
    unpriced = place(day_pass_cents=None, price_level=None)
    no_caps = ContextPreferences(workout_kinds=["swim"])
    assert unknown_constraints(unpriced, no_caps) == ()


def test_dietary_unknown_is_the_single_predicate_that_changes_with_the_column():
    """`places.amenities` is NOT NULL, so `[]` is the only unknown available."""
    assert dietary_unknown(place(amenities=[])) is True
    assert dietary_unknown(place(amenities=["pool"])) is False


def test_over_budget_is_still_over_budget():
    assert passes_hard_filters(place(day_pass_cents=9000), PREFS) is False
