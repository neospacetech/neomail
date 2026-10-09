"""Product API, mounted under ``/api/v1``.

Endpoints only translate between HTTP and :class:`~neomail.service.MailService`;
every mail rule lives in ``neomail_core``. Core errors propagate as
:class:`neomail_core.MailError` and :class:`~neomail.problems.ProblemRoute`
renders them, like missing resources, as problem documents.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import neomail_core as core
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from neomail.models import (
    PRINCIPAL_PATTERN,
    AddressList,
    AddressParseIn,
    DefaultsIn,
    MailboxIn,
    MailboxOut,
    MailboxPatch,
    MessageIn,
    MessageOut,
    MessagePatch,
    SendIn,
    SendOut,
    SmartSendIn,
    SmartSendOut,
    ThreadOut,
    ThreadSummary,
)
from neomail.problems import ProblemRoute, problem_responses
from neomail.repository import MailboxRecord, MessageRecord
from neomail.service import MailService
from neomail.settings import Settings, get_settings

API_PREFIX = "/api/v1"
# Changes sent per outbox read on the change stream.
CHANGE_BATCH = 100

OwnerQuery = Annotated[str | None, Query(pattern=PRINCIPAL_PATTERN)]


def sse_event(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    """Encode one Server-Sent Event."""
    payload = json.dumps(data, separators=(",", ":"))
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {payload}\n\n"


def smart_send_out(report: dict[str, Any]) -> SmartSendOut:
    findings = report["findings"]
    return SmartSendOut.model_validate(
        {
            "findings": findings,
            "claims_checked": len(report["claims"]),
            "blocking": any(f["severity"] == "conflict" for f in findings),
        }
    )


def create_api_router(service: MailService) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, route_class=ProblemRoute)

    def mailbox_out(record: MailboxRecord, counts: dict[str, tuple[int, int]]) -> MailboxOut:
        return MailboxOut.of(record, service.ref(record.id), counts.get(record.id, (0, 0)))

    def message_out(record: MessageRecord) -> MessageOut:
        return MessageOut.of(record, service.ref(record.id))

    # -- mailboxes ---------------------------------------------------------------------------

    @router.get(
        "/mailboxes",
        tags=["mailboxes"],
        operation_id="listMailboxes",
        responses=problem_responses(422),
    )
    async def list_mailboxes(owner: OwnerQuery = None) -> list[MailboxOut]:
        """Mailboxes with message counts, in display order (inbox first, custom last)."""
        counts = service.mailbox_counts()
        return [mailbox_out(m, counts) for m in service.list_mailboxes(owner)]

    @router.post(
        "/mailboxes",
        tags=["mailboxes"],
        operation_id="createMailbox",
        status_code=201,
        responses=problem_responses(409, 422),
    )
    async def create_mailbox(body: MailboxIn) -> MailboxOut:
        """Create a mailbox. Names are unique per owner, and so is every role except custom."""
        record = service.create_mailbox(body.owner, body.name, body.role)
        return mailbox_out(record, {})

    @router.post(
        "/mailboxes/defaults",
        tags=["mailboxes"],
        operation_id="createDefaultMailboxes",
        responses=problem_responses(409, 422),
    )
    async def create_default_mailboxes(body: DefaultsIn) -> list[MailboxOut]:
        """Make sure the owner has Inbox, Drafts, Sent, Archive, Junk and Trash."""
        records = service.ensure_defaults(body.owner)
        counts = service.mailbox_counts()
        return [mailbox_out(m, counts) for m in records]

    @router.patch(
        "/mailboxes/{mailbox_id}",
        tags=["mailboxes"],
        operation_id="renameMailbox",
        responses=problem_responses(404, 409, 422),
    )
    async def rename_mailbox(mailbox_id: str, body: MailboxPatch) -> MailboxOut:
        record = service.rename_mailbox(mailbox_id, body.name)
        return mailbox_out(record, service.mailbox_counts())

    # -- threads -----------------------------------------------------------------------------

    @router.get(
        "/threads",
        tags=["threads"],
        operation_id="listThreads",
        responses=problem_responses(404, 422),
    )
    async def list_threads(
        owner: OwnerQuery = None,
        mailbox_id: Annotated[str | None, Query(max_length=64)] = None,
    ) -> list[ThreadSummary]:
        """Conversations, newest activity first, optionally only those in one mailbox."""
        return [ThreadSummary.model_validate(t) for t in service.list_threads(owner, mailbox_id)]

    @router.get(
        "/threads/{thread_id}",
        tags=["threads"],
        operation_id="getThread",
        responses=problem_responses(404, 422),
    )
    async def get_thread(thread_id: str) -> ThreadOut:
        """A conversation with its messages, oldest first."""
        summary, messages = service.get_thread(thread_id)
        return ThreadOut.model_validate(
            {**summary, "messages": [message_out(m).model_dump(by_alias=True) for m in messages]}
        )

    # -- messages ----------------------------------------------------------------------------

    @router.post(
        "/messages",
        tags=["messages"],
        operation_id="deliverMessage",
        status_code=201,
        responses=problem_responses(404, 422),
    )
    async def deliver_message(body: MessageIn) -> MessageOut:
        """File an incoming message and thread it by References, In-Reply-To and subject."""
        return message_out(service.deliver(body.owner, body.model_dump()))

    @router.get(
        "/messages/{message_id}",
        tags=["messages"],
        operation_id="getMessage",
        responses=problem_responses(404, 422),
    )
    async def get_message(message_id: str) -> MessageOut:
        return message_out(service.get_message(message_id))

    @router.patch(
        "/messages/{message_id}",
        tags=["messages"],
        operation_id="updateMessage",
        responses=problem_responses(404, 422),
    )
    async def update_message(message_id: str, body: MessagePatch) -> MessageOut:
        """Mark as seen or flagged, or move to other mailboxes."""
        record = service.update_message(message_id, body.seen, body.flagged, body.mailbox_ids)
        return message_out(record)

    @router.post(
        "/messages/send",
        tags=["messages"],
        operation_id="sendMessage",
        responses=problem_responses(404, 409, 422, 502),
    )
    def send_message(body: SendIn) -> SendOut:
        """Send a message through the mail server and file it in Sent.

        Smart Send runs first. A conflict (for example, proposing a time the sender
        is busy) stops the send with `smart_send_blocked` unless `send_anyway` is set.
        """
        data = body.model_dump(exclude={"claims"})
        data["claims"] = [c.to_core() for c in body.claims]
        result = service.send(body.owner, data)
        return SendOut.model_validate(
            {
                "message": message_out(result.record).model_dump(by_alias=True),
                "submission_id": result.submission_id,
                "findings": result.findings,
            }
        )

    @router.post(
        "/addresses/parse",
        tags=["messages"],
        operation_id="parseAddresses",
        responses=problem_responses(422),
    )
    async def parse_addresses(body: AddressParseIn) -> AddressList:
        """Parse a header-style address list, as typed into To or Cc."""
        return AddressList.model_validate({"addresses": core.parse_address_list(body.value)})

    # -- Smart Send --------------------------------------------------------------------------

    @router.post(
        "/smart-send/check",
        tags=["smart-send"],
        operation_id="checkSmartSend",
        responses=problem_responses(422),
    )
    async def check_smart_send(body: SmartSendIn) -> SmartSendOut:
        """Check a draft before sending: its claims against the sender's calendar, and
        its mentions of attachments and people against what the draft contains.

        Read-only and deterministic. Claims extracted upstream (meeting times,
        availability, presence) come in `claims`; attachment and recipient mentions
        are found in the text unless `include_local` is false.
        """
        report = service.smart_send(
            body.owner,
            body.draft.model_dump(),
            [c.to_core() for c in body.claims],
            body.include_local,
        )
        return smart_send_out(report)

    # -- change stream -----------------------------------------------------------------------

    @router.get(
        "/changes",
        tags=["changes"],
        operation_id="streamChanges",
        response_class=StreamingResponse,
        responses={
            **problem_responses(422),
            200: {
                "description": "Server-Sent Events: one `change` per domain event, then `end`.",
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            },
        },
    )
    async def stream_changes(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
        after: Annotated[int, Query(ge=0, description="Last change sequence already seen.")] = 0,
        follow: Annotated[bool, Query(description="Keep the stream open for new changes.")] = True,
    ) -> StreamingResponse:
        """Domain events (CloudEvents 1.0, thin payloads) as Server-Sent Events.

        Each ``change`` event carries the envelope and its sequence number as the SSE
        id, so a client resumes with ``after=<last id>``. Without ``follow`` the
        stream ends with an ``end`` event once it has caught up.
        """

        async def events() -> AsyncIterator[str]:
            seq = after
            while True:
                batch = service.outbox.since(seq, CHANGE_BATCH)
                for change in batch:
                    seq = change.seq
                    yield sse_event("change", change.envelope, change.seq)
                if len(batch) == CHANGE_BATCH:
                    continue
                if not follow:
                    yield sse_event("end", {"seq": seq})
                    return
                await asyncio.sleep(max(settings.stream_interval_seconds, 0.01))
                if await request.is_disconnected():
                    return

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
