"""NeoFlow action invocation: ``POST /neosuite/actions/v1/{action_id}:invoke``.

Implements the suite action contract for this product's actions:

* body ``{"input": {...}, "dry_run": false}``;
* ``Idempotency-Key`` replays return the stored result for at least 24 hours,
  and reusing a key with a different body is rejected;
* ``dry_run`` validates and computes the result without committing anything.
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from neomail.contracts import ACTION_INVOKE_PATH
from neomail.models import SendIn, SmartSendIn, Strict
from neomail.problems import ProblemRoute, problem, problem_responses
from neomail.service import MailService
from neomail.settings import Settings, get_settings


class InvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: dict[str, Any] = Field(description="Action input; see the action's input_schema.")
    dry_run: bool = Field(default=False, description="Validate and preview without effects.")


class InvokeResponse(BaseModel):
    action_id: str
    dry_run: bool
    output: dict[str, Any]
    undo_token: str | None = None


class MoveInput(Strict):
    message_id: str = Field(max_length=64)
    mailbox_ids: list[str] = Field(min_length=1, max_length=50)


class MarkInput(Strict):
    message_id: str = Field(max_length=64)
    seen: bool | None = None
    flagged: bool | None = None


ActionResult = tuple[dict[str, Any], str | None]


def _send(service: MailService, payload: dict[str, Any], dry_run: bool) -> ActionResult:
    data = SendIn.model_validate(payload)
    fields = data.model_dump(exclude={"claims"})
    fields["claims"] = [c.to_core() for c in data.claims]
    result = service.send(data.owner, fields, dry_run=dry_run)
    record = result.record
    output = {
        "message_id": None if dry_run else record.id,
        "thread_id": record.thread_id or None,
        "subject": record.subject,
        "recipients": [a["email"] for a in (*record.to, *record.cc, *record.bcc)],
        "submission_id": result.submission_id,
        "findings": result.findings,
    }
    return output, None


def _message_state(service: MailService, message_id: str, record: Any) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "mailbox_ids": list(record.mailbox_ids),
        "seen": record.seen,
        "flagged": record.flagged,
        "version": record.version,
    }


def _move(service: MailService, payload: dict[str, Any], dry_run: bool) -> ActionResult:
    data = MoveInput.model_validate(payload)
    record = service.update_message(data.message_id, mailbox_ids=data.mailbox_ids, dry_run=dry_run)
    return _message_state(service, data.message_id, record), None


def _mark(service: MailService, payload: dict[str, Any], dry_run: bool) -> ActionResult:
    data = MarkInput.model_validate(payload)
    record = service.update_message(
        data.message_id, seen=data.seen, flagged=data.flagged, dry_run=dry_run
    )
    return _message_state(service, data.message_id, record), None


def _check(service: MailService, payload: dict[str, Any], dry_run: bool) -> ActionResult:
    data = SmartSendIn.model_validate(payload)
    report = service.smart_send(
        data.owner, data.draft.model_dump(), [c.to_core() for c in data.claims], data.include_local
    )
    findings = report["findings"]
    blocking = any(f["severity"] == "conflict" for f in findings)
    return {
        "findings": findings,
        "claims_checked": len(report["claims"]),
        "blocking": blocking,
    }, None


# Action id -> handler taking the service, validated JSON input and the dry_run
# flag, and returning the JSON output plus an undo token. On a dry run a handler
# validates and computes everything but sends, stores and emits nothing.
HANDLERS: dict[str, Callable[[MailService, dict[str, Any], bool], ActionResult]] = {
    "neomail.message.send": _send,
    "neomail.message.move": _move,
    "neomail.message.mark": _mark,
    "neomail.smartsend.check": _check,
}


@dataclass
class IdempotencyStore:
    """Remembers results per (action, Idempotency-Key).

    This in-process store suits a single replica. A deployed product keeps these
    records in NeoDB so replays survive restarts and are shared across replicas.
    """

    ttl_seconds: int
    _entries: dict[tuple[str, str], tuple[float, str, InvokeResponse]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def get(self, action_id: str, key: str) -> tuple[str, InvokeResponse] | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get((action_id, key))
            if entry is None or entry[0] < now:
                self._entries.pop((action_id, key), None)
                return None
            return entry[1], entry[2]

    def put(self, action_id: str, key: str, fingerprint: str, response: InvokeResponse) -> None:
        with self._lock:
            expires = time.monotonic() + self.ttl_seconds
            self._entries[(action_id, key)] = (expires, fingerprint, response)


def _fingerprint(body: InvokeRequest) -> str:
    canonical = json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_actions_router(service: MailService, settings: Settings | None = None) -> APIRouter:
    store = IdempotencyStore(ttl_seconds=(settings or get_settings()).idempotency_ttl_seconds)
    router = APIRouter(tags=["neosuite"], route_class=ProblemRoute)

    @router.post(
        ACTION_INVOKE_PATH,
        operation_id="invokeAction",
        response_model=InvokeResponse,
        responses=problem_responses(404, 409, 422, 502),
    )
    async def invoke_action(
        action_id: str,
        body: InvokeRequest,
        request: Request,
        response: Response,
        idempotency_key: Annotated[str | None, Header(max_length=255)] = None,
    ) -> InvokeResponse | Response:
        """Invoke one of this product's NeoFlow actions."""
        handler = HANDLERS.get(action_id)
        if handler is None:
            raise HTTPException(404, f"unknown action {action_id!r}")

        fingerprint = _fingerprint(body)
        if idempotency_key is not None:
            stored = store.get(action_id, idempotency_key)
            if stored is not None:
                stored_fingerprint, stored_response = stored
                if stored_fingerprint != fingerprint:
                    return problem(
                        422,
                        "idempotency_key_reused",
                        detail="This Idempotency-Key was already used with a different body.",
                        instance=request.url.path,
                    )
                response.headers["Idempotent-Replayed"] = "true"
                return stored_response

        try:
            output, undo_token = handler(service, body.input, body.dry_run)
        except ValidationError as exc:
            errors = [{**err, "loc": ("body", "input", *err["loc"])} for err in exc.errors()]
            raise RequestValidationError(errors) from exc

        result = InvokeResponse(
            action_id=action_id, dry_run=body.dry_run, output=output, undo_token=undo_token
        )
        if idempotency_key is not None and not body.dry_run:
            store.put(action_id, idempotency_key, fingerprint, result)
        return result

    return router
