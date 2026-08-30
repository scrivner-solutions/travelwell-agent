"""Tests for scripts/dump_openapi.py.

backend/openapi.json is the frontend's type source (ADR 004), so its value is
that it describes the server and nothing else. The script rewrites exactly two
things on the way out, and these tests exist to keep that number at two: a
transformation nobody is watching is how a generated artifact quietly goes back
to being a hand-written one.
"""

import importlib.util
import json
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load(name: str):
    """scripts/ is not a package."""
    path = BACKEND_DIR / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dump = _load("dump_openapi")


@pytest.fixture(scope="module")
def served():
    return dump.load_served()


@pytest.fixture(scope="module")
def built():
    return dump.build()


class TestOnlyTheDeclaredRewrites:
    def test_components_are_passed_through_untouched(self, served, built):
        assert built["components"] == served["components"]

    def test_every_operation_is_passed_through_untouched(self, served, built):
        prefix = dump.API_PREFIX
        assert {prefix + p: v for p, v in built["paths"].items()} == served["paths"]

    def test_nothing_else_at_the_top_level_changes(self, served, built):
        rewritten = {"info", "servers", "paths"}
        for key in set(served) | set(built):
            if key not in rewritten:
                assert built.get(key) == served.get(key), key

    def test_servers_carries_the_prefix_the_paths_lost(self, built):
        assert built["servers"] == [{"url": dump.API_PREFIX}]
        assert all(not p.startswith(dump.API_PREFIX) for p in built["paths"])


class TestStripPrefix:
    def test_moves_the_prefix_off_and_keeps_the_rest(self):
        out = dump.strip_prefix({"/api/v1/trips/{trip_id}": {"get": {}}})
        assert out == {"/trips/{trip_id}": {"get": {}}}

    def test_refuses_a_path_mounted_somewhere_else(self):
        # A route outside the prefix means the bare app picked up more than
        # api_router, and silently emitting it would misdescribe the surface.
        with pytest.raises(SystemExit):
            dump.strip_prefix({"/healthz": {"get": {}}})


class TestTheCommittedFileIsCurrent:
    def test_openapi_json_matches_what_the_script_would_write(self, built):
        """CI regenerates and diffs; this fails first, with a clearer message."""
        committed = json.loads(dump.OUT_PATH.read_text())
        assert committed == built, (
            "backend/openapi.json is stale; run: uv run python scripts/dump_openapi.py"
        )

    def test_the_error_contract_is_in_it(self, built):
        # Rendered by an exception handler, so it reaches the contract only
        # because app/api/router.py declares it. Easy to lose, hard to notice:
        # the frontend's Problem type is generated from this.
        assert "ProblemOut" in built["components"]["schemas"]
        assert all(
            "default" in op["responses"]
            for item in built["paths"].values()
            for op in item.values()
        )
