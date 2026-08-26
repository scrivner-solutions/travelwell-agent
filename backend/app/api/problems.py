"""RFC 9457 problem details, per the error convention in docs/openapi.yaml.

Every /api/v1 error body is application/problem+json with a stable machine
`code` the frontend maps to honest failure states. Raise Problem anywhere in
the request path; the installed handler renders it.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

PROBLEM_MEDIA_TYPE = "application/problem+json"


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
    body: dict = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
    }
    if detail is not None:
        body["detail"] = detail
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
