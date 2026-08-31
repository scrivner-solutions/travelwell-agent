"""The busy rule: classify() over a Google payload. The read-side predicate is
tested in tests/api/test_calendar_busy_agreement.py."""

import pytest

from app.services.calendar.busy import classify


def timed(**over):
    event = {"start": {"dateTime": "2026-09-01T10:00:00Z"}}
    event.update(over)
    return event


def all_day(**over):
    event = {"start": {"date": "2026-09-01"}}
    event.update(over)
    return event


def test_an_ordinary_event_blocks_time():
    assert classify(timed()) is True


def test_opaque_is_the_default_for_a_timed_event():
    """Google omits `transparency` on most events and documents the default."""
    assert classify(timed(transparency=None)) is True
    assert classify(timed(transparency="opaque")) is True


def test_an_event_marked_free_does_not_block():
    assert classify(timed(transparency="transparent")) is False


def test_a_cancelled_event_does_not_block():
    assert classify(timed(status="cancelled")) is False


def test_a_cancelled_event_wins_over_opaque():
    assert classify(timed(status="cancelled", transparency="opaque")) is False


def test_declining_frees_the_slot():
    """Declining is how a user says they are not going; blocking it anyway
    would refuse to plan around time they deliberately freed."""
    event = timed(attendees=[{"self": True, "responseStatus": "declined"}])
    assert classify(event) is False


def test_someone_else_declining_changes_nothing():
    event = timed(attendees=[{"self": False, "responseStatus": "declined"}])
    assert classify(event) is True


def test_accepting_blocks_normally():
    event = timed(attendees=[{"self": True, "responseStatus": "accepted"}])
    assert classify(event) is True


def test_an_all_day_event_does_not_block_the_whole_trip():
    """The judgment call in this rule. Google's API documents `opaque` when
    `transparency` is absent, but its UI creates all-day events as Free, so
    applying the API default turns one multi-day conference into a wall of
    busy time across an entire trip."""
    assert classify(all_day()) is False


def test_an_all_day_event_marked_busy_is_still_busy():
    """Only the absent case flips; an explicit choice is honoured."""
    assert classify(all_day(transparency="opaque")) is True


@pytest.mark.parametrize("event", [{}, {"start": {}}, {"attendees": []}])
def test_a_sparse_payload_still_decides(event):
    """The function always answers. A NULL in the column means no sync has run
    over that row, never that this could not be classified."""
    assert isinstance(classify(event), bool)
