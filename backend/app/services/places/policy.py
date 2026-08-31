"""When the places layer is allowed to spend money.

Lives here rather than in `app/agent` because the agent is not the only
plausible caller -- Explore is the obvious second one -- and a fetch budget that
lived with one consumer would have to be re-derived by the next.

The asymmetry below is the point of the module: a call site may push toward
*less* fetching and never toward more, so no caller can escalate spend by
passing an argument. Raising the ceiling is a deployment decision.
"""

from __future__ import annotations

import os
from datetime import timedelta

# 14 days matches `DEFAULT_TTL` for a single row. Hours and prices move slowly.
_DEFAULT_AREA_TTL_DAYS = 14
# Long enough that a sustained outage is not retried per planning run, short
# enough that a blip does not blind an area for a fortnight.
_DEFAULT_ERROR_BACKOFF_MINUTES = 30


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def fetch_enabled() -> bool:
    """The deployment-wide ceiling. Off means nothing bills, whatever callers ask."""
    return os.getenv("PLACES_FETCH_ENABLED", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def area_ttl() -> timedelta:
    return timedelta(days=_env_int("PLACES_AREA_TTL_DAYS", _DEFAULT_AREA_TTL_DAYS))


def error_backoff() -> timedelta:
    return timedelta(
        minutes=_env_int(
            "PLACES_ERROR_BACKOFF_MINUTES", _DEFAULT_ERROR_BACKOFF_MINUTES
        )
    )


def resolve_ttl(requested: timedelta | None) -> timedelta:
    """A caller may lengthen the freshness window, never shorten it.

    A shorter TTL means *more* fetching, so accepting one would be the escalation
    this module exists to prevent.
    """
    configured = area_ttl()
    return configured if requested is None else max(requested, configured)
