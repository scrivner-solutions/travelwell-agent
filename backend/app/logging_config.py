"""Process-wide logging setup.

Cloud Run's log agent turns any JSON line on stdout into a real LogEntry, so
structured logging needs no client library: it lifts out `severity` and
`message` and files the rest under jsonPayload.
"""

from __future__ import annotations

import json
import logging
import os
import sys

# Built from a throwaway record so new stdlib attributes (3.12's taskName) never
# leak into the payload; whatever is left over came from the caller's `extra=`.
_RESERVED = frozenset(
    vars(
        logging.LogRecord(
            name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
        )
    )
) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, in the shape the Cloud Run log agent reads."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        payload.update({k: v for k, v in vars(record).items() if k not in _RESERVED})
        # default=str so a UUID or datetime in `extra=` can never kill a log call.
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install the one root handler. Call once, before anything logs."""
    handler = logging.StreamHandler(sys.stdout)
    # K_SERVICE is set only by Cloud Run, which is exactly where an agent is
    # parsing stdout. LOG_FORMAT overrides the guess in either direction.
    fmt = os.getenv("LOG_FORMAT") or ("json" if os.getenv("K_SERVICE") else "text")
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else logging.Formatter("%(levelname)-8s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
