"""The agent harness: tier 2 of three.

The tiering is the safety property, not an organising convenience. The model
(tier 1) reads one JSON value and writes one JSON value. This package (tier 2)
reads the database and read-only external services and writes rows in
*proposed* states. The executor (`app/services/actions/`, tier 3) is the only
thing that acts, and only on a gate the user has passed.

Each tier reaches the next only through data, which makes the boundary
mechanically checkable and it is checked: **nothing under `app/agent/` may
import `app/services/actions/`, and the executor may not import `app/agent/`.**
See `tests/unit/test_agent_layering.py`. Same shape as the frontend's
`no-restricted-paths` zones.
"""
