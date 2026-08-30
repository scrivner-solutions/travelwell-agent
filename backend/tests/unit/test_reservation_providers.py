"""Rules every reservation provider has to obey, and the simulator's own.

The first half is a contract suite, parametrized over implementations. It is
the portability guarantee in executable form: adding a real client means adding
it to `PROVIDERS` and running this, not writing a fresh set of tests and hoping
they cover the same ground. Each rule here is one the executor or the database
actually depends on, so a client that breaks one breaks something real.

The second half is specific to the simulator, and is about the properties that
make a demo rehearsable rather than merely green.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import ReservationProvider, ReservationStatus
from app.services.reservations import (
    BookingHandle,
    BookingRequest,
    Rules,
    SimulatedProvider,
    Timings,
    UnsupportedProvider,
    provider_for,
)
from app.services.reservations.external_link import ExternalLinkProvider

pytestmark = pytest.mark.asyncio

START = datetime(2026, 8, 30, 18, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def build(name: str, clock: Clock):
    if name == "travelwell":
        return SimulatedProvider(
            clock=clock,
            timings=Timings(timedelta(seconds=2), timedelta(seconds=6)),
            rules=Rules(max_party=8, declining_places=frozenset({"mildreds"})),
        )
    return ExternalLinkProvider(clock=clock)


PROVIDERS = ["travelwell", "external_link"]


def a_request(**overrides) -> BookingRequest:
    return BookingRequest(
        **{
            "place_name": "Beatrix",
            "slot_at": START + timedelta(hours=2),
            "party_size": 2,
            "idempotency_key": "test-key",
            **overrides,
        }
    )


# --- the contract every provider owes the executor ------------------------


@pytest.mark.parametrize("name", PROVIDERS)
async def test_place_returns_a_handle_that_names_its_own_provider(name):
    clock = Clock()
    provider = build(name, clock)
    handle = await provider.place(a_request())
    assert handle.provider is provider.provider
    assert handle.reference
    assert handle.placed_at == START


@pytest.mark.parametrize("name", PROVIDERS)
async def test_the_handle_survives_a_round_trip_through_json(name):
    """It is persisted in pending_actions.execution_result, so the executor can
    restart mid-booking and keep polling something it did not submit."""
    clock = Clock()
    handle = await build(name, clock).place(a_request())
    restored = BookingHandle.from_json(handle.to_json())
    assert restored == handle


@pytest.mark.parametrize("name", PROVIDERS)
async def test_polling_twice_without_time_passing_says_the_same_thing(name):
    clock = Clock()
    provider = build(name, clock)
    handle = await provider.place(a_request())
    clock.advance(3)
    first, second = await provider.poll(handle), await provider.poll(handle)
    assert first.status is second.status
    assert first.confirmation_code == second.confirmation_code


@pytest.mark.parametrize("name", PROVIDERS)
async def test_every_booking_settles(name):
    """An attempt that never becomes terminal is an executor that never stops."""
    clock = Clock()
    provider = build(name, clock)
    handle = await provider.place(a_request())
    for _ in range(20):
        update = await provider.poll(handle)
        if update.terminal:
            break
        clock.advance(2)
    else:
        pytest.fail(f"{name} never reached a terminal update")


@pytest.mark.parametrize("name", PROVIDERS)
async def test_a_confirmation_always_carries_its_code(name):
    """reservations_check enforces this in the database. A client that forgets
    fails at the constraint, which is the right place to fail but a poor place
    to find out."""
    clock = Clock()
    provider = build(name, clock)
    handle = await provider.place(a_request())
    for _ in range(20):
        update = await provider.poll(handle)
        if update.status is ReservationStatus.confirmed:
            assert update.confirmation_code
        if update.terminal:
            break
        clock.advance(2)


@pytest.mark.parametrize("name", PROVIDERS)
async def test_a_refusal_always_says_why(name):
    clock = Clock()
    provider = build(name, clock)
    handle = await provider.place(a_request(place_name="Mildreds", party_size=30))
    for _ in range(20):
        update = await provider.poll(handle)
        if update.status is ReservationStatus.failed:
            assert update.failure_reason
        if update.terminal:
            break
        clock.advance(2)


@pytest.mark.parametrize("name", PROVIDERS)
async def test_every_answer_carries_evidence(name):
    """`raw` becomes pending_actions.verification: what we were told, kept
    apart from what we concluded."""
    clock = Clock()
    provider = build(name, clock)
    handle = await provider.place(a_request())
    clock.advance(30)
    update = await provider.poll(handle)
    assert update.raw["provider"] == provider.provider.value
    assert update.raw["reference"] == handle.reference


@pytest.mark.parametrize("name", PROVIDERS)
async def test_cancel_reaches_a_terminal_answer(name):
    clock = Clock()
    provider = build(name, clock)
    handle = await provider.place(a_request())
    clock.advance(30)
    assert (await provider.cancel(handle)).terminal


# --- the simulator's own promises ----------------------------------------


async def test_the_walk_is_ordered_and_complete():
    """pending -> holding -> confirmed. Skipping a state would put back in code
    exactly the limitation the seed already has."""
    clock = Clock()
    provider = build("travelwell", clock)
    handle = await provider.place(a_request())
    seen = []
    for _ in range(6):
        seen.append((await provider.poll(handle)).status.value)
        clock.advance(2)
    assert seen[0] == "pending"
    assert "holding" in seen
    assert seen[-1] == "confirmed"
    assert seen.index("pending") < seen.index("holding") < seen.index("confirmed")


async def test_a_refusal_never_holds_a_table_first():
    """A venue that will not take the booking says so; it does not hold a table
    and then change its mind. This is the pending -> failed edge."""
    clock = Clock()
    provider = build("travelwell", clock)
    handle = await provider.place(a_request(party_size=12))
    seen = []
    for _ in range(6):
        seen.append((await provider.poll(handle)).status.value)
        clock.advance(2)
    assert "holding" not in seen
    assert seen[-1] == "failed"


async def test_outcomes_are_steerable_so_a_demo_can_be_rehearsed():
    """Same request, same outcome, every time. A simulator that failed on a
    coin flip could not be shown to anyone twice."""
    clock = Clock()
    provider = build("travelwell", clock)
    for _ in range(5):
        handle = await provider.place(a_request(place_name="Mildreds"))
        clock.advance(30)
        update = await provider.poll(handle)
        assert update.status is ReservationStatus.failed
        assert "Mildreds" in update.failure_reason
        clock.now = START


async def test_the_same_idempotency_key_is_the_same_booking():
    clock = Clock()
    provider = build("travelwell", clock)
    first = await provider.place(a_request(idempotency_key="abc"))
    second = await provider.place(a_request(idempotency_key="abc"))
    third = await provider.place(a_request(idempotency_key="xyz"))
    assert first.reference == second.reference
    assert third.reference != first.reference


async def test_a_confirmation_code_is_readable_out_loud():
    """No characters that are ambiguous in print: a code gets read to a host."""
    clock = Clock()
    provider = build("travelwell", clock)
    handle = await provider.place(a_request())
    clock.advance(30)
    code = (await provider.poll(handle)).confirmation_code
    assert len(code) == 5
    assert not set(code) & set("OI01")


async def test_external_link_claims_nothing_and_says_where_to_go():
    clock = Clock()
    handle = await ExternalLinkProvider(clock=clock).place(a_request())
    update = await ExternalLinkProvider(clock=clock).poll(handle)
    assert update.status is ReservationStatus.pending
    assert update.handed_off is True
    # Finished without being a terminal *status*: nothing on our side will move it.
    assert update.terminal is True
    assert update.confirmation_code is None
    assert "Beatrix" in update.external_url


async def test_an_unbuilt_provider_refuses_rather_than_falling_back():
    """`opentable` has been in the enum since the first migration and nothing
    has ever called it. Silently using the simulator instead would book a table
    the real provider never heard about."""
    with pytest.raises(UnsupportedProvider, match="opentable"):
        provider_for(ReservationProvider.opentable)


async def test_a_place_id_survives_onto_the_request():
    place = uuid.uuid4()
    assert a_request(place_id=place).place_id == place
