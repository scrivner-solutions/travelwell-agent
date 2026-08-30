"""RFC 9457 problem details, per the error convention in docs/openapi.yaml.

Every /api/v1 error body is application/problem+json with a stable machine
`code` the frontend maps to honest failure states. Raise Problem anywhere in
the request path; the installed handler renders it.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

PROBLEM_MEDIA_TYPE = "application/problem+json"
# No per-problem type URIs yet; `code` is what the client actually branches on.
PROBLEM_TYPE = "about:blank"


class ProblemOut(BaseModel):
    """The error body, declared so it reaches the generated contract.

    Rendered by an exception handler rather than returned from a route, so
    FastAPI cannot infer it; app/api/router.py attaches it to every operation
    as the default response. problem_response() below builds from this model,
    which is what keeps the declaration and the wire body the same shape.
    """

    title: str
    status: int
    code: str = Field(description="Stable machine code the client maps to a failure state.")
    # No default: a default is what makes Pydantic declare a field optional, and
    # every error body carries this one. problem_response() passes it.
    type: str
    detail: str | None = None


class Problem(Exception):
    def __init__(
        self, status: int, title: str, code: str, detail: str | None = None
    ) -> None:
        super().__init__(title)
        self.status = status
        self.title = title
        self.code = code
        self.detail = detail


def problem_response(
    status: int, title: str, code: str, detail: str | None = None
) -> JSONResponse:
    body = ProblemOut(
        type=PROBLEM_TYPE, title=title, status=status, code=code, detail=detail
    ).model_dump(exclude_none=True)
    return JSONResponse(status_code=status, content=body, media_type=PROBLEM_MEDIA_TYPE)


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def handle_problem(request: Request, exc: Problem) -> JSONResponse:
        return problem_response(exc.status, exc.title, exc.code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}"
            for e in exc.errors()
        )
        return problem_response(422, "Request validation failed", "validation_error", detail)
