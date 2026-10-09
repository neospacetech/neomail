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

from neomail.api import TransitionIn, apply_transition
from neomail.contracts import ACTION_INVOKE_PATH
from neomail.problems import ProblemRoute, problem, problem_responses
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


class TransitionActionInput(TransitionIn):
    slug: str = Field(max_length=64)


def _transition(payload: dict[str, Any]) -> dict[str, Any]:
    data = TransitionActionInput.model_validate(payload)
    return apply_transition(data.slug, data).model_dump()


# Action id -> handler taking validated JSON input and returning JSON output.
# A handler must not commit anything itself: the invoke endpoint decides,
# based on dry_run, whether to persist the result and emit events.
HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "neomail.item.transition": _transition,
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


def create_actions_router(settings: Settings | None = None) -> APIRouter:
    store = IdempotencyStore(ttl_seconds=(settings or get_settings()).idempotency_ttl_seconds)
    router = APIRouter(tags=["neosuite"], route_class=ProblemRoute)

    @router.post(
        ACTION_INVOKE_PATH,
        operation_id="invokeAction",
        response_model=InvokeResponse,
        responses=problem_responses(404, 409, 422),
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
            output = handler(body.input)
        except ValidationError as exc:
            errors = [{**err, "loc": ("body", "input", *err["loc"])} for err in exc.errors()]
            raise RequestValidationError(errors) from exc

        result = InvokeResponse(action_id=action_id, dry_run=body.dry_run, output=output)
        if idempotency_key is not None and not body.dry_run:
            store.put(action_id, idempotency_key, fingerprint, result)
        return result

    return router
