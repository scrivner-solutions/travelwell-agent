"""The Google client: what it asks for, and how it reads what comes back.

No network. Every request is served by an httpx MockTransport, which is the
real client stack minus the socket - so the params asserted here are the params
that would go on the wire.

The three parameters worth a test each are `singleEvents`, `showDeleted` and
pagination. All three fail the same silent way if dropped: the sync reports
success and returns a calendar that is missing things.
"""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.services.calendar.google import (
    EVENTS_URL,
    TOKEN_URL,
    GoogleCalendarClient,
    to_remote_event,
)
from app.services.calendar.ports import CalendarUnavailable, CredentialRejected

pytestmark = pytest.mark.asyncio

WINDOW = (datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 30, tzinfo=UTC))


def _event(**over):
    base = {
        "id": "evt-1",
        "summary": "Standup",
        "status": "confirmed",
        "start": {"dateTime": "2026-09-02T09:00:00-07:00"},
        "end": {"dateTime": "2026-09-02T09:30:00-07:00"},
    }
    return base | over


def _client(handler):
    transport = httpx.MockTransport(handler)
    return GoogleCalendarClient(
        "refresh-abc",
        client_id="cid",
        client_secret="secret",
        http=httpx.AsyncClient(transport=transport),
    )


def _pages(*pages, token_status=200, token_body=None):
    """Serve the token endpoint, then one events page per call."""
    calls = {"events": 0, "requests": []}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["requests"].append(request)
        if str(request.url).startswith(TOKEN_URL):
            return httpx.Response(
                token_status, json=token_body or {"access_token": "at-1"}
            )
        page = pages[calls["events"]]
        calls["events"] += 1
        return httpx.Response(200, json=page)

    return handler, calls


async def test_it_asks_for_expanded_occurrences_and_deletions():
    handler, calls = _pages({"items": [_event()], "timeZone": "UTC"})

    await _client(handler).list_events(*WINDOW)

    events_request = calls["requests"][-1]
    query = parse_qs(urlsplit(str(events_request.url)).query)
    assert urlsplit(str(events_request.url))._replace(query="").geturl() == EVENTS_URL
    # Without this the response carries RRULEs, not occurrences.
    assert query["singleEvents"] == ["true"]
    # Without this a removed event simply stops arriving, which is
    # indistinguishable from never having existed.
    assert query["showDeleted"] == ["true"]
    assert query["timeMin"] == ["2026-09-01T00:00:00Z"]
    assert query["timeMax"] == ["2026-09-30T00:00:00Z"]


async def test_it_follows_every_page():
    handler, _ = _pages(
        {"items": [_event(id="a")], "nextPageToken": "p2", "timeZone": "UTC"},
        {"items": [_event(id="b")], "timeZone": "UTC"},
    )

    events = await _client(handler).list_events(*WINDOW)

    # A single unpaged request returns a prefix and calls it a calendar.
    assert [e.external_id for e in events] == ["a", "b"]


async def test_paging_that_never_ends_raises_rather_than_truncating():
    def handler(request):
        if str(request.url).startswith(TOKEN_URL):
            return httpx.Response(200, json={"access_token": "at-1"})
        return httpx.Response(
            200, json={"items": [_event()], "nextPageToken": "always", "timeZone": "UTC"}
        )

    with pytest.raises(CalendarUnavailable):
        await _client(handler).list_events(*WINDOW)


async def test_a_revoked_grant_is_its_own_error():
    handler, _ = _pages(
        {"items": []}, token_status=400, token_body={"error": "invalid_grant"}
    )

    with pytest.raises(CredentialRejected):
        await _client(handler).list_events(*WINDOW)


async def test_a_refused_read_is_a_rejected_credential_not_an_outage():
    def handler(request):
        if str(request.url).startswith(TOKEN_URL):
            return httpx.Response(200, json={"access_token": "at-1"})
        return httpx.Response(403, json={"error": "forbidden"})

    # 403 here means the scope was removed, which retrying cannot fix.
    with pytest.raises(CredentialRejected):
        await _client(handler).list_events(*WINDOW)


async def test_a_server_error_is_transient_not_a_credential_problem():
    def handler(request):
        if str(request.url).startswith(TOKEN_URL):
            return httpx.Response(200, json={"access_token": "at-1"})
        return httpx.Response(503, text="upstream")

    with pytest.raises(CalendarUnavailable) as caught:
        await _client(handler).list_events(*WINDOW)
    assert not isinstance(caught.value, CredentialRejected)


async def test_the_token_is_fetched_once_per_client():
    handler, calls = _pages(
        {"items": [], "nextPageToken": "p2"}, {"items": []}
    )

    await _client(handler).list_events(*WINDOW)

    token_calls = [r for r in calls["requests"] if str(r.url).startswith(TOKEN_URL)]
    assert len(token_calls) == 1


# --- reading one payload --------------------------------------------------


def test_an_all_day_event_lands_on_the_calendars_own_midnight():
    from zoneinfo import ZoneInfo

    event = to_remote_event(
        _event(start={"date": "2026-09-02"}, end={"date": "2026-09-03"}),
        ZoneInfo("Asia/Tokyo"),
    )

    # Read as UTC this is 09-01T15:00 Tokyo, which is the previous day.
    assert event.starts_at == datetime(2026, 9, 2, tzinfo=ZoneInfo("Asia/Tokyo"))
    # All-day events do not block time; classify() already says so.
    assert event.busy is False


def test_an_event_with_no_summary_is_still_shown_as_taken():
    event = to_remote_event(_event(summary=None), UTC)

    # Google omits the summary on busy-only shares, which is exactly when the
    # traveler needs to know the slot is gone.
    assert event.title == "Busy"
    assert event.busy is True


def test_a_cancelled_event_is_returned_and_marked_not_busy():
    event = to_remote_event(_event(status="cancelled"), UTC)

    assert event.status == "cancelled"
    assert event.busy is False


def test_an_event_with_no_time_is_skipped_rather_than_invented():
    assert to_remote_event(_event(start={}, end={}), UTC) is None
