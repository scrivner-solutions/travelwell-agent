"""Writing a calendar window into `calendar_events`. No network here.

Everything in this module is a pure function of what the client returned, which
is what lets it be tested without credentials - the reason the port has exactly
one method.

Two things it deliberately does not do:

**It never sets `trip_id`.** Which trip an event belongs to is detection's
question, and detection is a separate pass over the same rows. A sync that
guessed would overwrite a real answer with a heuristic every time it ran.

**It never deletes.** Cancellations arrive as rows with `status = 'cancelled'`
because the client asks for them, so removal is a status change rather than a
missing row. Sweeping rows the window did not return would delete every event
outside whatever range was last fetched.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CalendarEvent, ConnectedSource, SourceStatus
from app.services.calendar.ports import (
    CalendarClient,
    CredentialRejected,
    RemoteEvent,
)

# Bumping this re-hashes every row, so every event reads as changed once. That
# is the intended cost of adding a field to the comparison.
_HASH_VERSION = "1"


def content_hash(event: RemoteEvent) -> str:
    """A stable digest of everything sync would write.

    Unit-separated rather than concatenated: a title ending in a digit next to
    a timestamp starting with one would otherwise collide with the pair beside
    it. `busy` is included because it is derived from fields that are not - a
    guest declining changes nothing else about the event.
    """
    parts = (
        _HASH_VERSION,
        event.external_id,
        event.title,
        event.location or "",
        event.starts_at.astimezone(UTC).isoformat(),
        event.ends_at.astimezone(UTC).isoformat(),
        event.status,
        "1" if event.busy else "0",
    )
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def seen(self) -> int:
        return self.created + self.updated + self.unchanged


async def sync_source(
    session: AsyncSession,
    source: ConnectedSource,
    client: CalendarClient,
    *,
    start: datetime,
    end: datetime,
) -> SyncResult:
    """Fetch a window and reconcile it into `calendar_events`.

    Does not commit: the caller owns the transaction, so a failed write cannot
    leave `last_synced_at` claiming a sync that did not land. On a rejected
    credential the source is marked `error` and the exception re-raised - the
    caller must still commit for that mark to survive, which is deliberate,
    since the mark is the useful part of the failure.
    """
    try:
        events = await client.list_events(start, end)
    except CredentialRejected:
        source.status = SourceStatus.error
        raise

    existing = {
        row.external_id: row
        for row in (
            (
                await session.execute(
                    sa.select(CalendarEvent).where(
                        CalendarEvent.source_id == source.source_id
                    )
                )
            )
            .scalars()
            .all()
        )
    }

    now = datetime.now(UTC)
    created = updated = unchanged = 0

    for event in events:
        digest = content_hash(event)
        row = existing.get(event.external_id)
        if row is None:
            session.add(
                CalendarEvent(
                    user_id=source.user_id,
                    source_id=source.source_id,
                    external_id=event.external_id,
                    title=event.title,
                    location=event.location,
                    starts_at=event.starts_at,
                    ends_at=event.ends_at,
                    status=event.status,
                    busy=event.busy,
                    content_hash=digest,
                    last_seen_at=now,
                )
            )
            created += 1
        elif row.content_hash != digest:
            # trip_id is not in this list on purpose; see the module docstring.
            row.title = event.title
            row.location = event.location
            row.starts_at = event.starts_at
            row.ends_at = event.ends_at
            row.status = event.status
            row.busy = event.busy
            row.content_hash = digest
            row.last_seen_at = now
            updated += 1
        else:
            row.last_seen_at = now
            unchanged += 1

    source.last_synced_at = now
    # A sync that succeeded is the only evidence that clears an earlier `error`.
    source.status = SourceStatus.connected
    return SyncResult(created=created, updated=updated, unchanged=unchanged)
