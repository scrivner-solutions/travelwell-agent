"""Frame, Decode and Repair, with no database and no provider.

The helpers come from `test_agent_schemas` on purpose rather than being copied:
a second `make_context` would drift from the first, and these tests are only
meaningful against the same context Verify is tested with.
"""

import json

import pytest

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
    assert isinstance(result, PlanProposal)
    assert client.call_count == 1


@pytest.mark.asyncio
async def test_a_repair_turn_shows_the_model_its_own_output():
    """Not a retry from a clean slate: the second call carries the bad answer and
    the machine-generated list of what was wrong with it."""
    bad = json.dumps(proposal(items=[{**proposal()["items"][0], "window_id": "w9"}]))
    client = FakeLLM([bad, json.dumps(proposal())])

    result = await invoke_verified(client, frame(make_context(), model=MODEL), make_context())

    assert isinstance(result, PlanProposal)
    assert client.call_count == 2
    _, turns = client.calls[1]
    assert turns[0] == bad
    assert "unknown_window" in turns[1]


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


@pytest.mark.asyncio
async def test_a_decode_failure_is_not_repaired():
    """Decode failures are provider or configuration problems. A repair turn on a
    refusal refuses again, at full price."""
    client = FakeLLM([LlmResponse(text="", stop_reason="refusal")])
    with pytest.raises(RunFailed) as caught:
        await invoke_verified(client, frame(make_context(), model=MODEL), make_context())
    assert caught.value.code == "decode:refusal"
    assert client.call_count == 1


# ---------------------------------------------------------------------------
# Code-generated display strings
# ---------------------------------------------------------------------------


def test_window_label_is_ours():
    assert window_label(90) == "90 minutes free"


def test_provenance_describes_what_was_read_not_what_the_model_claimed():
    ctx = make_context()
    ctx.trip.hotel = Hotel(name="The Gwen")
    summary = provenance_summary(ctx)
    assert "your hotel" in summary
    assert f"{len(ctx.candidates)} places nearby" in summary


def test_provenance_never_names_a_source_that_was_not_read():
    ctx = make_context(commitments=[], candidates=[])
    assert provenance_summary(ctx) == "From your trip dates"
