"""Tests for scripts/check_openapi_drift.py.

A drift check that over-normalizes stops reporting anything and nobody notices,
because a silent gate looks exactly like a passing one. So the cases here run in
both directions: drift that must be caught, and harmless spelling differences
between the two documents that must not be.
"""

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_checker():
    """The check lives in scripts/, which is not a package."""
    path = BACKEND_DIR / "scripts" / "check_openapi_drift.py"
    spec = importlib.util.spec_from_file_location("check_openapi_drift", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


drift = _load_checker()


def compare(declared_schemas, served_schemas, root="Root"):
    """Walk two component sets from a shared root and return the findings."""
    d_doc = drift.Document({"paths": {}, "components": {"schemas": declared_schemas}})
    s_doc = drift.Document({"paths": {}, "components": {"schemas": served_schemas}})
    findings = drift.Findings()
    drift.compare(
        d_doc,
        s_doc,
        {"$ref": f"#/components/schemas/{root}"},
        {"$ref": f"#/components/schemas/{root}"},
        "root",
        findings,
        "GET /test",
        set(),
    )
    return {(kind, where) for kind, where, _ in findings.rows}


OBJECT = {"type": "object", "properties": {}, "required": []}


def obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required)}


class TestPathShape:
    def test_parameter_names_do_not_make_two_routes(self):
        # The spec writes tripId, the router emits trip_id. Same route.
        assert drift.path_shape("/trips/{tripId}") == drift.path_shape("/trips/{trip_id}")

    def test_distinct_routes_stay_distinct(self):
        assert drift.path_shape("/trips/{id}/plan") != drift.path_shape("/trips/{id}")

    def test_literal_segments_survive(self):
        assert drift.path_shape("/trips/{id}/plan/accept-all") == "/trips/{}/plan/accept-all"


class TestPropertyDrift:
    def test_declared_field_the_server_never_sends(self):
        # The bug this check exists for: PlanItem.reservation shipped in the
        # spec, generated a typed field, and no route ever populated it.
        findings = compare(
            {"Root": obj({"id": {"type": "string"}, "reservation": {"type": "string"}})},
            {"Root": obj({"id": {"type": "string"}})},
        )
        assert ("MISSING", "Root.reservation") in findings

    def test_served_field_absent_from_the_spec(self):
        findings = compare(
            {"Root": obj({"id": {"type": "string"}})},
            {"Root": obj({"id": {"type": "string"}, "party_size": {"type": "integer"}})},
        )
        assert ("UNDECLARED", "Root.party_size") in findings

    def test_matching_shapes_report_nothing(self):
        schema = {"Root": obj({"id": {"type": "string"}}, ["id"])}
        assert compare(schema, copy.deepcopy(schema)) == set()


class TestRequiredDrift:
    def test_required_in_spec_optional_in_server(self):
        findings = compare(
            {"Root": obj({"a": {"type": "string"}}, ["a"])},
            {"Root": obj({"a": {"type": "string"}})},
        )
        assert ("REQUIRED", "Root.a") in findings

    def test_required_in_server_optional_in_spec(self):
        findings = compare(
            {"Root": obj({"a": {"type": "string"}})},
            {"Root": obj({"a": {"type": "string"}}, ["a"])},
        )
        assert ("REQUIRED", "Root.a") in findings

    def test_a_field_only_one_side_declares_is_not_also_a_required_finding(self):
        # Otherwise every missing field reports twice and the report doubles.
        findings = compare(
            {"Root": obj({"a": {"type": "string"}}, ["a"])},
            {"Root": obj({})},
        )
        assert findings == {("MISSING", "Root.a")}


class TestEnums:
    def test_member_missing_from_the_server(self):
        findings = compare(
            {"Root": obj({"s": {"enum": ["a", "b"]}})},
            {"Root": obj({"s": {"enum": ["a"]}})},
        )
        assert ("ENUM", "Root.s") in findings

    def test_member_the_spec_does_not_declare(self):
        findings = compare(
            {"Root": obj({"s": {"enum": ["a"]}})},
            {"Root": obj({"s": {"enum": ["a", "b"]}})},
        )
        assert ("ENUM", "Root.s") in findings

    def test_member_order_is_not_drift(self):
        findings = compare(
            {"Root": obj({"s": {"enum": ["a", "b"]}})},
            {"Root": obj({"s": {"enum": ["b", "a"]}})},
        )
        assert findings == set()


class TestNullabilityIsNotDrift:
    """The two documents spell optional differently and always will.

    FastAPI writes `anyOf: [T, {type: null}]`; the hand-written spec uses the
    3.1 type array or just leaves the field out of `required`.
    """

    def test_anyof_null_wrapper_against_a_bare_type(self):
        findings = compare(
            {"Root": obj({"a": {"type": "string"}})},
            {"Root": obj({"a": {"anyOf": [{"type": "string"}, {"type": "null"}]}})},
        )
        assert findings == set()

    def test_type_array_against_a_bare_type(self):
        findings = compare(
            {"Root": obj({"a": {"type": ["integer", "null"]}})},
            {"Root": obj({"a": {"type": "integer"}})},
        )
        assert findings == set()

    def test_a_real_mismatch_is_still_found_through_the_wrapper(self):
        # The normalizer must unwrap without swallowing what it wraps.
        findings = compare(
            {"Root": obj({"a": {"type": "string"}})},
            {"Root": obj({"a": {"anyOf": [{"type": "integer"}, {"type": "null"}]}})},
        )
        assert ("TYPE", "Root.a") in findings

    def test_a_genuine_union_is_left_alone(self):
        findings = compare(
            {"Root": obj({"a": {"anyOf": [{"type": "string"}, {"type": "integer"}]}})},
            {"Root": obj({"a": {"anyOf": [{"type": "string"}, {"type": "integer"}]}})},
        )
        assert findings == set()


class TestNesting:
    def test_drift_inside_an_array_of_objects(self):
        # PlanItem.reservation sat under Plan.items[]; a top-level-only diff
        # would have walked straight past it.
        findings = compare(
            {
                "Root": obj({"items": {"type": "array", "items": {"$ref": "#/components/schemas/Item"}}}),
                "Item": obj({"id": {"type": "string"}, "ghost": {"type": "string"}}),
            },
            {
                "Root": obj({"items": {"type": "array", "items": {"$ref": "#/components/schemas/Item"}}}),
                "Item": obj({"id": {"type": "string"}}),
            },
        )
        assert ("MISSING", "Item.ghost") in findings

    def test_findings_are_named_for_the_declared_schema_not_the_route(self):
        # One wrong field reaches many operations; naming it by schema is what
        # collapses those into a single line.
        findings = compare(
            {
                "Root": obj({"a": {"$ref": "#/components/schemas/Inner"}}),
                "Inner": obj({"ghost": {"type": "string"}}),
            },
            {
                "Root": obj({"a": {"$ref": "#/components/schemas/Inner"}}),
                "Inner": obj({}),
            },
        )
        assert findings == {("MISSING", "Inner.ghost")}

    def test_a_recursive_schema_terminates(self):
        recursive = {
            "Root": obj({"child": {"$ref": "#/components/schemas/Root"}, "ghost": {"type": "string"}})
        }
        served = {"Root": obj({"child": {"$ref": "#/components/schemas/Root"}})}
        assert ("MISSING", "Root.ghost") in compare(recursive, served)


class TestBodies:
    def test_fastapis_empty_schema_is_not_a_body(self):
        # A bare `return Response(...)` documents itself as `{}`: "any body".
        doc = drift.Document({"paths": {}})
        operation = {
            "responses": {"202": {"content": {"application/json": {"schema": {}}}}}
        }
        assert doc.json_body(operation, "response") is None

    def test_the_first_success_response_with_content_wins(self):
        doc = drift.Document({"paths": {}})
        operation = {
            "responses": {
                "204": {"description": "no content"},
                "200": {"content": {"application/json": {"schema": {"type": "object"}}}},
            }
        }
        assert doc.json_body(operation, "response") == {"type": "object"}


class TestAgainstTheRealSpec:
    """End to end, with drift injected into a copy of the real contract."""

    @pytest.fixture
    def spec(self):
        return yaml.safe_load(drift.SPEC_PATH.read_text())

    def _run(self, tmp_path, monkeypatch, spec, capsys):
        path = tmp_path / "openapi.yaml"
        path.write_text(yaml.safe_dump(spec))
        monkeypatch.setattr(drift, "SPEC_PATH", path)
        code = drift.main()
        return code, capsys.readouterr().out

    def test_the_contract_as_written_has_no_unaccounted_drift(
        self, tmp_path, monkeypatch, spec, capsys
    ):
        code, out = self._run(tmp_path, monkeypatch, spec, capsys)
        assert code == 0, out

    def test_a_field_added_to_the_spec_is_caught(
        self, tmp_path, monkeypatch, spec, capsys
    ):
        spec["components"]["schemas"]["PlanItem"]["properties"]["ghost"] = {
            "type": "string"
        }
        code, out = self._run(tmp_path, monkeypatch, spec, capsys)
        assert code == 1
        assert "PlanItem.ghost" in out

    def test_an_enum_member_dropped_from_the_spec_is_caught(
        self, tmp_path, monkeypatch, spec, capsys
    ):
        spec["components"]["schemas"]["ItemStatus"]["enum"].remove("skipped")
        code, out = self._run(tmp_path, monkeypatch, spec, capsys)
        assert code == 1
        assert "ENUM" in out and "skipped" in out

    def test_an_undeclared_route_is_caught(
        self, tmp_path, monkeypatch, spec, capsys
    ):
        del spec["paths"]["/trips/{tripId}/timeline"]
        code, out = self._run(tmp_path, monkeypatch, spec, capsys)
        assert code == 1
        assert "UNDECLARED" in out and "/trips/{}/timeline" in out

    def test_a_newly_declared_route_needs_a_reason(
        self, tmp_path, monkeypatch, spec, capsys
    ):
        spec["paths"]["/nothing-serves-this"] = {"get": {"responses": {"200": {}}}}
        code, out = self._run(tmp_path, monkeypatch, spec, capsys)
        assert code == 1
        assert "/nothing-serves-this" in out

    def test_an_exemption_that_no_longer_applies_is_caught(
        self, tmp_path, monkeypatch, spec, capsys
    ):
        # Implementing an endpoint must force its entry out of UNIMPLEMENTED,
        # or the list quietly becomes a record of things that were once true.
        # /explore used to stand here and no longer can: it is served now, so
        # its exemption is gone. Any still-exempt path proves the same rule.
        del spec["paths"]["/notifications"]
        code, out = self._run(tmp_path, monkeypatch, spec, capsys)
        assert code == 1
        assert "Stale exemptions" in out and "/notifications" in out
