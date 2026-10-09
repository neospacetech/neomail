"""RFC 9457 problem documents.

Every error the service returns is ``application/problem+json`` with a stable
``code``. Domain errors keep the code raised by the Rust core, so clients see
exactly the same codes whichever layer rejected the input.

Routers use :class:`ProblemRoute` so they produce problem documents on their own,
whether they run in the standalone app or are mounted into a host process.
"""

from collections.abc import Callable, Coroutine, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from neomail_core import ItemError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "urn:neosuite:problem:"

# HTTP status for each core error code. Input that can never be valid is 422;
# a well-formed request that conflicts with the item's current state is 409.
STATUS_BY_CODE: dict[str, int] = {
    "title_empty": 422,
    "title_too_long": 422,
    "status_unknown": 422,
    "slug_invalid": 422,
    "transition_invalid": 409,
    "status_terminal": 409,
}

CODE_BY_HTTP_STATUS: dict[int, str] = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "request_invalid",
    429: "rate_limited",
    500: "internal_error",
    503: "unavailable",
}


class Problem(BaseModel):
    """RFC 9457 problem details with a NeoSuite ``code`` extension member."""

    type: str = Field(description="URI identifying the problem type.")
    title: str = Field(description="Short, human-readable summary of the problem type.")
    status: int = Field(description="HTTP status code.")
    code: str = Field(description="Stable machine-readable error code.")
    detail: str | None = Field(default=None, description="Explanation of this occurrence.")
    instance: str | None = Field(default=None, description="URI of this occurrence.")
    errors: list[dict[str, Any]] | None = Field(
        default=None, description="Field-level validation errors, when relevant."
    )


class ProblemResponse(JSONResponse):
    media_type = PROBLEM_MEDIA_TYPE


def problem(
    status: int,
    code: str,
    *,
    detail: str | None = None,
    instance: str | None = None,
    errors: Sequence[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> ProblemResponse:
    """Build a problem response."""
    body = Problem(
        type=f"{PROBLEM_TYPE_PREFIX}{code}",
        title=HTTPStatus(status).phrase,
        status=status,
        code=code,
        detail=detail,
        instance=instance,
        errors=list(errors) if errors is not None else None,
    )
    return ProblemResponse(body.model_dump(exclude_none=True), status_code=status, headers=headers)


def from_item_error(exc: ItemError, request: Request) -> ProblemResponse:
    code = getattr(exc, "code", "request_invalid")
    return problem(STATUS_BY_CODE.get(code, 422), code, detail=str(exc), instance=request.url.path)


def from_validation_error(exc: RequestValidationError, request: Request) -> ProblemResponse:
    errors = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return problem(
        422,
        "request_invalid",
        detail="The request does not match the expected schema.",
        instance=request.url.path,
        errors=errors,
    )


def from_http_exception(exc: StarletteHTTPException, request: Request) -> ProblemResponse:
    code = CODE_BY_HTTP_STATUS.get(exc.status_code, f"http_{exc.status_code}")
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem(
        exc.status_code,
        code,
        detail=detail,
        instance=request.url.path,
        headers=dict(exc.headers) if exc.headers else None,
    )


class ProblemRoute(APIRoute):
    """Route class that turns errors raised by an endpoint into problem documents."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def problem_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except ItemError as exc:
                return from_item_error(exc, request)
            except RequestValidationError as exc:
                return from_validation_error(exc, request)
            except StarletteHTTPException as exc:
                return from_http_exception(exc, request)

        return problem_handler


def install_problem_handlers(app: FastAPI) -> None:
    """Serve app-level errors (unknown paths, wrong methods, ...) as problem documents."""

    async def on_http_exception(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, StarletteHTTPException)
        return from_http_exception(exc, request)

    async def on_validation_error(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, RequestValidationError)
        return from_validation_error(exc, request)

    async def on_item_error(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, ItemError)
        return from_item_error(exc, request)

    app.add_exception_handler(StarletteHTTPException, on_http_exception)
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(ItemError, on_item_error)


_PROBLEM_SCHEMA = Problem.model_json_schema()
_DESCRIPTIONS = {
    404: "No such resource.",
    409: "The request conflicts with the item's current state.",
    422: "The input was rejected.",
}


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` entries for the problem statuses a route can return."""
    return {
        status: {
            "description": _DESCRIPTIONS.get(status, HTTPStatus(status).phrase),
            "content": {PROBLEM_MEDIA_TYPE: {"schema": _PROBLEM_SCHEMA}},
        }
        for status in statuses
    }
