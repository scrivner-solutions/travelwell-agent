"""The preference matcher: chips, budget reasons, distance and ranking.

Pure functions, so these build detached model instances and never touch a
database. Server-side column defaults do not apply to a detached instance, so
list columns are passed explicitly wherever they matter.
"""

from app.db.models import Place, PlaceKind, UserPreferences
from app.services.places.matching import (
    distance_from,
    match_preferences,
    meters_between,
    over_budget_reason,
    rank_places,
)


def place(**kw) -> Place:
    base = dict(
        name="Somewhere",
        kind=PlaceKind.workout,
        amenities=[],
        lat=None,
        lng=None,
        price_level=None,
        day_pass_cents=None,
    )
    return Place(**{**base, **kw})


def prefs(**kw) -> UserPreferences:
    base = dict(dietary=[], activities=[], amenities=[], memberships=[])
    return UserPreferences(**{**base, **kw})


def test_no_preferences_earns_no_chips():
    assert match_preferences(place(amenities=["pool"]), None) == []
    assert match_preferences(place(amenities=["pool"]), prefs()) == []


def test_an_activity_matches_through_the_amenity_bridge():
    """The seed credits the YMCA with "Swim" for having a pool, not a swim."""
    p = place(amenities=["pool", "treadmill"])
    assert match_preferences(p, prefs(activities=["swim"])) == ["Swim"]


def test_chips_follow_the_users_order_not_the_places():
    p = place(amenities=["sauna", "pool", "vegetarian"])
    got = match_preferences(
        p, prefs(dietary=["vegetarian"], amenities=["sauna", "pool"])
    )
    assert got == ["Vegetarian", "Sauna", "Pool"]


def test_a_chip_is_not_repeated_when_two_rules_hit_it():
    """`swim` bridges to `pool` and `pool` is also asked for directly."""
    p = place(amenities=["pool"])
    got = match_preferences(p, prefs(activities=["swim"], amenities=["pool"]))
    assert got == ["Swim", "Pool"]


def test_price_ceiling_reads_as_the_ceiling_the_user_set():
    p = place(price_level=1)
    assert "$$ or less" in match_preferences(p, prefs(price_level_max=2))


def test_over_budget_is_a_reason_rather_than_a_filter():
    pricey = place(price_level=4)
    assert over_budget_reason(pricey, prefs(price_level_max=2)) == (
        "$$$$, above the $$ or less you set"
    )
    assert match_preferences(pricey, prefs(price_level_max=2)) == []


def test_day_pass_over_the_cap_names_both_numbers():
    p = place(day_pass_cents=3500)
    assert over_budget_reason(p, prefs(day_pass_budget_cents=2000)) == (
        "$35 day pass, above the $20 you set"
    )


def test_a_free_day_pass_is_within_any_budget():
    p = place(day_pass_cents=0)
    assert "Within your day-pass budget" in match_preferences(
        p, prefs(day_pass_budget_cents=2000)
    )
    assert over_budget_reason(p, prefs(day_pass_budget_cents=2000)) is None


def test_unpriced_places_are_neither_matched_nor_rejected():
    """A cache row with no price is missing data, not a cheap venue."""
    p = place()
    assert match_preferences(p, prefs(price_level_max=2)) == []
    assert over_budget_reason(p, prefs(price_level_max=2)) is None


def test_meters_between_is_symmetric_and_zero_on_itself():
    a = (41.8924, -87.6252)
    b = (41.8763, -87.6534)
    assert meters_between(*a, *a) == 0
    assert meters_between(*a, *b) == meters_between(*b, *a)


def test_a_degree_of_latitude_is_about_111_km():
    """Anchors the haversine to a number that is true independent of the code."""
    meters = meters_between(41.0, -87.6, 42.0, -87.6)
    assert abs(meters - 111_195) < 1_000


def test_distance_needs_both_ends():
    anchored = place(lat=41.8763, lng=-87.6534)
    assert distance_from(anchored, None, None) == (None, None)
    assert distance_from(place(), 41.8924, -87.6252) == (None, None)
    meters, minutes = distance_from(anchored, 41.8924, -87.6252)
    assert meters > 0 and minutes > 0


def test_ranking_is_matches_then_distance_then_name():
    near_no_match = place(name="Near", lat=41.8925, lng=-87.6253)
    far_match = place(name="Far", lat=41.8763, lng=-87.6534, amenities=["pool"])
    ranked = rank_places(
        [near_no_match, far_match], prefs(amenities=["pool"]), 41.8924, -87.6252
    )
    assert [r.place.name for r in ranked] == ["Far", "Near"]


def test_over_budget_sorts_last_even_with_more_matches():
    """Still returned, still explained -- just not offered first."""
    over = place(name="Over", amenities=["pool", "sauna"], price_level=4)
    ok = place(name="Ok", amenities=["pool"], price_level=1)
    ranked = rank_places(
        [over, ok], prefs(amenities=["pool", "sauna"], price_level_max=2)
    )
    assert [r.place.name for r in ranked] == ["Ok", "Over"]
    assert ranked[1].over_budget_reason is not None


def test_ranking_is_stable_without_any_coordinates():
    a, b = place(name="Alpha"), place(name="Beta")
    assert [r.place.name for r in rank_places([b, a], None)] == ["Alpha", "Beta"]
