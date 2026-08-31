"""Does a calendar event block time? Asked in one place, on purpose.

Four consumers want this question answered - the planner's windows, the trip
timeline, conflict detection, and eventually a user setting - and the research
in `docs/CALENDAR_INTEGRATION.md` section 4 closes by warning that the busy
rule *becomes a user preference* and is worth not hardcoding in three places
first. So the rule is `is_busy` and nothing else, and SQL consumers get the
same predicate spelled for their dialect rather than retyping it.

There are **two** questions here and they are not the same one, which is worth
naming because they were briefly given the same name:

- `classify(payload)` - *at sync time*, from a Google payload: does this event
  block time? This is the rule. It runs once per event and writes the column.
- `is_busy(row)` / `busy_clause()` / `BUSY_SQL` - *at read time*, from a stored
  row: does this event block time? One predicate in three dialects, because its
  three consumers read in three different ways. Python for callers that already
  hold the rows, an ORM expression, and a text fragment.

`calendar_events.busy` is nullable and NULL means **not yet classified**, which
is not the same as "does not block time". Every reader therefore asks
`busy IS NOT FALSE`: an unclassified event blocks time, because over-blocking
costs a suggestion and under-blocking double-books a real commitment. Storing
`true` by default would have made "never synced" and "Google said opaque" the
same value and left nothing able to tell them apart.

**Reading and filtering are not the same operation.** A declined meeting still
belongs on the traveler's timeline; it just must not carve a planning window.
So the Python reader exists precisely so one query can serve both - callers
split a list they already hold, rather than running a second filtered query and
giving the two reads a chance to disagree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa

from app.db.models import CalendarEvent

# For textual SQL (`api/trips.py` builds its calendar read as text). The same
# predicate as `is_busy` and `busy_clause`; the agreement test is what stops
# the three from drifting.
BUSY_SQL = "busy is not false"


def is_busy(event: CalendarEvent) -> bool:
    """Does this stored event block time? The read-side predicate, in Python.

    For callers holding rows rather than building a query - notably the agent's
    context gather, which reads a trip's events once and splits the list two
    ways: every row is a commitment, only the busy ones carve windows.
    """
    return event.busy is not False


def busy_clause() -> sa.ColumnElement[bool]:
    """The same predicate as an ORM expression."""
    return CalendarEvent.busy.isnot(False)


def classify(event: Mapping[str, Any]) -> bool:
    """The rule. Classify one Google `events.list` resource
    (`singleEvents=true`) at sync time, to be written to `busy`.

    Always decides. A NULL in the column means no sync has run over that row
    yet, never that this could not be classified.
    """
    if event.get("status") == "cancelled":
        return False

    # Declining a meeting is how a user says they are not going. Treating it as
    # busy would have us refuse to plan around a slot they deliberately freed.
    for attendee in event.get("attendees") or ():
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return False

    transparency = event.get("transparency")
    if transparency == "transparent":
        return False

    # All-day events are the exception to Google's `opaque`-when-absent default.
    # The API documents that default, but the Calendar UI creates all-day events
    # as Free, so honouring the API default here turns one multi-day conference
    # into a wall of busy time across the entire trip. Explicitly opaque still
    # counts; only the absent case flips.
    if transparency is None and "date" in (event.get("start") or {}):
        return False

    return True
