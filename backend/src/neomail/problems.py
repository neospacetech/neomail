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
from neomail_core import MailError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from neomail.service import ResourceNotFoundError, SmartSendBlockedError
from neomail.transport import TransportError

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "urn:neosuite:problem:"

# HTTP status for each core error code. Input that can never be valid is 422;
# a well-formed request that conflicts with existing mailboxes is 409.
STATUS_BY_CODE: dict[str, int] = {
    "address_empty": 422,
    "address_invalid": 422,
    "address_too_long": 422,
    "recipients_empty": 422,
    "recipients_too_many": 422,
    "subject_too_long": 422,
    "message_id_invalid": 422,
    "mailbox_name_empty": 422,
    "mailbox_name_invalid": 422,
    "mailbox_role_unknown": 422,
    "claim_kind_unknown": 422,
    "fact_kind_unknown": 422,
    "interval_invalid": 422,
    "claim_invalid": 422,
    "payload_invalid": 422,
    "mailbox_role_taken": 409,
    "mailbox_name_taken": 409,
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
    502: "bad_gateway",
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


def from_core_error(exc: MailError, request: Request) -> ProblemResponse:
    code = getattr(exc, "code", "request_invalid")
    return problem(STATUS_BY_CODE.get(code, 422), code, detail=str(exc), instance=request.url.path)


def from_not_found(exc: ResourceNotFoundError, request: Request) -> ProblemResponse:
    return problem(404, "not_found", detail=str(exc), instance=request.url.path)


def from_blocked(exc: SmartSendBlockedError, request: Request) -> ProblemResponse:
    return problem(409, exc.code, detail=str(exc), instance=request.url.path)


def from_transport(exc: TransportError, request: Request) -> ProblemResponse:
    return problem(502, "transport_failed", detail=str(exc), instance=request.url.path)


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
            except MailError as exc:
                return from_core_error(exc, request)
            except ResourceNotFoundError as exc:
                return from_not_found(exc, request)
            except SmartSendBlockedError as exc:
                return from_blocked(exc, request)
            except TransportError as exc:
                return from_transport(exc, request)
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

    async def on_core_error(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, MailError)
        return from_core_error(exc, request)

    async def on_not_found(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, ResourceNotFoundError)
        return from_not_found(exc, request)

    async def on_blocked(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, SmartSendBlockedError)
        return from_blocked(exc, request)

    async def on_transport(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, TransportError)
        return from_transport(exc, request)

    app.add_exception_handler(StarletteHTTPException, on_http_exception)
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(MailError, on_core_error)
    app.add_exception_handler(ResourceNotFoundError, on_not_found)
    app.add_exception_handler(SmartSendBlockedError, on_blocked)
    app.add_exception_handler(TransportError, on_transport)


_PROBLEM_SCHEMA = Problem.model_json_schema()
_DESCRIPTIONS = {
    404: "No such resource.",
    409: "The request conflicts with existing mailboxes or with Smart Send findings.",
    422: "The input was rejected.",
    502: "The mail server did not accept the message.",
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
