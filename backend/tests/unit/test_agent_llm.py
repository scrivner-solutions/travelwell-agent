"""The provider seam: scripted, recorded, and strict about running out."""

import dataclasses

import pytest

from app.agent.llm import FakeLLM, LlmRequest, LlmResponse
from app.agent.schemas import PlanProposal


def request() -> LlmRequest:
    return LlmRequest(
        model="gemini-x",
        system="frozen",
        payload='{"a":1}',
        output_schema=PlanProposal,
    )


@pytest.mark.asyncio
async def test_responses_come_back_in_order():
    llm = FakeLLM(["first", "second"])
    assert (await llm.complete(request())).text == "first"
    assert (await llm.complete(request())).text == "second"


@pytest.mark.asyncio
async def test_requests_are_recorded_with_their_repair_turns():
    llm = FakeLLM(["ok", "ok"])
    await llm.complete(request())
    await llm.complete(request(), turns=["unknown_window at items[0]"])
    assert llm.call_count == 2
    assert llm.calls[1][1] == ("unknown_window at items[0]",)


@pytest.mark.asyncio
async def test_running_out_is_an_error_not_a_default():
    """A repair loop that does not terminate is the bug worth catching."""
    llm = FakeLLM(["only one"])
    await llm.complete(request())
    with pytest.raises(AssertionError, match="ran out"):
        await llm.complete(request())


@pytest.mark.asyncio
async def test_stop_reason_can_be_scripted():
    llm = FakeLLM([LlmResponse(text="", stop_reason="max_tokens")])
    assert (await llm.complete(request())).stop_reason == "max_tokens"


def test_a_request_is_frozen_data():
    with pytest.raises(dataclasses.FrozenInstanceError):
        request().model = "something-else"
