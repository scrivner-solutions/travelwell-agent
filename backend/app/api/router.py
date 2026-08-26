"""The versioned API surface described by docs/openapi.yaml.

New endpoints mount here under /api/v1; the prototype's legacy endpoints
(/api/recommend, /resolve_location, ...) stay at the app root and retire
slice by slice.
"""

from fastapi import APIRouter

from app.api import auth, trips

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(trips.router)
