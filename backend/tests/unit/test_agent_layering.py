"""The tier boundary, checked rather than trusted.

Tier 2 (`app/agent/`) proposes; tier 3 (`app/services/actions/`) is the only
thing that acts. Each reaches the next only through data, and the cheapest way
to keep it that way is to make the import itself impossible to land quietly.
Same shape as the frontend's `no-restricted-paths` zones.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
AGENT = APP / "agent"
EXECUTOR = APP / "services" / "actions"


def imported_modules(path: Path) -> set[str]:
    """Every module named by an import, including ones inside functions."""
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("path", sorted(AGENT.glob("*.py")), ids=lambda p: p.name)
def test_the_harness_never_imports_the_executor(path):
    offending = {m for m in imported_modules(path) if m.startswith("app.services.actions")}
    assert not offending, f"{path.name} imports {offending}"


@pytest.mark.parametrize("path", sorted(EXECUTOR.glob("*.py")), ids=lambda p: p.name)
def test_the_executor_never_imports_the_harness(path):
    offending = {
        m for m in imported_modules(path) if m == "app.agent" or m.startswith("app.agent.")
    }
    assert not offending, f"{path.name} imports {offending}"
