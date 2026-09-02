"""Verify: one test per violation code, plus the two tiers failing differently.

The database CHECKs are the backstop, not the error surface. Anything Postgres
would reject has to fail here first, with a code that names the problem, so
every code below is a promise about a run that never reaches Commit.
"""

import json
from pathlib import Path

import pytest

from app.agent.schemas import (
    Candidate,
    ContextMeta,
    ContextPreferences,
    ContextWindow,
    PlanProposal,
    SessionMinutes,
    TripContext,
    TripFacts,
    ViolationCode,
    sanitize_prose,
    verify,
)

SNAPSHOT = Path(__file__).parent / "snapshots" / "plan_proposal.schema.json"


def make_context(**overrides) -> TripContext:
    base = {
        "meta": ContextMeta(
            prompt_version="pretrip-v1",
            generated_at="2026-09-02T14:00:00Z",
            run_kind="pretrip_plan",
        ),
        "trip": TripFacts(
            destination="Chicago",
            start_date="2026-09-09",
            end_date="2026-09-12",
            timezone="America/Chicago",
        ),
        "windows": [
            ContextWindow(
                id="w1", day="2026-09-09", start="17:30", end="19:30", minutes=120
            ),
            ContextWindow(
                id="w2", day="2026-09-09", start="20:00", end="21:30", minutes=90
            ),
        ],
        "preferences": ContextPreferences(
            dietary=["vegetarian"],
            workout_kinds=["swim"],
            facilities=["pool"],
            day_pass_max_cents=2000,
            price_level_max=2,
            session_minutes=SessionMinutes(min=45, max=90),
        ),
        "candidates": [
            Candidate(
                id="c1",
                kind="activity",
                window_ids=["w1", "w2"],
                name="Lakeshore Sport & Fitness",
                day_pass_cents=2000,
                amenities=["pool"],
            ),
            Candidate(
                id="c2",
                kind="activity",
                window_ids=["w1"],
                name="Hotel fitness room",
                day_pass_cents=0,
                amenities=["treadmill"],
            ),
            Candidate(
                id="c3",
                kind="meal",
                window_ids=["w2"],
                name="Beatrix",
                price_level=2,
                amenities=["vegetarian"],
            ),
        ],
    }
    return TripContext(**{**base, **overrides})


def proposal(**overrides) -> dict:
    base = {
        "headline": "Room for a swim",
        "window_notes": [],
        "items": [
            {
                "window_id": "w1",
                "kind": "activity",
                "start": "17:40",
                "end": "18:45",
                "options": [
                    {
                        "candidate_id": "c1",
                        "reason": "Pool for your swim",
                        "matched_preferences": ["swim", "45-90 min"],
                        "state": "selected",
                        "rank": 1,
                    }
                ],
            }
        ],
    }
    return {**base, **overrides}


def codes(result) -> set[ViolationCode]:
    return {v.code for v in result}


def test_a_well_formed_proposal_verifies():
    result = verify(proposal(), make_context())
    assert isinstance(result, PlanProposal)
    assert result.items[0].options[0].state == "selected"


def test_unknown_window():
    payload = proposal()
    payload["items"][0]["window_id"] = "w9"
    assert codes(verify(payload, make_context())) == {ViolationCode.unknown_window}


def test_unknown_candidate():
    payload = proposal()
    payload["items"][0]["options"][0]["candidate_id"] = "c99"
    assert ViolationCode.unknown_candidate in codes(verify(payload, make_context()))


def test_candidate_window_mismatch():
    """c3 was only ever fetched for w2; using it in w1 is not a lookup miss."""
    payload = proposal()
    payload["items"][0]["options"][0]["candidate_id"] = "c3"
    assert ViolationCode.candidate_window_mismatch in codes(
        verify(payload, make_context())
    )


def test_outside_window():
    payload = proposal()
    payload["items"][0]["start"] = "16:00"
    assert ViolationCode.outside_window in codes(verify(payload, make_context()))


def test_duration_out_of_range():
    payload = proposal()
    payload["items"][0]["end"] = "17:50"  # 10 minutes, floor is 45
    assert ViolationCode.duration_out_of_range in codes(verify(payload, make_context()))


def test_duration_is_not_checked_for_meals():
    """`session_minutes` is a workout preference; a short dinner is not a bug."""
    payload = proposal()
    payload["items"][0]["kind"] = "meal"
    payload["items"][0]["end"] = "17:50"
    assert ViolationCode.duration_out_of_range not in codes(
        verify(payload, make_context())
    )


def test_overlapping_items():
    payload = proposal()
    payload["items"].append(
        {
            "window_id": "w1",
            "kind": "activity",
            "start": "18:00",
            "end": "19:00",
            "options": [
                {"candidate_id": "c2", "state": "selected", "rank": 1},
            ],
        }
    )
    assert ViolationCode.overlapping_items in codes(verify(payload, make_context()))


def test_no_selected():
    payload = proposal()
    payload["items"][0]["options"][0]["state"] = "alternative"
    assert ViolationCode.no_selected in codes(verify(payload, make_context()))


def test_multiple_selected():
    payload = proposal()
    payload["items"][0]["options"].append(
        {"candidate_id": "c2", "state": "selected", "rank": 2}
    )
    assert ViolationCode.multiple_selected in codes(verify(payload, make_context()))


def test_rejection_reason_missing():
    payload = proposal()
    payload["items"][0]["options"].append(
        {"candidate_id": "c2", "state": "rejected", "rank": 2}
    )
    assert ViolationCode.rejection_reason_missing in codes(
        verify(payload, make_context())
    )


def test_duplicate_rank():
    payload = proposal()
    payload["items"][0]["options"].append(
        {"candidate_id": "c2", "state": "alternative", "rank": 1}
    )
    assert ViolationCode.duplicate_rank in codes(verify(payload, make_context()))


def test_hard_preference_violation_on_budget():
    context = make_context()
    context.candidates[0].day_pass_cents = 3500
    assert ViolationCode.hard_preference_violation in codes(
        verify(proposal(), context)
    )


def test_hard_preference_violation_on_dietary_for_a_meal():
    payload = proposal()
    payload["items"][0]["kind"] = "meal"
    payload["items"][0]["end"] = "18:30"
    payload["items"][0]["options"][0]["candidate_id"] = "c2"  # no vegetarian tag
    assert ViolationCode.hard_preference_violation in codes(
        verify(payload, make_context())
    )


def test_unknown_preference_token():
    payload = proposal()
    payload["items"][0]["options"][0]["matched_preferences"] = ["pilates"]
    assert ViolationCode.unknown_preference_token in codes(
        verify(payload, make_context())
    )


def test_the_session_length_token_is_in_the_vocabulary():
    assert "45-90 min" in make_context().preference_vocabulary()


def test_schema_mismatch_when_the_payload_is_not_the_schema():
    result = verify({"items": "not a list"}, make_context())
    assert codes(result) == {ViolationCode.schema_mismatch}


# --- the prose tier: never fails a run -------------------------------------


def test_prose_is_sanitized_not_rejected():
    payload = proposal(headline="**Room** for a swim\x07")
    result = verify(payload, make_context())
    assert isinstance(result, PlanProposal)
    assert result.headline == "Room for a swim"


def test_agent_first_person_is_dropped():
    assert sanitize_prose("I found you a pool", 120) == ""


def test_a_rejection_reason_emptied_by_the_sanitizer_gets_a_fallback():
    """Otherwise the prose tier would fail a run through the db CHECK."""
    payload = proposal()
    payload["items"][0]["options"].append(
        {
            "candidate_id": "c2",
            "state": "rejected",
            "rank": 2,
            "rejection_reason": "I think the treadmill is worse",
        }
    )
    result = verify(payload, make_context())
    assert isinstance(result, PlanProposal)
    assert result.items[0].options[1].rejection_reason.strip()


def test_over_long_prose_is_truncated():
    payload = proposal(headline="x" * 500)
    # The schema cap rejects it before the sanitizer ever sees it, which is the
    # cheaper of the two places to stop it.
    assert codes(verify(payload, make_context())) == {ViolationCode.schema_mismatch}


# --- the empty decision space ----------------------------------------------


def test_no_windows_is_an_empty_decision_space():
    assert make_context(windows=[]).is_empty_decision_space()


def test_windows_with_no_reachable_candidate_are_empty_too():
    context = make_context(candidates=[])
    assert context.is_empty_decision_space()


def test_a_window_with_a_candidate_is_not_empty():
    assert not make_context().is_empty_decision_space()


# --- the wire contract ------------------------------------------------------


def test_plan_proposal_json_schema_matches_the_snapshot():
    """A Pydantic upgrade must not silently change what the provider is sent.

    Regenerate deliberately with:
        uv run python -c "from app.agent.schemas import PlanProposal; import json;
        print(json.dumps(PlanProposal.model_json_schema(), indent=2, sort_keys=True))"
    """
    actual = json.loads(
        json.dumps(PlanProposal.model_json_schema(), sort_keys=True)
    )
    assert actual == json.loads(SNAPSHOT.read_text())


@pytest.mark.parametrize(
    "definition", PlanProposal.model_json_schema()["$defs"].values()
)
def test_every_object_forbids_extra_properties(definition):
    assert definition.get("additionalProperties") is False


def _prefs(**overrides) -> ContextPreferences:
    """The default preferences with one field changed.

    Building a bare `ContextPreferences` instead empties the vocabulary that
    `matched_preferences` resolve against, so the proposal fails on a code the
    test was not about.
    """
    return make_context().preferences.model_copy(update=overrides)


def _second_item() -> dict:
    """A legal second item: different window, no overlap, in-range duration."""
    return {
        "window_id": "w2",
        "kind": "activity",
        "start": "20:10",
        "end": "21:15",
        "options": [
            {"candidate_id": "c1", "matched_preferences": [], "state": "selected", "rank": 1}
        ],
    }


def test_output_size_is_capped_by_verify_not_by_the_schema():
    """The cap moved out of `maxItems`, so this asserts the ceiling holds.

    Asserting the keyword's presence was testing the proxy: it passed for a
    year while the wire schema stripped the keyword before it was ever sent.
    """
    assert "maxItems" not in json.dumps(PlanProposal.model_json_schema())

    payload = proposal()
    payload["items"].append(_second_item())
    ctx = make_context(preferences=_prefs(target_sessions=1))
    assert ViolationCode.too_many_items in codes(verify(payload, ctx))


def test_target_sessions_absent_allows_more_than_one_item():
    """Demonstration two: it stays quiet, and for the right reason.

    Without this, a check that rejected every multi-item plan would look
    identical to a working one on the test above.
    """
    payload = proposal()
    payload["items"].append(_second_item())
    result = verify(payload, make_context())
    assert isinstance(result, PlanProposal)
    assert len(result.items) == 2


def test_too_many_items_falls_back_to_max_items():
    payload = proposal(items=[proposal()["items"][0] for _ in range(13)])
    assert ViolationCode.too_many_items in codes(verify(payload, make_context()))


def test_too_many_options():
    """Co-fires with `duplicate_rank`, and is kept for the repair message.

    Five options cannot have unique ranks while `rank` is bounded at 4, so
    `duplicate_rank` fires too - but it sends a repair turn to renumber when
    the real instruction is to drop one.
    """
    payload = proposal()
    option = payload["items"][0]["options"][0]
    payload["items"][0]["options"] = [
        {**option, "rank": r} for r in (1, 2, 3, 4, 4)
    ]
    assert ViolationCode.too_many_options in codes(verify(payload, make_context()))


def test_enum_values_are_matched_case_insensitively():
    """Structured output does not guarantee enum capitalization."""
    payload = proposal()
    payload["items"][0]["kind"] = "Activity"
    payload["items"][0]["options"][0]["state"] = "SELECTED"
    result = verify(payload, make_context())
    assert isinstance(result, PlanProposal)
    assert (result.items[0].kind, result.items[0].options[0].state) == (
        "activity",
        "selected",
    )
