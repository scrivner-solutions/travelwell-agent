#!/usr/bin/env python
"""Write the served contract to backend/openapi.json, the frontend's type source.

Per ADR 004, docs/openapi.yaml is the design artifact and this file is the type
source. They are different jobs: a design artifact should be free to run ahead
of the code, a type source must promise only what is real. The frontend
generates src/api/schema.d.ts from this file, so it can only reference fields
the server sends and only call routes the server serves.

The output is committed rather than built on the fly. Generation would otherwise
destroy the review signal that hand-editing used to provide: a contract change
has to show up as a diff someone reads in the pull request.

Two things are rewritten, and deliberately nothing else, because every rewrite
is a place the artifact could stop describing the server:

  info      FastAPI cannot know it from a bare router.
  servers   the /api/v1 prefix moves off every path and into servers[0].url,
            which is where OpenAPI puts a base path and where docs/openapi.yaml
            already puts this one. The request URL is unchanged (servers.url +
            path), the two documents stay structurally comparable, and the mount
            point stays in one place instead of in every call site.

Nothing under `components` is touched, and `paths` is only re-keyed. Both are
pinned by tests/unit/test_dump_openapi.py so this cannot quietly grow.

    uv run python scripts/dump_openapi.py

CI regenerates and fails on a diff, the same way it does for the TypeScript
client, so a stale checked-in contract cannot survive a pull request.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from served_spec import load_served

BACKEND_DIR = Path(__file__).resolve().parents[1]
OUT_PATH = BACKEND_DIR / "openapi.json"

# app/api/router.py mounts every route under this. It comes off the paths and
# goes into servers; see the module docstring.
API_PREFIX = "/api/v1"

INFO = {
    "title": "TravelWell API (served)",
    "version": "1.0.0",
    "description": (
        "Generated from the FastAPI routers by backend/scripts/dump_openapi.py. "
        "Do not edit: run the script. This describes what the server actually "
        "serves and is what the frontend's types are generated from. The "
        "hand-written docs/openapi.yaml is the design artifact and may declare "
        "endpoints ahead of the code; backend/scripts/check_openapi_drift.py "
        "holds the two together. See docs/adr/004."
    ),
}


def strip_prefix(paths: dict) -> dict:
    """Move API_PREFIX off every path key. A path that lacks it is a bug."""
    stripped = {}
    for path, item in paths.items():
        if not path.startswith(API_PREFIX + "/"):
            raise SystemExit(f"{path} is not under {API_PREFIX}; nothing else mounts here")
        stripped[path[len(API_PREFIX) :]] = item
    return stripped


def build() -> dict:
    spec = load_served()
    spec["info"] = INFO
    spec["servers"] = [{"url": API_PREFIX}]
    spec["paths"] = strip_prefix(spec["paths"])
    return spec


def main() -> int:
    # sort_keys so the diff reflects real contract changes, not FastAPI's
    # incidental ordering; this file is read almost exclusively as a diff.
    text = json.dumps(build(), indent=2, sort_keys=True) + "\n"
    OUT_PATH.write_text(text)
    print(f"wrote {OUT_PATH.relative_to(BACKEND_DIR.parent)} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
