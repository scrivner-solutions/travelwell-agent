"""Which calendar events fall inside a trip? Asked in one place, on purpose.

Two readers want the same rows - the trip timeline and the planner's context
gather - and they used to ask different questions. The timeline asked by owner
and date overlap. Gather asked `where trip_id = ?`, a column sync never wrote,
so the planner saw nothing for any calendar that had actually been synced and
scheduled workouts over real meetings. This module is the one query, so the two
reads cannot drift apart again.

The question is overlap, not ownership. Which trip an event BELONGS to is
detection's judgement and lives in `trip_evidence`. Whether an event CONSTRAINS
the traveler while they are away is arithmetic on the trip's own dates and
zone, and the events a planner most needs are exactly the ones detection would
reject: the standing meeting back home that still eats the morning.

`events_during` takes the `Trip` row rather than its fields so that the owner
scope cannot be left out. A trip has one owner, and a date overlap without
`user_id` matches every traveler's calendar.
"""

from __future__ import annotations

from datetime import date, timedelta

import sqlalchemy as sa

from app.db.models import CalendarEvent, Trip
from app.services.calendar.status import live_clause


def _midnight(day: date, tz: str) -> sa.ColumnElement:
    """The instant a trip-local calendar day begins.

    `timezone(zone, timestamp)` reads a naive timestamp as wall time in that
    zone and returns the instant, which is the direction needed here.
    """
    return sa.func.timezone(tz, sa.cast(sa.literal(day), sa.TIMESTAMP))


def local_day(trip: Trip) -> sa.ColumnElement[date]:
    """An event's start as a calendar date in the trip's zone, for day filters."""
    return sa.cast(sa.func.timezone(trip.timezone, CalendarEvent.starts_at), sa.Date)


def events_during(trip: Trip) -> sa.Select[tuple[CalendarEvent]]:
    """Every live event on the trip owner's calendar that overlaps the trip's
    dates, in start order. The last day is inclusive, so the window runs to the
    midnight after it."""
    window_start = _midnight(trip.start_date, trip.timezone)
    window_end = _midnight(trip.end_date + timedelta(days=1), trip.timezone)
    return (
        sa.select(CalendarEvent)
        .where(
            CalendarEvent.user_id == trip.user_id,
            live_clause(),
            CalendarEvent.starts_at < window_end,
            CalendarEvent.ends_at > window_start,
        )
        .order_by(CalendarEvent.starts_at)
    )
