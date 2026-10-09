"""Mail operations shared by the HTTP API and the NeoFlow actions.

The service orchestrates storage, the Rust core, the transport and the
outbox. Address parsing, envelope validation, mailbox rules, threading and
Smart Send are all decided by ``neomail_core``; this module decides what to
load, what to save and which domain events to emit.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import neomail_core as core

from neomail import engine
from neomail.calendar_facts import CalendarFacts
from neomail.ids import new_ulid, object_ref
from neomail.outbox import Outbox, cloud_event
from neomail.repository import MailboxRecord, MailRepository, MessageRecord, ThreadRecord
from neomail.transport import MailTransport, OutgoingMessage

# Mailboxes every owner gets on first use, in display order.
DEFAULT_MAILBOXES = {
    "inbox": "Inbox",
    "drafts": "Drafts",
    "sent": "Sent",
    "archive": "Archive",
    "junk": "Junk",
    "trash": "Trash",
}
SNIPPET_CHARS = 160


class ResourceNotFoundError(LookupError):
    """A referenced mailbox, thread or message does not exist."""

    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"no {kind} {key!r}")
        self.kind = kind
        self.key = key


class SmartSendBlockedError(Exception):
    """Smart Send found a conflict and the sender did not confirm."""

    code = "smart_send_blocked"

    def __init__(self, findings: list[dict[str, Any]]) -> None:
        conflicts = [f for f in findings if f["severity"] == "conflict"]
        super().__init__(
            f"Smart Send found {len(conflicts)} conflict(s); review them or send anyway: "
            + " ".join(f["why"] for f in conflicts)
        )
        self.findings = findings


@dataclass(frozen=True)
class SendResult:
    record: MessageRecord
    submission_id: str | None
    findings: list[dict[str, Any]]


def snippet(text: str) -> str:
    collapsed = " ".join(line for line in text.split() if line)
    return collapsed[:SNIPPET_CHARS]


def epoch(moment: datetime) -> int:
    return int(moment.timestamp())


class MailService:
    def __init__(
        self,
        repository: MailRepository,
        outbox: Outbox,
        tenant: str,
        transport: MailTransport,
        calendar: CalendarFacts,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.outbox = outbox
        self.tenant = tenant
        self.transport = transport
        self.calendar = calendar
        self._clock = clock or (lambda: datetime.now(UTC))

    def ref(self, object_id: str) -> str:
        return object_ref(self.tenant, object_id)

    def _emit(
        self, event_type: str, subject: str, changed: list[str], version: int, **scalars: Any
    ) -> None:
        self.outbox.append(
            cloud_event(self.tenant, event_type, subject, changed, version, **scalars)
        )

    # -- mailboxes ---------------------------------------------------------------------------

    def list_mailboxes(self, owner: str | None = None) -> list[MailboxRecord]:
        """Mailboxes in display order: by role (inbox first, custom last), then name."""
        boxes = self.repository.list_mailboxes(owner)
        return sorted(boxes, key=lambda b: (b.owner, core.role_rank(b.role), b.name.lower()))

    def get_mailbox(self, mailbox_id: str, owner: str | None = None) -> MailboxRecord:
        record = self.repository.get_mailbox(mailbox_id)
        if record is None or (owner is not None and record.owner != owner):
            raise ResourceNotFoundError("mailbox", mailbox_id)
        return record

    def create_mailbox(self, owner: str, name: str, role: str) -> MailboxRecord:
        existing = [(b.name, b.role) for b in self.repository.list_mailboxes(owner)]
        normalized = core.validate_new_mailbox(name, role, existing)
        now = self._clock()
        record = MailboxRecord(
            id=new_ulid(),
            owner=owner,
            name=normalized,
            role=role,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.save_mailbox(record)
        self._emit("neomail.mailbox.created", record.id, ["owner", "name", "role"], 1, role=role)
        return record

    def rename_mailbox(self, mailbox_id: str, name: str) -> MailboxRecord:
        current = self.get_mailbox(mailbox_id)
        others = [
            (b.name, b.role)
            for b in self.repository.list_mailboxes(current.owner)
            if b.id != current.id
        ]
        normalized = core.validate_new_mailbox(name, current.role, others)
        if normalized == current.name:
            return current
        record = replace(
            current, name=normalized, version=current.version + 1, updated_at=self._clock()
        )
        self.repository.save_mailbox(record)
        self._emit("neomail.mailbox.updated", record.id, ["name"], record.version, role=record.role)
        return record

    def ensure_mailbox(self, owner: str, role: str) -> MailboxRecord:
        """The owner's mailbox with ``role``, creating the standard one if missing."""
        for box in self.repository.list_mailboxes(owner):
            if box.role == role:
                return box
        return self.create_mailbox(owner, DEFAULT_MAILBOXES[role], role)

    def ensure_defaults(self, owner: str) -> list[MailboxRecord]:
        for role in DEFAULT_MAILBOXES:
            self.ensure_mailbox(owner, role)
        return self.list_mailboxes(owner)

    def mailbox_counts(self) -> dict[str, tuple[int, int]]:
        """``mailbox id -> (total, unread)`` over all messages."""
        counts: dict[str, tuple[int, int]] = {}
        for message in self.repository.list_messages():
            for box in message.mailbox_ids:
                total, unread = counts.get(box, (0, 0))
                counts[box] = (total + 1, unread + (0 if message.seen else 1))
        return counts

    # -- messages ----------------------------------------------------------------------------

    def get_message(self, message_id: str) -> MessageRecord:
        record = self.repository.get_message(message_id)
        if record is None:
            raise ResourceNotFoundError("message", message_id)
        return record

    def _new_message_id(self) -> str:
        return f"{new_ulid().lower()}@{self.tenant}.neomail"

    def _record(
        self,
        owner: str,
        envelope: "core.Envelope",
        text: str,
        mailbox_ids: tuple[str, ...],
        message_id: str,
        in_reply_to: list[str],
        references: list[str],
        attachments: list[str],
        received_at: datetime,
        seen: bool,
    ) -> MessageRecord:
        return MessageRecord(
            id=new_ulid(),
            owner=owner,
            thread_id="",
            mailbox_ids=mailbox_ids,
            message_id=message_id,
            in_reply_to=tuple(in_reply_to),
            references=tuple(references),
            sender=dict(envelope["from"]),
            to=tuple(dict(a) for a in envelope["to"]),
            cc=tuple(dict(a) for a in envelope["cc"]),
            bcc=tuple(dict(a) for a in envelope["bcc"]),
            subject=envelope["subject"],
            text=text,
            attachments=tuple(attachments),
            received_at=received_at,
            seen=seen,
            flagged=False,
            version=1,
        )

    def deliver(self, owner: str, data: dict[str, Any]) -> MessageRecord:
        """Store an incoming message and thread it."""
        envelope = core.validate_envelope(
            data["sender"], data["to"], data["cc"], data["bcc"], data["subject"]
        )
        mailbox = (
            self.get_mailbox(data["mailbox_id"], owner)
            if data.get("mailbox_id")
            else self.ensure_mailbox(owner, "inbox")
        )
        message_id = (
            core.parse_message_id(data["message_id"])
            if data.get("message_id")
            else self._new_message_id()
        )
        record = self._record(
            owner,
            envelope,
            data["text"],
            (mailbox.id,),
            message_id,
            core.extract_message_ids(data.get("in_reply_to") or ""),
            core.extract_message_ids(data.get("references") or ""),
            data.get("attachments") or [],
            data.get("received_at") or self._clock(),
            seen=False,
        )
        self.repository.save_message(record)
        record = self._rethread(owner, record.id)
        self._emit(
            "neomail.message.received",
            record.id,
            ["mailbox_ids", "thread_id"],
            record.version,
            thread=self.ref(record.thread_id),
        )
        return record

    def send(self, owner: str, data: dict[str, Any], dry_run: bool = False) -> SendResult:
        """Validate, run Smart Send, submit through the transport and file in Sent.

        On a dry run nothing is submitted or stored; the result previews the
        message and its Smart Send findings.
        """
        envelope = core.validate_envelope(
            data["sender"], data["to"], data["cc"], data["bcc"], data["subject"]
        )
        in_reply_to: list[str] = []
        references: list[str] = []
        if data.get("reply_to_id"):
            parent = self.get_message(data["reply_to_id"])
            in_reply_to = [parent.message_id]
            references = [*parent.references, parent.message_id]
        attachments = data.get("attachments") or []
        report = self.smart_send(
            owner,
            {
                "to": data["to"],
                "cc": data["cc"],
                "bcc": data["bcc"],
                "text": data["text"],
                "attachments": attachments,
            },
            data.get("claims") or [],
        )
        blocking = any(f["severity"] == "conflict" for f in report["findings"])
        if blocking and not dry_run and not data.get("send_anyway"):
            raise SmartSendBlockedError(report["findings"])
        sent_box = self.ensure_mailbox(owner, "sent") if not dry_run else None
        record = self._record(
            owner,
            envelope,
            data["text"],
            (sent_box.id,) if sent_box else (),
            self._new_message_id(),
            in_reply_to,
            references,
            attachments,
            self._clock(),
            seen=True,
        )
        if dry_run:
            return SendResult(record, None, report["findings"])
        receipt = self.transport.submit(
            OutgoingMessage(
                message_id=record.message_id,
                sender=record.sender,
                to=list(record.to),
                cc=list(record.cc),
                bcc=list(record.bcc),
                subject=record.subject,
                text=record.text,
                in_reply_to=list(record.in_reply_to),
                references=list(record.references),
            )
        )
        self.repository.save_message(record)
        record = self._rethread(owner, record.id)
        self._emit(
            "neomail.message.sent",
            record.id,
            ["mailbox_ids", "thread_id"],
            record.version,
            thread=self.ref(record.thread_id),
            recipients=len(record.to) + len(record.cc) + len(record.bcc),
        )
        return SendResult(record, receipt.submission_id, report["findings"])

    def update_message(
        self,
        message_id: str,
        seen: bool | None = None,
        flagged: bool | None = None,
        mailbox_ids: list[str] | None = None,
        dry_run: bool = False,
    ) -> MessageRecord:
        current = self.get_message(message_id)
        record = current
        if seen is not None or flagged is not None:
            record = replace(
                record,
                seen=current.seen if seen is None else seen,
                flagged=current.flagged if flagged is None else flagged,
            )
        if mailbox_ids is not None:
            boxes = tuple(dict.fromkeys(mailbox_ids))
            if not boxes:
                raise ResourceNotFoundError("mailbox", "(none given)")
            for box in boxes:
                self.get_mailbox(box, current.owner)
            record = replace(record, mailbox_ids=boxes)
        marked = [k for k in ("seen", "flagged") if getattr(record, k) != getattr(current, k)]
        moved = record.mailbox_ids != current.mailbox_ids
        if not marked and not moved:
            return current
        record = replace(record, version=current.version + 1)
        if dry_run:
            return record
        self.repository.save_message(record)
        if moved:
            self._emit(
                "neomail.message.moved",
                record.id,
                ["mailbox_ids"],
                record.version,
                thread=self.ref(record.thread_id),
            )
        if marked:
            self._emit(
                "neomail.message.marked",
                record.id,
                marked,
                record.version,
                seen=record.seen,
                flagged=record.flagged,
            )
        return record

    # -- threads -----------------------------------------------------------------------------

    def _rethread(self, owner: str, message_id: str) -> MessageRecord:
        """Regroup ``owner``'s messages into threads, keeping thread ids stable.

        A group keeps the id its earliest already-threaded message had, so a
        thread's id only changes when two threads merge (the older id wins).
        """
        messages = {m.id: m for m in self.repository.list_messages(owner)}
        groups = engine.build_threads(
            [
                {
                    "key": m.id,
                    "message_id": m.message_id,
                    "in_reply_to": " ".join(f"<{i}>" for i in m.in_reply_to) or None,
                    "references": " ".join(f"<{i}>" for i in m.references) or None,
                    "subject": m.subject,
                    "date": epoch(m.received_at),
                }
                for m in messages.values()
            ]
        )
        threads: list[ThreadRecord] = []
        used: set[str] = set()
        for group in groups:
            members = [messages[key] for key in group["messages"]]
            previous = [m.thread_id for m in members if m.thread_id and m.thread_id not in used]
            thread_id = min(previous) if previous else new_ulid()
            used.add(thread_id)
            for member in members:
                if member.thread_id != thread_id:
                    self.repository.save_message(replace(member, thread_id=thread_id))
            threads.append(
                ThreadRecord(
                    id=thread_id,
                    owner=owner,
                    subject=group["subject"],
                    message_ids=tuple(group["messages"]),
                    last_at=max(m.received_at for m in members),
                )
            )
        self.repository.replace_threads(owner, threads)
        return self.get_message(message_id)

    def thread_summary(self, thread: ThreadRecord) -> dict[str, Any]:
        messages = [self.get_message(i) for i in thread.message_ids]
        senders: dict[str, str] = {}
        for m in messages:
            senders.setdefault(m.sender["canonical"], m.sender["name"] or m.sender["email"])
        last = messages[-1]
        return {
            "id": thread.id,
            "ref": self.ref(thread.id),
            "owner": thread.owner,
            "subject": thread.subject,
            "message_ids": list(thread.message_ids),
            "message_count": len(messages),
            "unread_count": sum(1 for m in messages if not m.seen),
            "flagged": any(m.flagged for m in messages),
            "participants": list(senders.values()),
            "mailbox_ids": sorted({b for m in messages for b in m.mailbox_ids}),
            "snippet": snippet(last.text),
            "last_at": thread.last_at,
        }

    def list_threads(
        self, owner: str | None = None, mailbox_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Thread summaries, newest activity first."""
        if mailbox_id is not None:
            self.get_mailbox(mailbox_id, owner)
        summaries = [self.thread_summary(t) for t in self.repository.list_threads(owner)]
        if mailbox_id is not None:
            summaries = [s for s in summaries if mailbox_id in s["mailbox_ids"]]
        summaries.sort(key=lambda s: (s["last_at"], s["id"]), reverse=True)
        return summaries

    def get_thread(self, thread_id: str) -> tuple[dict[str, Any], list[MessageRecord]]:
        thread = self.repository.get_thread(thread_id)
        if thread is None:
            raise ResourceNotFoundError("thread", thread_id)
        return self.thread_summary(thread), [self.get_message(i) for i in thread.message_ids]

    # -- Smart Send --------------------------------------------------------------------------

    def smart_send(
        self,
        owner: str,
        draft: dict[str, Any],
        claims: list[dict[str, Any]],
        include_local: bool = True,
    ) -> dict[str, Any]:
        """Check a draft's claims against the owner's calendar and the draft itself.

        Claims extracted upstream (NeoMind) arrive in ``claims`` with Unix-second
        times; attachment and recipient mentions are found here by the core.
        """
        checked = [*(engine.extract_local_claims(draft["text"]) if include_local else []), *claims]
        times = [(c["start"], c["end"]) for c in checked if "start" in c and "end" in c]
        facts: list[dict[str, Any]] = []
        if times:
            start = min(s for s, _ in times)
            end = max(e for _, e in times)
            if end > start:
                facts = self.calendar.facts(owner, start, end)
        recipients = [*draft["to"], *draft["cc"], *draft["bcc"]]
        findings = engine.check_smart_send(
            checked, facts, {"recipients": recipients, "attachments": draft["attachments"]}
        )
        return {"claims": checked, "findings": findings}
