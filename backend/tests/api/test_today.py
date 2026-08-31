"""GET /trips/{id}/today: the assembled Today view against the scene fixture.

The scene plants traps (an expired window, tomorrow's window, a skipped item,
tomorrow's item) so each filter in the endpoint has a case that would fail
if the filter went missing.
"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_today_assembly(authed_client, scene):
    r = await authed_client.get(f"/api/v1/trips/{scene.trip_id}/today")
    assert r.status_code == 200, r.text
    t = r.json()

    assert t["day_label"] == "Chicago · Day 2 of 4"
    assert t["state_word"] == "Active"
    assert t["state_detail"] == "Watching for schedule changes"
    assert t["timezone"] == scene.timezone

    # Today's OPEN window wins over both the expired one earlier today and
    # tomorrow's open one.
    window = t["window"]
    assert window is not None
    assert window["label"] == "90 minutes free"
    assert window["gap_explanation"].startswith("Between your workshop")
    assert [b["tag"] for b in window["bounds"]] == ["CAL", "PLAN"]
    assert window["bounds"][0]["title"] == "Workshop, Room 4B"
    assert window["bounds"][0]["source_label"] == "Calendar"

    # Only today's visible items, in start order: the skipped item and
    # tomorrow's run are absent.
    assert [i["title"] for i in t["next_up"]] == scene.visible_items_today

    workout = t["next_up"][0]
    assert workout["status"] == "awaiting_user"
    # The workout fills today's window; the design nests it inside the
    # window card, so the payload must carry the link both ways.
    assert workout["window_id"] == window["id"]
    assert workout["why"] == ["Swim", "45-90 min"]
    sel = workout["selected_option"]
    assert sel["display_name"] == "YMCA"
    assert sel["display_summary"] == "Pool + treadmill · 75 min"
    assert sel["reason"] == "Fits your 90-minute opening"
    assert sel["distance_minutes"] == 7

    dinner = t["next_up"][1]
    assert dinner["status"] == "awaiting_user"
    assert dinner["selected_option"]["display_name"] == "Beatrix"


async def test_today_before_trip_starts(authed_client, user, make_trip):
    from app.db.models import TripState

    trip = await make_trip(
        user, state=TripState.confirmed, city="Austin", region="TX",
        tz="America/Chicago", start_in=10,
    )
    r = await authed_client.get(f"/api/v1/trips/{trip.trip_id}/today")
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["day_label"] == "Austin in 10 days"
    assert t["state_word"] == "Upcoming"
    # None fields are omitted from responses, never sent as null (ApiRoute).
    assert "window" not in t
    assert t["next_up"] == []


async def test_today_detail_derived_from_activation(authed_client, user, make_trip):
    """Confirmed and upcoming have no table detail, so it is derived here; the
    copy stays person-free like every _STATE_WORDS entry beside it."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.db.models import TripState

    tz = "America/Chicago"
    trip = await make_trip(
        user, state=TripState.confirmed, city="Austin", region="TX",
        tz=tz, start_in=10, activation_in=3,
    )
    r = await authed_client.get(f"/api/v1/trips/{trip.trip_id}/today")
    assert r.status_code == 200, r.text

    expected = (datetime.now(ZoneInfo(tz)) + timedelta(days=3)).strftime("%b %d")
    assert r.json()["state_detail"] == f"Preparing from {expected}"
