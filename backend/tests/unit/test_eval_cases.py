"""The case schema, and proof its guards fire.

Every rejection below has a positive control above it: the same case passes with
the one bad field corrected. A validator that never rejects anything looks
identical to one that works, and the suite it guards would look green either way.
"""

import json

import pytest
from pydantic import ValidationError

from tests.eval.assistant.cases import (
    SUITE_DIR,
    Case,
    ExpectedChange,
    Suite,
    bind_items,
    digest_of,
    load_suite,
)

SUITE = SUITE_DIR / "assistant-v1.json"

GOOD = {
    "id": "c1",
    "scene": "chicago_gym_planned",
    "mode": "controller",
    "turns": [
        {
            "utterance": "skip the gym",
            "scripted": [{"reply": "ok", "actions": []}],
            "expect": {"applied": [{"item": "Hotel gym"}]},
        }
    ],
}


def variant(**over) -> dict:
    return {**json.loads(json.dumps(GOOD)), **over}


def test_shipped_suite_validates():
    suite = load_suite(SUITE)
    assert {c.id for c in suite.cases} >= {"skip_gym_plain", "unskip_not_a_verb"}
    # The sequence is not hypothetical: a case in the shipped suite uses it.
    assert any(len(c.turns) > 1 for c in suite.cases)


def test_control_the_good_case_passes():
    assert Case.model_validate(GOOD).mode == "controller"


def test_typo_in_a_field_name_is_rejected():
    bad = variant()
    bad["turns"][0]["expect"]["applyed"] = []
    with pytest.raises(ValidationError):
        Case.model_validate(bad)


def test_unknown_refusal_code_is_rejected():
    bad = variant()
    bad["turns"][0]["expect"]["refused"] = [{"code": "status:tired"}]
    with pytest.raises(ValidationError, match="unknown refusal code"):
        Case.model_validate(bad)
    bad["turns"][0]["expect"]["refused"] = [{"code": "status:confirmed"}]
    Case.model_validate(bad)


def test_prompt_mode_may_not_script_the_model():
    with pytest.raises(ValidationError, match="would test nothing"):
        Case.model_validate(variant(mode="prompt"))


def test_controller_mode_needs_a_script():
    bad = variant()
    del bad["turns"][0]["scripted"]
    with pytest.raises(ValidationError, match="needs a scripted"):
        Case.model_validate(bad)


def test_an_empty_script_is_not_a_missing_one():
    """`[]` asserts the model is never called, so it must satisfy the guard."""
    ok = variant()
    ok["turns"][0]["scripted"] = []
    assert Case.model_validate(ok).turns[0].scripted == []


def test_duplicate_case_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate case ids"):
        Suite.model_validate({"cases": [GOOD, variant()]})


def test_item_placeholders_bind_by_name():
    body = json.dumps({"actions": [{"item_id": "{{item:Hotel gym}}"}]})
    assert "abc-123" in bind_items(body, {"Hotel gym": "abc-123"})
    with pytest.raises(KeyError, match="not in the plan"):
        bind_items(body, {"Rooftop bar": "abc-123"})


def test_digest_separates_a_changed_question_from_a_moody_model():
    base = digest_of("system", "payload")
    assert base == digest_of("system", "payload")
    assert base != digest_of("system v2", "payload")
    assert base != digest_of("system", "payload with one more item")


def test_unskip_expectation_is_unwritable_until_the_verb_exists():
    """The schema refuses to describe an outcome the controller cannot produce.

    Same discipline as `AssistantAction.kind`: a second verb is a second member,
    and until it is added a case cannot quietly assert a status nothing sets.
    """
    with pytest.raises(ValidationError):
        ExpectedChange.model_validate({"item": "Hotel gym", "status": "planned"})
