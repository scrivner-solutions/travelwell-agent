"""Frame, Decode and Repair, with no database and no provider.

The helpers come from `test_agent_schemas` on purpose rather than being copied:
a second `make_context` would drift from the first, and these tests are only
meaningful against the same context Verify is tested with.
"""

import json

import pytest

from app.agent.context import AreaCoverage
from app.agent.llm import FakeLLM, LlmResponse
from app.agent.prompts import PRETRIP_V1
from app.agent.runs import (
    RunFailed,
    decode,
    frame,
    invoke_verified,
    provenance_summary,
    render_violations,
    window_label,
)
from app.agent.schemas import Hotel, PlanProposal, ViolationCode
from app.db.models import AreaFillOutcome
from app.services.places.cache import AreaFill, FillSource
from tests.unit.test_agent_schemas import make_context, proposal

MODEL = "gemini-test"


# ---------------------------------------------------------------------------
# Stage 3: Frame
# ---------------------------------------------------------------------------


def test_frame_serialises_canonically():
    """Byte-identical payloads for the same context are what make replay a diff."""
    ctx = make_context()
    once, twice = frame(ctx, model=MODEL), frame(ctx, model=MODEL)
    assert once.payload == twice.payload
    assert once.payload == json.dumps(
        json.loads(once.payload), sort_keys=True, separators=(",", ":")
    )


def test_frame_carries_the_frozen_prompt_and_nothing_variable():
    """No trip data in the system prompt, or the cacheable prefix moves per run."""
    request = frame(make_context(), model=MODEL)
    assert request.system == PRETRIP_V1
    assert "Chicago" not in request.system
    assert "Chicago" in request.payload
    assert request.output_schema is PlanProposal
    assert request.tools == ()


# ---------------------------------------------------------------------------
# Stage 5: Decode
# ---------------------------------------------------------------------------


def test_decode_reads_a_normal_response():
    assert decode(LlmResponse(text='{"headline":"x"}')) == {"headline": "x"}


def test_decode_checks_stop_reason_before_parsing():
    """A truncated structured output is invalid JSON; saying so sends the reader
    after a schema problem that is not there."""
    with pytest.raises(RunFailed) as caught:
        decode(LlmResponse(text='{"headline": "unfinis', stop_reason="max_tokens"))
    assert caught.value.code == "decode:truncated"


def test_decode_reports_a_refusal_as_a_refusal():
    with pytest.raises(RunFailed) as caught:
        decode(LlmResponse(text="", stop_reason="refusal"))
    assert caught.value.code == "decode:refusal"


def test_decode_rejects_malformed_json():
    with pytest.raises(RunFailed) as caught:
        decode(LlmResponse(text="not json"))
    assert caught.value.code == "decode:malformed"


def test_decode_rejects_a_valid_json_document_that_is_not_an_object():
    with pytest.raises(RunFailed) as caught:
        decode(LlmResponse(text="[1, 2]"))
    assert caught.value.code == "decode:malformed"


# ---------------------------------------------------------------------------
# Stage 7: Repair
# ---------------------------------------------------------------------------


def test_render_violations_emits_codes_and_paths_not_prose():
    from app.agent.schemas import Violation

    rendered = render_violations(
        [Violation(ViolationCode.unknown_candidate, "$.items[0]", "c9 not in context")]
    )
    assert "unknown_candidate" in rendered
    assert "$.items[0]" in rendered


@pytest.mark.asyncio
async def test_a_valid_first_answer_costs_one_call():
    client = FakeLLM([json.dumps(proposal())])
    result = await invoke_verified(client, frame(make_context(), model=MODEL), make_context())
    assert isinstance(result.proposal, PlanProposal)
    assert client.call_count == 1
    assert result.spend.calls == 1
    assert result.spend.repairs == 0


@pytest.mark.asyncio
async def test_a_repair_turn_shows_the_model_its_own_output():
    """Not a retry from a clean slate: the second call carries the bad answer and
    the machine-generated list of what was wrong with it."""
    bad = json.dumps(proposal(items=[{**proposal()["items"][0], "window_id": "w9"}]))
    client = FakeLLM([bad, json.dumps(proposal())])

    result = await invoke_verified(client, frame(make_context(), model=MODEL), make_context())

    assert isinstance(result.proposal, PlanProposal)
    assert client.call_count == 2
    _, turns = client.calls[1]
    assert turns[0] == bad
    assert "unknown_window" in turns[1]
    # The repair rate is how a wrong prompt or schema announces itself, so it
    # has to survive the call rather than being visible only to FakeLLM.
    assert result.spend.calls == 2
    assert result.spend.repairs == 1


@pytest.mark.asyncio
async def test_the_second_failure_fails_the_run_rather_than_repairing_again():
    """Unbounded repair is a money leak that also hides the repair rate, which is
    how a wrong prompt or schema announces itself."""
    bad = json.dumps(proposal(items=[{**proposal()["items"][0], "window_id": "w9"}]))
    client = FakeLLM([bad, bad])

    with pytest.raises(RunFailed) as caught:
        await invoke_verified(client, frame(make_context(), model=MODEL), make_context())

    assert caught.value.code == "verify:invalid"
    assert ViolationCode.unknown_window in {v.code for v in caught.value.violations}
    assert client.call_count == 2
    # A run that repaired and still failed is the most expensive outcome there
    # is; recording nothing for it would hide exactly the wrong runs.
    assert caught.value.spend.calls == 2
    assert caught.value.spend.repairs == 1


@pytest.mark.asyncio
async def test_tokens_are_summed_across_the_repair_turn():
    """The undercount this exists to stop: reading usage off the final response
    reports half the cost of exactly the runs that cost double."""
    bad = json.dumps(proposal(items=[{**proposal()["items"][0], "window_id": "w9"}]))
    client = FakeLLM(
        [
            LlmResponse(text=bad, usage={"input_tokens": 100, "output_tokens": 20}),
            LlmResponse(
                text=json.dumps(proposal()),
                usage={"input_tokens": 140, "output_tokens": 30},
            ),
        ]
    )

    result = await invoke_verified(client, frame(make_context(), model=MODEL), make_context())

    assert result.spend.usage == {"input_tokens": 240, "output_tokens": 50}


@pytest.mark.asyncio
async def test_a_decode_failure_is_not_repaired():
    """Decode failures are provider or configuration problems. A repair turn on a
    refusal refuses again, at full price."""
    client = FakeLLM([LlmResponse(text="", stop_reason="refusal")])
    with pytest.raises(RunFailed) as caught:
        await invoke_verified(client, frame(make_context(), model=MODEL), make_context())
    assert caught.value.code == "decode:refusal"
    assert client.call_count == 1
    assert caught.value.spend.calls == 1


# ---------------------------------------------------------------------------
# Code-generated display strings
# ---------------------------------------------------------------------------


def test_window_label_is_ours():
    assert window_label(90) == "90 minutes free"


def a_fill(authoritative: bool, *, source=FillSource.fetched, outcome=None) -> AreaFill:
    return AreaFill(
        area_key="41.89,-87.63,8000,food",
        source=source,
        outcome=outcome,
        result_count=3,
        authoritative=authoritative,
    )


LOOKED = AreaCoverage.over((a_fill(True, outcome=AreaFillOutcome.ok),))
UNLOOKED = AreaCoverage.over((a_fill(False, source=FillSource.policy_declined),))


def test_provenance_describes_what_was_read_not_what_the_model_claimed():
    ctx = make_context()
    ctx.trip.hotel = Hotel(name="The Gwen")
    summary = provenance_summary(ctx, LOOKED)
    assert "your hotel" in summary
    assert f"{len(ctx.candidates)} places nearby" in summary


def test_provenance_never_names_a_source_that_was_not_read():
    ctx = make_context(commitments=[], candidates=[])
    assert provenance_summary(ctx, UNLOOKED) == "From your trip dates"


def test_provenance_stops_claiming_a_search_nobody_ran():
    """The defect: the string read identically whether we looked or not."""
    ctx = make_context()
    looked = provenance_summary(ctx, LOOKED)
    unlooked = provenance_summary(ctx, UNLOOKED)
    assert looked != unlooked, "the dishonest string is the one that never changed"
    assert f"{len(ctx.candidates)} places nearby" in looked
    assert f"{len(ctx.candidates)} places nearby" not in unlooked
    assert "on file" in unlooked


def test_provenance_counts_one_place_as_one_place():
    """The shipped string said "1 places nearby"."""
    ctx = make_context(candidates=make_context().candidates[:1])
    assert "1 place nearby" in provenance_summary(ctx, LOOKED)


def test_one_unlooked_area_makes_the_whole_count_dishonest():
    """AND, not OR: coverage is only as good as its worst area."""
    mixed = AreaCoverage.over((a_fill(True, outcome=AreaFillOutcome.ok), a_fill(False)))
    assert mixed.authoritative is False


def test_coverage_over_no_areas_at_all_is_not_authoritative():
    """`all(())` is True, so the vacuous reading of this is exactly backwards."""
    assert AreaCoverage.over(()).authoritative is False
    assert AreaCoverage.over(()).reasons() == ["places_coverage:not_attempted"]


def test_coverage_reasons_name_the_cause_and_are_empty_when_there_is_none():
    assert LOOKED.reasons() == []
    assert UNLOOKED.reasons() == ["places_coverage:policy_declined"]
    outage = AreaCoverage.over((a_fill(False, outcome=AreaFillOutcome.error),))
    assert outage.reasons() == ["places_coverage:error"]
