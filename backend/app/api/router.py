"""The versioned API surface described by docs/openapi.yaml.

New endpoints mount here under /api/v1; the prototype's legacy endpoints
(/api/recommend, /resolve_location, ...) stay at the app root and retire
slice by slice.
"""

from fastapi import APIRouter

from app.api import actions, auth, plan, profile, trips
from app.api.problems import ProblemOut

# Every error on this surface is an RFC 9457 problem document, but the handler
# that renders it is invisible to FastAPI. Declaring it here is what puts it in
# the generated contract, and so in the frontend's types. The body goes out as
# application/problem+json; FastAPI takes an additional response's media type
# from the route's response class, so the generated spec says application/json.
# docs/openapi.yaml carries the accurate media type.
api_router = APIRouter(
    prefix="/api/v1",
    responses={"default": {"model": ProblemOut, "description": "Problem details (RFC 9457)"}},
)
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(trips.router)
api_router.include_router(plan.router)
api_router.include_router(actions.router)
