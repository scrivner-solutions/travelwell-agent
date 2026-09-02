"""Interval arithmetic over fixture calendars - the ledger's enforcement for
"when is the traveler free", which is code's decision and never the model's.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.agent.windows import BusyInterval, free_windows, merge_busy

TZ = ZoneInfo("America/Chicago")
DAY = date(2026, 9, 9)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 9, hour, minute, tzinfo=TZ)


def busy(start: tuple[int, int], end: tuple[int, int], title: str) -> BusyInterval:
    return BusyInterval(start=at(*start), end=at(*end), title=title)


def spans(windows) -> list[tuple[str, str]]:
    return [
        (f"{w.start.hour:02d}:{w.start.minute:02d}", f"{w.end.hour:02d}:{w.end.minute:02d}")
        for w in windows
    ]


def test_empty_day_is_one_window_over_waking_hours():
    result = free_windows([], [DAY], TZ)
    assert spans(result) == [("07:00", "22:00")]
    assert result[0].bounded_by == ()


def test_one_meeting_splits_the_day():
    result = free_windows([busy((9, 0), (17, 0), "Workshop day 1")], [DAY], TZ)
    assert spans(result) == [("07:00", "09:00"), ("17:00", "22:00")]
    assert result[0].bounded_by == ("Workshop day 1",)
    assert result[1].bounded_by == ("Workshop day 1",)


def test_gap_between_two_events_names_both():
    result = free_windows(
        [busy((9, 0), (17, 0), "Workshop day 1"), busy((19, 0), (21, 0), "Team dinner")],
        [DAY],
        TZ,
    )
    middle = next(w for w in result if w.start == at(17, 0))
    assert middle.bounded_by == ("Workshop day 1", "Team dinner")
    assert middle.minutes == 120


def test_short_gaps_are_dropped():
    result = free_windows(
        [busy((9, 0), (12, 0), "Standup"), busy((12, 20), (17, 0), "Review")],
        [DAY],
        TZ,
        min_minutes=30,
    )
    assert ("12:00", "12:20") not in spans(result)


def test_back_to_back_events_merge_and_the_window_names_the_outer_pair():
    """Two touching meetings are one solid block, not a zero-minute window."""
    result = free_windows(
        [busy((9, 0), (12, 0), "Standup"), busy((12, 0), (17, 0), "Review")],
        [DAY],
        TZ,
    )
    assert spans(result) == [("07:00", "09:00"), ("17:00", "22:00")]
    assert result[1].bounded_by == ("Review",)


def test_overlapping_events_merge():
    merged = merge_busy(
        [busy((9, 0), (13, 0), "A"), busy((11, 0), (17, 0), "B")]
    )
    assert len(merged) == 1
    assert merged[0].start == at(9, 0) and merged[0].end == at(17, 0)
    assert merged[0].titles == ("A", "B")


def test_a_full_day_event_leaves_nothing():
    result = free_windows([busy((6, 0), (23, 0), "Offsite")], [DAY], TZ)
    assert result == []


def test_events_outside_waking_hours_do_not_bound_anything():
    result = free_windows([busy((5, 0), (6, 0), "Red-eye landing")], [DAY], TZ)
    assert spans(result) == [("07:00", "22:00")]


def test_zero_length_intervals_are_ignored():
    assert merge_busy([busy((9, 0), (9, 0), "Cancelled")]) == []


def test_day_bounds_are_a_parameter_not_a_constant():
    result = free_windows([], [DAY], TZ, day_start=time(5, 30), day_end=time(23, 0))
    assert spans(result) == [("05:30", "23:00")]
