#!/usr/bin/env python
"""Contract drift check: what the server serves vs docs/openapi.yaml.

CI already verifies that the generated TypeScript client matches the spec. That
runs in the wrong direction: it proves the client agrees with a hand-written
file, not that the file describes the running API. `PlanItem.reservation` sat in
the spec for months, generated a typed field, and drove three UI surfaces the
server never populated. This closes that loop.

Companion to check_schema_drift.sh, one layer up: that script proves
docs/schema.sql matches the migrations, this one proves docs/openapi.yaml
matches the server.

How it compares
---------------
The two documents are not comparable by schema name. The spec names things for
the domain (`PlanItem`); FastAPI names them for the Pydantic class
(`PlanItemOut`). Paths disagree too: the spec writes `/trips/{tripId}`, the
router emits `/trips/{trip_id}`. So the walk starts at the operations, matches
them by path shape with parameter names normalized away, and descends through
both sides' `$ref`s in step, comparing by position. Findings are labelled with
the *declared* schema name, so one wrong field reports once instead of once per
operation that reaches it.

What it checks
--------------
  operations   a path+method on one side and not the other
  status       the success codes an operation declares
  properties   object fields present on one side only
  required     fields whose optionality disagrees
  enums        member sets (the spec promises these mirror the Postgres enums)
  types        the primitive type, where both sides state one

What it deliberately does not check, because the two documents are written by
different hands and differ harmlessly: descriptions, titles, examples, defaults,
formats, and nullability spelling (FastAPI writes `anyOf: [T, null]` where the
spec writes `type: [T, null]` or just omits the field from `required`). Error
responses are skipped as well: the spec declares one shared RFC 9457 `Problem`,
FastAPI emits `HTTPValidationError`, and diffing those is pure noise.

Divergence that is on purpose goes in ACCEPTED / UNIMPLEMENTED below, with a
reason. Both lists are printed on every run and an entry that no longer matches
anything fails the check, so a stale exemption cannot outlive the drift it
covered.

Local run from backend/:
    DATABASE_URL=postgresql+psycopg://u:p@localhost/db uv run python scripts/check_openapi_drift.py

Nothing connects; the URL only has to parse, because the app builds its engine
at import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# tests/unit/test_openapi_drift.py loads this file by path, so scripts/ is not
# on sys.path the way it is under `python scripts/...`. Put it there explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from served_spec import load_served

BACKEND_DIR = Path(__file__).resolve().parents[1]
SPEC_PATH = BACKEND_DIR.parent / "docs" / "openapi.yaml"

# The spec's single server; the router mounts the same surface under this prefix.
API_PREFIX = "/api/v1"
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")


# Declared in the spec, no route yet. Each entry names why, so landing the slice
# forces this list to shrink rather than letting the gap go quiet.
UNIMPLEMENTED: dict[tuple[str, str], str] = {
    ("/runs/{}", "get"): "Slice 2: agent runs",
    ("/runs/{}/events", "get"): "Slice 2: agent runs",
    ("/events", "post"): "Slice 5: calendar/event ingestion",
    ("/explore", "get"): "not started; no slice claims it yet",
    ("/notifications", "get"): "not started; no slice claims it yet",
    ("/notifications/{}/opened", "post"): "not started; no slice claims it yet",
    ("/config", "get"): (
        "served at the app root as /api/config, not under /api/v1; "
        "the spec places it in the versioned surface it has not moved to"
    ),
    ("/resolve_location", "get"): (
        "legacy prototype endpoint served at the app root; retires with the "
        "rest of the prototype surface rather than moving under /api/v1"
    ),
}

# Divergence inside a shared operation that is a decision, not a defect.
ACCEPTED: dict[tuple[str, str], str] = {
    ("MISSING", "ActionFailure.alternatives"): (
        "other places to try needs the places cache, which is Slice 6. Serving "
        "an empty list would claim we looked and found nothing"
    ),
    ("MISSING", "PlanItemOption.place"): (
        "forward declaration, and the spec says so: 'Populated once the places "
        "cache slice lands; display_* fields are authoritative until then.' "
        "No frontend surface reads it"
    ),
}


def load_declared() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text())


def path_shape(path: str) -> str:
    """`/trips/{tripId}` and `/trips/{trip_id}` are the same route."""
    out: list[str] = []
    depth = 0
    for ch in path:
        if ch == "{":
            depth += 1
            if depth == 1:
                out.append("{}")
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


class Document:
    """One side of the comparison, indexed by (path shape, method)."""

    def __init__(self, spec: dict, strip_prefix: str = "") -> None:
        self.spec = spec
        self.ops: dict[tuple[str, str], dict] = {}
        for raw_path, item in spec.get("paths", {}).items():
            path = raw_path
            if strip_prefix and path.startswith(strip_prefix):
                path = path[len(strip_prefix) :] or "/"
            for method, operation in item.items():
                if method.lower() in HTTP_METHODS:
                    self.ops[(path_shape(path), method.lower())] = operation

    def deref(self, node):
        """Follow $refs, reporting the last component schema name passed through."""
        name = None
        for _ in range(32):
            if not (isinstance(node, dict) and "$ref" in node):
                return node, name
            parts = node["$ref"].lstrip("#/").split("/")
            if parts[:2] == ["components", "schemas"]:
                name = parts[2]
            target = self.spec
            for part in parts:
                target = target[part]
            node = target
        raise RuntimeError(f"$ref cycle at {node}")

    def resolve(self, node):
        """Deref, then strip nullability so an optional field compares to its type."""
        node, name = self.deref(node)
        if not isinstance(node, dict):
            return node, name
        declared_type = node.get("type")
        if isinstance(declared_type, list):
            # OpenAPI 3.1 spelling: {"type": ["integer", "null"]}
            concrete = [t for t in declared_type if t != "null"]
            if len(concrete) == 1:
                node = {**node, "type": concrete[0]}
        for key in ("anyOf", "oneOf"):
            if key in node:
                # FastAPI's spelling: {"anyOf": [T, {"type": "null"}]}
                branches = [
                    b
                    for b in node[key]
                    if not (isinstance(b, dict) and b.get("type") == "null")
                ]
                if len(branches) == 1:
                    return self.resolve(branches[0])
        return node, name

    def success_codes(self, operation: dict) -> set[str]:
        return {
            str(code)
            for code in operation.get("responses", {})
            if str(code)[:1] in ("2", "3")
        }

    def json_body(self, operation: dict, which: str):
        """The JSON schema of a request body or the first success response."""
        if which == "request":
            body = operation.get("requestBody")
            if not body:
                return None
            content = self.deref(body)[0].get("content", {})
        else:
            content = {}
            responses = operation.get("responses", {})
            for code in sorted(responses, key=str):
                if str(code)[:1] not in ("2", "3"):
                    continue
                content = self.deref(responses[code])[0].get("content", {})
                if content:
                    break
        for content_type, media in content.items():
            if "json" in content_type:
                schema = media.get("schema")
                # FastAPI emits `{}` for a bare Response: "any body", not a shape.
                return schema or None
        return None


class Findings:
    """Findings keyed by what they are, not by where they were reached from."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], list[str]] = {}

    def add(self, kind: str, where: str, detail: str, operation: str) -> None:
        self.rows.setdefault((kind, where, detail), []).append(operation)


def compare(
    declared: Document,
    served: Document,
    d_node,
    s_node,
    where: str,
    findings: Findings,
    operation: str,
    seen: set[tuple[int, int]],
) -> None:
    d_node, d_name = declared.resolve(d_node)
    s_node, _ = served.resolve(s_node)
    if not isinstance(d_node, dict) or not isinstance(s_node, dict):
        return
    # Name the position after the spec's schema, which is what a reader knows it
    # by, and what makes one wrong field report once across every operation.
    where = d_name or where
    fingerprint = (id(d_node), id(s_node))
    if fingerprint in seen:
        return
    seen.add(fingerprint)

    d_enum, s_enum = d_node.get("enum"), s_node.get("enum")
    if d_enum and s_enum and set(d_enum) != set(s_enum):
        if missing := sorted(set(d_enum) - set(s_enum)):
            findings.add("ENUM", where, f"declared only: {missing}", operation)
        if extra := sorted(set(s_enum) - set(d_enum)):
            findings.add("ENUM", where, f"served only: {extra}", operation)

    d_type, s_type = d_node.get("type"), s_node.get("type")
    if d_type and s_type and d_type != s_type:
        findings.add("TYPE", where, f"declared {d_type}, served {s_type}", operation)

    if "items" in d_node and "items" in s_node:
        compare(
            declared,
            served,
            d_node["items"],
            s_node["items"],
            f"{where}[]",
            findings,
            operation,
            seen,
        )

    d_props, s_props = d_node.get("properties"), s_node.get("properties")
    if d_props is None or s_props is None:
        return
    for name in sorted(set(d_props) - set(s_props)):
        findings.add("MISSING", f"{where}.{name}", "declared, never served", operation)
    for name in sorted(set(s_props) - set(d_props)):
        findings.add("UNDECLARED", f"{where}.{name}", "served, not in the spec", operation)

    d_req = set(d_node.get("required", []))
    s_req = set(s_node.get("required", []))
    for name in sorted((d_req - s_req) & set(s_props)):
        findings.add(
            "REQUIRED", f"{where}.{name}", "required in spec, optional in server", operation
        )
    for name in sorted((s_req - d_req) & set(d_props)):
        findings.add(
            "REQUIRED", f"{where}.{name}", "required in server, optional in spec", operation
        )

    for name in sorted(set(d_props) & set(s_props)):
        compare(
            declared,
            served,
            d_props[name],
            s_props[name],
            f"{where}.{name}",
            findings,
            operation,
            seen,
        )


def main() -> int:
    declared = Document(load_declared())
    served = Document(load_served(), strip_prefix=API_PREFIX)

    shared = sorted(set(declared.ops) & set(served.ops))
    declared_only = sorted(set(declared.ops) - set(served.ops))
    served_only = sorted(set(served.ops) - set(declared.ops))

    print(
        f"Comparing {SPEC_PATH.name} against the router: "
        f"{len(shared)} shared operations, {len(declared_only)} declared-only, "
        f"{len(served_only)} served-only."
    )

    errors: list[str] = []
    unused_exemptions: list[str] = []

    for key in declared_only:
        if key not in UNIMPLEMENTED:
            errors.append(
                f"UNIMPLEMENTED  {key[1].upper()} {key[0]}\n"
                f"               declared in the spec, no route serves it. Implement "
                f"it, or add it to UNIMPLEMENTED with a reason."
            )
    for key in UNIMPLEMENTED:
        if key not in declared_only:
            unused_exemptions.append(
                f"UNIMPLEMENTED  {key[1].upper()} {key[0]} no longer applies "
                f"(it is served now, or the spec dropped it). Remove the entry."
            )

    for key in served_only:
        errors.append(
            f"UNDECLARED     {key[1].upper()} {key[0]}\n"
            f"               served under {API_PREFIX}, absent from the spec. Every "
            f"versioned route belongs in the contract."
        )

    findings = Findings()
    for key in shared:
        label = f"{key[1].upper()} {key[0]}"
        d_op, s_op = declared.ops[key], served.ops[key]

        d_codes, s_codes = declared.success_codes(d_op), served.success_codes(s_op)
        if d_codes != s_codes:
            findings.add(
                "STATUS",
                label,
                f"declared {sorted(d_codes)}, served {sorted(s_codes)}",
                label,
            )

        for which in ("request", "response"):
            d_body = declared.json_body(d_op, which)
            s_body = served.json_body(s_op, which)
            if d_body is None or s_body is None:
                if (d_body is None) != (s_body is None):
                    findings.add(
                        "BODY",
                        label,
                        f"{which} body declared={d_body is not None} "
                        f"served={s_body is not None}",
                        label,
                    )
                continue
            compare(declared, served, d_body, s_body, f"{label} {which}", findings, label, set())

    seen_accepted: set[tuple[str, str]] = set()
    for (kind, where, detail), operations in sorted(findings.rows.items()):
        if (kind, where) in ACCEPTED:
            seen_accepted.add((kind, where))
            continue
        reached = f"{len(operations)} operation(s), e.g. {operations[0]}"
        errors.append(
            f"{kind:<14} {where}\n"
            f"               {detail}\n"
            f"               reached by {reached}"
        )
    for key in ACCEPTED:
        if key not in seen_accepted:
            unused_exemptions.append(
                f"{key[0]:<14} {key[1]} no longer diverges. Remove the entry."
            )

    print(f"\nAccepted divergence ({len(UNIMPLEMENTED) + len(ACCEPTED)} entries):")
    for (path, method), reason in sorted(UNIMPLEMENTED.items()):
        print(f"  not served   {method.upper():6} {path}  -- {reason}")
    for (kind, where), reason in sorted(ACCEPTED.items()):
        print(f"  {kind.lower():<12} {where}  -- {reason}")

    if unused_exemptions:
        print("\nStale exemptions:")
        for line in unused_exemptions:
            print(f"  {line}")

    if errors or unused_exemptions:
        print(f"\nDRIFT: {len(errors) + len(unused_exemptions)} finding(s).\n")
        for line in errors:
            print(f"  {line}")
        print()
        return 1

    print("\nContract drift check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
