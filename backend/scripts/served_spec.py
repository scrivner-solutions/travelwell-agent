"""The OpenAPI document the server actually serves.

One owner, because two scripts ask the same question for opposite reasons:
check_openapi_drift.py compares this against the hand-written design spec, and
dump_openapi.py writes it out as the frontend's type source. If they derived it
differently the two answers could disagree, which is precisely the class of bug
this whole arrangement exists to prevent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_served() -> dict:
    """The versioned surface only.

    app/fast_api_app.py mounts `api_router` and nothing else under /api/v1, so
    the same router on a bare app is a faithful copy. Going through the real app
    would drag in ADK's ~200 schemas, none of which this contract describes.
    """
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault(
        "DATABASE_URL", "postgresql+psycopg://drift:drift@localhost:5432/drift"
    )

    from fastapi import FastAPI

    from app.api.router import api_router

    app = FastAPI()
    app.include_router(api_router)
    return app.openapi()
