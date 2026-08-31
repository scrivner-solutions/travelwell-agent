"""The provider config: what we send Gemini, and what still enforces the rest.

These exist because 528 green tests said the agent worked while the very first
real call returned 400. `FakeLLM` exercises every stage except the one that
builds a provider request, so nothing here can be checked by the pipeline tests.
"""

import pytest

from app.agent.gemini import (
    _UNSERVABLE,
    DEFAULT_MODEL,
    thinking_config,
    wire_schema,
)
from app.agent.schemas import PlanProposal, verify


class _EmptyContext:
    windows: list = []
    candidates: list = []


def _keywords(node, found=None):
    found = found if found is not None else set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            _keywords(value, found)
    elif isinstance(node, list):
        for value in node:
            _keywords(value, found)
    return found


def test_the_wire_schema_carries_no_unservable_constraint():
    """Vertex compiles these into a state machine and ours overflows it.

    Checked over the whole tree, `$defs` included: `PlanProposal`'s patterns and
    array bounds live on nested models, so a top-level check would pass while
    the request still 400s.
    """
    assert _keywords(wire_schema(PlanProposal)) & _UNSERVABLE == set()


def test_the_wire_schema_keeps_the_shape():
    """Only value matchers go. Structure is what the schema is for."""
    kept = _keywords(wire_schema(PlanProposal))
    assert {"properties", "required", "type", "$defs", "$ref"} <= kept


def test_pydantic_still_rejects_what_the_wire_schema_stopped_asking_for():
    """The accuser for the trade `wire_schema` makes.

    Dropping the constraints is only safe because `verify` re-applies them, so a
    malformed time becomes a repair turn rather than an accepted plan. Delete
    the pattern from the model believing the provider enforces it and this is
    what objects.
    """
    result = verify(
        {
            "headline": "x",
            "items": [
                {
                    "window_id": "w1",
                    "kind": "activity",
                    "start": "9am",
                    "end": "25:00",
                    "options": [],
                }
            ],
            "window_notes": [],
        },
        _EmptyContext(),
    )
    assert not isinstance(result, PlanProposal)
    paths = {v.path for v in result}
    assert {"items.0.start", "items.0.end"} <= paths
    # The path and the offending value, not a count. A repair turn is given to
    # a machine, and "3 validation errors" names nothing it can change.
    assert any("9am" in v.detail for v in result)


@pytest.mark.parametrize(
    "model,field",
    [
        ("gemini-2.5-pro", "thinking_budget"),
        ("gemini-2.0-flash", "thinking_budget"),
        ("gemini-3.5-flash", "thinking_level"),
        ("gemini-3.1-pro-preview", "thinking_level"),
        # Unparseable names are assumed newer, which is the direction models move.
        ("some-future-model", "thinking_level"),
    ],
)
def test_effort_uses_the_spelling_this_generation_accepts(model, field):
    """2.5 rejects `thinking_level` outright; 3.x has no `thinking_budget`."""
    config = thinking_config(model, "high")
    assert getattr(config, field) is not None
    other = "thinking_level" if field == "thinking_budget" else "thinking_budget"
    assert getattr(config, other) is None


def test_the_default_model_is_one_that_takes_a_thinking_level():
    """`DEFAULT_MODEL` and the effort spelling have to agree.

    They did not, and that was the whole of the first 400: the default was 2.5
    and the config sent `thinking_level` unconditionally.
    """
    level = thinking_config(DEFAULT_MODEL, "high").thinking_level
    # The SDK coerces the string into a `ThinkingLevel` member, so compare on
    # the value rather than the name we passed in.
    assert str(getattr(level, "value", level)).lower() == "high"


@pytest.mark.integration_live
@pytest.mark.asyncio
async def test_vertex_accepts_the_request_we_actually_build():
    """The gate that was missing, and the only kind that could have fired.

    Every other agent test uses `FakeLLM`, which accepts any config because it
    never looks at one. This asserts the provider does.

    Deselected by default everywhere - `addopts` in pyproject.toml, not this
    marker on its own - because it costs a call and needs credentials. Run it
    with `-m integration_live` after any change to `_config`, the default
    model, or `PlanProposal`'s field constraints, the three things that can
    break it.
    """
    from app.agent.gemini import GeminiClient
    from app.agent.llm import LlmRequest

    client = GeminiClient()
    response = await client.complete(
        LlmRequest(
            model=client.model,
            system="Return an empty plan.",
            payload='{"windows":[],"candidates":[]}',
            output_schema=PlanProposal,
        )
    )
    # Not asserting on the plan itself: this is about whether the request is
    # well-formed, and a 400 raises before there is anything to assert on.
    assert response.stop_reason == "end_turn"


def test_wire_schema_prunes_nothing_today():
    """`_UNSERVABLE` is a backstop, and this is what makes it a loud one.

    `maxItems` is the keyword Vertex refuses to compile at `PlanProposal`'s
    nesting depth, so the bounds live in Verify now and nothing should be
    stripped on the way out. If someone adds `max_length=` to a list field the
    request keeps working - which is the point of the backstop - but the
    constraint silently stops applying, and only this catches that.
    """
    from app.agent.gemini import wire_schema
    from app.agent.schemas import PlanProposal

    assert wire_schema(PlanProposal) == PlanProposal.model_json_schema()


def test_enum_survives_into_the_wire_schema():
    """`pattern` is not a documented `responseJsonSchema` keyword and `enum` is.

    `state` and `kind` are `Literal` for this reason: it is the only spelling
    of those two fields the grammar itself enforces.
    """
    from app.agent.gemini import wire_schema
    from app.agent.schemas import PlanProposal

    defs = wire_schema(PlanProposal)["$defs"]
    assert defs["ProposedOption"]["properties"]["state"]["enum"] == [
        "selected",
        "alternative",
        "rejected",
    ]
    assert defs["ProposedItem"]["properties"]["kind"]["enum"] == ["activity", "meal"]
