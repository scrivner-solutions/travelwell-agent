"""GET /trips/{id}/timeline: calendar/plan interleave, ordering, day filter."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_full_timeline_interleaves_and_sorts(authed_client, scene):
    r = await authed_client.get(f"/api/v1/trips/{scene.trip_id}/timeline")
    assert r.status_code == 200, r.text
    entries = r.json()["entries"]

    assert len(entries) == scene.total_timeline_entries
    assert {e["entry_type"] for e in entries} == {"calendar_event", "plan_item"}
    starts = [e["starts_at"] for e in entries]
    assert starts == sorted(starts), "entries must be time-ordered"

    # The skipped item is a tombstone: hidden here too.
    titles = [
        e["plan_item"]["title"] for e in entries if e["entry_type"] == "plan_item"
    ]
    assert "Walk the Riverwalk" not in titles

    # Each entry carries exactly its own payload kind.
    for e in entries:
        if e["entry_type"] == "calendar_event":
            assert e["calendar_event"] is not None and e["plan_item"] is None
        else:
            assert e["plan_item"] is not None and e["calendar_event"] is None


async def test_day_filter_scopes_both_sources(authed_client, scene):
    r = await authed_client.get(
        f"/api/v1/trips/{scene.trip_id}/timeline",
        params={"day": scene.today.isoformat()},
    )
    entries = r.json()["entries"]
    cal = [e for e in entries if e["entry_type"] == "calendar_event"]
    items = [e["plan_item"]["title"] for e in entries if e["entry_type"] == "plan_item"]
    assert [c["calendar_event"]["title"] for c in cal] == ["Conference", "Workshop"]
    assert cal[0]["calendar_event"]["location_name"] == "McCormick Place"
    assert items == scene.visible_items_today

    r = await authed_client.get(
        f"/api/v1/trips/{scene.trip_id}/timeline",
        params={"day": scene.tomorrow.isoformat()},
    )
    entries = r.json()["entries"]
    assert [
        e["plan_item"]["title"] for e in entries if e["entry_type"] == "plan_item"
    ] == [scene.visible_item_tomorrow]
    assert [
        e["calendar_event"]["title"]
        for e in entries
        if e["entry_type"] == "calendar_event"
    ] == ["Keynote"]


async def test_empty_day_returns_empty_list(authed_client, scene):
    r = await authed_client.get(
        f"/api/v1/trips/{scene.trip_id}/timeline", params={"day": "1999-01-01"}
    )
    assert r.status_code == 200
    assert r.json()["entries"] == []
