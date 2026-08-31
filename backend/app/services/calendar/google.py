"""Google Calendar, behind the port. The only file here that opens a socket.

Three details are load-bearing and none of them are obvious from the API docs:

`singleEvents=true` expands recurring events into occurrences. Without it the
response carries RRULEs, and expanding those correctly - exceptions, moved
instances, timezone-crossing rules - is a library, not a helper.

`showDeleted=true` is what makes a removed event arrive as `status: cancelled`
rather than simply not arriving. A row that vanished and a row that was
cancelled look the same to a sync that only sees what is present, so without
this the alternative is sweeping every row the window did not return, which
deletes real events whenever a partial window is fetched.

Pagination is not optional. `maxResults` caps at 250 and a working calendar
passes that in a quarter, so a single unpaged request silently returns a
prefix. Silence is the problem: the sync reports success and the planner sees
an empty afternoon that is actually full.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.services.calendar.busy import classify
from app.services.calendar.ports import (
    CalendarUnavailable,
    CredentialRejected,
    RemoteEvent,
)

TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

# Google's own ceiling; asking for more is silently clamped.
_PAGE_SIZE = 250
# A page cap, not a result cap. It exists so a pageToken that never terminates
# fails loudly instead of looping forever; hitting it raises rather than
# returning a prefix, because a truncated calendar reads as a free afternoon.
_MAX_PAGES = 40


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _zone(name: str | None) -> tzinfo:
    if not name:
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def _rfc3339(moment: datetime) -> str:
    # Google rejects a naive timeMin/timeMax outright rather than assuming UTC.
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _when(part: Mapping[str, Any] | None, zone: tzinfo) -> datetime | None:
    """A Google start/end is one of two shapes: timed, or an all-day date."""
    if not part:
        return None
    stamp = part.get("dateTime")
    if stamp:
        moment = datetime.fromisoformat(stamp)
        return moment if moment.tzinfo else moment.replace(tzinfo=zone)
    day = part.get("date")
    if day:
        # All-day events carry no offset, and the calendar's own timezone is
        # the only thing that says which midnight is meant.
        return datetime.combine(date.fromisoformat(day), time.min, tzinfo=zone)
    return None


def to_remote_event(payload: Mapping[str, Any], zone: tzinfo) -> RemoteEvent | None:
    """Normalize one payload, or None if it cannot be placed in time."""
    external_id = payload.get("id")
    start = _when(payload.get("start"), zone)
    end = _when(payload.get("end"), zone)
    if not external_id or start is None or end is None:
        # Nothing to draw and nothing to plan around. Skipped rather than
        # defaulted, because inventing a time would put it on a timeline.
        return None
    # Google omits `summary` on events shared as busy-only, which is exactly
    # when the traveler most needs to see that the slot is taken.
    title = (payload.get("summary") or "").strip() or "Busy"
    return RemoteEvent(
        external_id=external_id,
        title=title,
        location=(payload.get("location") or "").strip() or None,
        starts_at=start,
        ends_at=end,
        status=payload.get("status") or "confirmed",
        busy=classify(payload),
    )


class GoogleCalendarClient:
    """Reads the user's primary calendar with a stored refresh token.

    The access token is fetched once per client and held for its lifetime,
    which is one sync. Caching it across syncs would mean tracking expiry for
    an object that lives for seconds.
    """

    def __init__(
        self,
        refresh_token: str,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        http: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._refresh_token = refresh_token
        self._client_id = client_id or os.getenv("GOOGLE_CLIENT_ID") or ""
        self._client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET") or ""
        self._http = http
        self._timeout = timeout
        self._access_token: str | None = None

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self._http is not None:
            return await self._http.request(method, url, **kwargs)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.request(method, url, **kwargs)

    async def _token(self) -> str:
        if self._access_token:
            return self._access_token
        if not self._client_id or not self._client_secret:
            raise CalendarUnavailable("Google credentials are not configured")
        try:
            response = await self._request(
                "POST",
                TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.HTTPError as exc:
            raise CalendarUnavailable(f"Token refresh failed: {exc}") from exc

        if response.status_code == 400 and _json(response).get("error") == "invalid_grant":
            # The user revoked us, or the grant aged out of Testing mode's
            # 7-day window. Retrying is what keeps that invisible.
            raise CredentialRejected("The calendar grant is no longer valid")
        if response.status_code != 200:
            raise CalendarUnavailable(f"Token refresh returned {response.status_code}")

        token = _json(response).get("access_token")
        if not token:
            raise CalendarUnavailable("Token refresh returned no access token")
        self._access_token = token
        return token

    async def list_events(
        self, start: datetime, end: datetime
    ) -> Sequence[RemoteEvent]:
        token = await self._token()
        headers = {"Authorization": f"Bearer {token}"}
        events: list[RemoteEvent] = []
        page_token: str | None = None

        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {
                "timeMin": _rfc3339(start),
                "timeMax": _rfc3339(end),
                "singleEvents": "true",
                "orderBy": "startTime",
                "showDeleted": "true",
                "maxResults": _PAGE_SIZE,
            }
            if page_token:
                params["pageToken"] = page_token
            try:
                response = await self._request(
                    "GET", EVENTS_URL, params=params, headers=headers
                )
            except httpx.HTTPError as exc:
                raise CalendarUnavailable(f"Calendar read failed: {exc}") from exc

            if response.status_code in (401, 403):
                raise CredentialRejected(
                    f"Calendar read refused with {response.status_code}"
                )
            if response.status_code != 200:
                raise CalendarUnavailable(
                    f"Calendar read returned {response.status_code}"
                )

            body = _json(response)
            zone = _zone(body.get("timeZone"))
            for payload in body.get("items") or ():
                event = to_remote_event(payload, zone)
                if event is not None:
                    events.append(event)

            page_token = body.get("nextPageToken")
            if not page_token:
                return events

        raise CalendarUnavailable(
            f"Calendar paging did not terminate after {_MAX_PAGES} pages"
        )
