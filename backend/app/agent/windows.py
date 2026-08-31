"""When the traveler is actually free. Interval arithmetic, no judgment.

Deliberately event-agnostic: nothing here has ever seen a calendar row, and
nothing here decides what "busy" means. "Occupies you" is not "is on the
calendar" - a declined optional meeting, an event marked free, and a cancelled
invite all still have rows - and that predicate belongs to the calendar sync,
which stores it once as `calendar_events.busy` rather than having every reader
recompute it. Callers pass intervals that are already busy by that definition.

That split is a track boundary as well as a design one: the busy predicate is
Track A's to define, and a copy of the rule living here would be a second home
for it, which is how the two drift.

Windows are **capacity, not demand**. This module answers "how much room is
there", never "how much should we put in it" - the second question is the
planner's, and conflating them is what produces a plan with six activities in
it that the user does two of.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

# Waking hours, as a default rather than a constant: the real bound is a user
# preference we do not have a column for yet, so callers can already override it
# and the day it becomes a preference nothing here changes.
DEFAULT_DAY_START = time(7, 0)
DEFAULT_DAY_END = time(22, 0)

# Below this a gap is not an opportunity, it is a rounding error. The planner
# additionally applies `session_minutes.min`; this is the floor under it, so a
# user with no session preference still does not get eleven-minute windows.
DEFAULT_MIN_MINUTES = 30


@dataclass(frozen=True)
class BusyInterval:
    """Something that occupies the traveler, in trip-local time."""

    start: datetime
    end: datetime
    title: str


@dataclass(frozen=True)
class FreeWindow:
    day: date
    start: datetime
    end: datetime
    # What the window sits between, in order. The display string
    # ("Between your workshop and the team dinner") is built from this, so the
    # provenance survives the bounding event being deleted.
    bounded_by: tuple[str, ...]

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class _Merged:
    start: datetime
    end: datetime
    titles: tuple[str, ...]


def merge_busy(intervals: Sequence[BusyInterval]) -> list[_Merged]:
    """Overlapping and touching intervals become one, keeping every title.

    Two back-to-back meetings do not leave a zero-minute gap between them, and
    treating them as one block is what makes `bounded_by` name the events either
    side of the *window* rather than the two halves of a solid afternoon.
    """
    ordered = sorted(intervals, key=lambda b: (b.start, b.end))
    merged: list[_Merged] = []
    for interval in ordered:
        if interval.end <= interval.start:
            continue
        if merged and interval.start <= merged[-1].end:
            last = merged[-1]
            merged[-1] = _Merged(
                last.start,
                max(last.end, interval.end),
                (*last.titles, interval.title),
            )
        else:
            merged.append(_Merged(interval.start, interval.end, (interval.title,)))
    return merged


def free_windows(
    busy: Sequence[BusyInterval],
    days: Sequence[date],
    tz: tzinfo,
    *,
    day_start: time = DEFAULT_DAY_START,
    day_end: time = DEFAULT_DAY_END,
    min_minutes: int = DEFAULT_MIN_MINUTES,
) -> list[FreeWindow]:
    """The gaps between busy intervals, clipped to waking hours, per day."""
    merged = merge_busy(busy)
    out: list[FreeWindow] = []

    for day in days:
        opens = datetime.combine(day, day_start, tzinfo=tz)
        closes = datetime.combine(day, day_end, tzinfo=tz)
        if closes <= opens:
            continue

        cursor = opens
        before: str | None = None
        for block in merged:
            if block.end <= opens or block.start >= closes:
                continue
            gap_end = min(block.start, closes)
            _append(out, day, cursor, gap_end, before, block.titles[0], min_minutes)
            cursor = max(cursor, min(block.end, closes))
            before = block.titles[-1]
        _append(out, day, cursor, closes, before, None, min_minutes)

    return out


def _append(
    out: list[FreeWindow],
    day: date,
    start: datetime,
    end: datetime,
    before: str | None,
    after: str | None,
    min_minutes: int,
) -> None:
    if end - start < timedelta(minutes=min_minutes):
        return
    bounds = tuple(t for t in (before, after) if t)
    out.append(FreeWindow(day=day, start=start, end=end, bounded_by=bounds))
