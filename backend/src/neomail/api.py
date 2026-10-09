"""Product API, mounted under ``/api/v1``.

Endpoints only translate between HTTP and the Rust core: every decision about
titles, slugs and statuses is made by ``neomail_core``. Core errors propagate
as :class:`neomail_core.ItemError` and :class:`~neomail.problems.ProblemRoute`
renders them as problem documents.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import neomail_core as core
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from neomail.problems import ProblemRoute, problem_responses
from neomail.settings import Settings, get_settings

API_PREFIX = "/api/v1"

# Upper bound on raw input size, so oversized payloads are rejected before they
# reach the core. The core enforces the real limit on the normalised title.
RAW_TITLE_MAX = 10_000


class ItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=RAW_TITLE_MAX, description="Raw title as typed by the user.")


def following_status(status: str) -> str | None:
    """The status after ``status``, or None when the core says it is final."""
    try:
        return core.next_status(status)
    except core.ItemError:
        return None


class ItemOut(BaseModel):
    title: str = Field(description="Normalised title.")
    slug: str = Field(description="URL-safe identifier derived from the title.")
    status: str = Field(description="Lifecycle status: todo, doing or done.")
    next_status: str | None = Field(
        description="Status the item can move to next; null when the status is final."
    )

    @classmethod
    def from_core(cls, item: core.Item) -> "ItemOut":
        return cls(
            title=item.title,
            slug=item.slug,
            status=item.status,
            next_status=following_status(item.status),
        )


class TransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(max_length=32, description="The item's current status.")
    target: str | None = Field(
        default=None, max_length=32, description="Requested status; omit to advance one step."
    )


class TransitionOut(BaseModel):
    slug: str
    previous_status: str
    status: str
    next_status: str | None = Field(
        description="Status the item can move to next; null when the status is final."
    )


def apply_transition(slug: str, body: TransitionIn) -> TransitionOut:
    """Validate and apply a status change. Shared by the API and the action."""
    core.validate_slug(slug)
    if body.target is None:
        new_status = core.next_status(body.status)
    else:
        new_status = core.transition(body.status, body.target)
    return TransitionOut(
        slug=slug,
        previous_status=body.status,
        status=new_status,
        next_status=following_status(new_status),
    )


def sse_event(event: str, data: dict[str, Any], event_id: int) -> str:
    """Encode one Server-Sent Event."""
    payload = json.dumps(data, separators=(",", ":"))
    return f"id: {event_id}\nevent: {event}\ndata: {payload}\n\n"


def create_api_router() -> APIRouter:
    router = APIRouter(
        prefix=API_PREFIX,
        tags=["items"],
        route_class=ProblemRoute,
    )

    @router.post("/items/validate", operation_id="validateItem", responses=problem_responses(422))
    async def validate_item(draft: ItemDraft) -> ItemOut:
        """Normalise a draft title and return the item it would create."""
        return ItemOut.from_core(core.Item(draft.title))

    @router.post(
        "/items/{slug}/transition",
        operation_id="transitionItem",
        responses=problem_responses(409, 422),
    )
    async def transition_item(slug: str, body: TransitionIn) -> TransitionOut:
        """Move an item to its next status, or to ``target`` if that step is allowed."""
        return apply_transition(slug, body)

    @router.get(
        "/items/lifecycle",
        operation_id="streamItemLifecycle",
        response_class=StreamingResponse,
        responses={
            **problem_responses(422),
            200: {
                "description": "Server-Sent Events: item.created, item.status (per step), end.",
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            },
        },
    )
    async def stream_lifecycle(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        title: Annotated[str, Query(max_length=RAW_TITLE_MAX)],
    ) -> StreamingResponse:
        """Stream an item moving through its whole lifecycle as Server-Sent Events.

        The title is validated before the stream opens, so a bad title is a normal
        problem response rather than an error event mid-stream.
        """
        item = core.Item(title)

        async def events() -> AsyncIterator[str]:
            event_id = 1
            yield sse_event("item.created", ItemOut.from_core(item).model_dump(), event_id)
            while True:
                await asyncio.sleep(settings.stream_interval_seconds)
                if await request.is_disconnected():
                    return
                previous = item.status
                try:
                    item.advance()
                except core.ItemError:
                    # The core decides when the lifecycle is over (status_terminal).
                    break
                event_id += 1
                step = TransitionOut(
                    slug=item.slug,
                    previous_status=previous,
                    status=item.status,
                    next_status=following_status(item.status),
                )
                yield sse_event("item.status", step.model_dump(), event_id)
            yield sse_event("end", {"slug": item.slug}, event_id + 1)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
