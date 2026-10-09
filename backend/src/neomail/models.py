"""Request and response models of the product API and the NeoFlow actions."""

from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from neomail.repository import MailboxRecord, MessageRecord

# Principals as defined by NeoAdmin: user:, group:, org:, svc: and agent: ids.
PRINCIPAL_PATTERN = r"^(user|group|org|svc|agent):[A-Za-z0-9._-]{1,64}$"
# Upper bounds on raw input sizes, so oversized payloads are rejected before
# they reach the core. The core enforces the real limits.
RAW_ADDRESS_MAX = 2_000
RAW_TEXT_MAX = 1_000_000

MailboxRole = Literal["inbox", "drafts", "sent", "archive", "junk", "trash", "custom"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Address(BaseModel):
    name: str | None = Field(description="Display name, unquoted.")
    email: str = Field(description="local@domain as written on the wire.")
    canonical: str = Field(description="Case-folded local@domain, for comparing people.")
    display: str = Field(description="RFC 5322 form: Name <local@domain>.")


# -- mailboxes ------------------------------------------------------------------------------


class MailboxIn(Strict):
    owner: str = Field(pattern=PRINCIPAL_PATTERN)
    name: str = Field(max_length=RAW_ADDRESS_MAX, description="Hierarchical, '/'-separated.")
    role: MailboxRole = "custom"


class MailboxPatch(Strict):
    name: str = Field(max_length=RAW_ADDRESS_MAX)


class DefaultsIn(Strict):
    owner: str = Field(pattern=PRINCIPAL_PATTERN)


class MailboxOut(BaseModel):
    id: str
    ref: str
    owner: str
    name: str
    role: MailboxRole
    total: int
    unread: int
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, record: MailboxRecord, ref: str, counts: tuple[int, int]) -> "MailboxOut":
        return cls(
            id=record.id,
            ref=ref,
            owner=record.owner,
            name=record.name,
            role=record.role,
            total=counts[0],
            unread=counts[1],
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


# -- messages -------------------------------------------------------------------------------


class Recipients(Strict):
    to: list[str] = Field(default_factory=list, max_length=500)
    cc: list[str] = Field(default_factory=list, max_length=500)
    bcc: list[str] = Field(default_factory=list, max_length=500)


class MessageIn(Recipients):
    """An incoming message to file (as delivered by the mail server)."""

    owner: str = Field(pattern=PRINCIPAL_PATTERN)
    sender: str = Field(max_length=RAW_ADDRESS_MAX, description="The From header.")
    subject: str = Field(default="", max_length=RAW_ADDRESS_MAX * 2)
    text: str = Field(default="", max_length=RAW_TEXT_MAX)
    mailbox_id: str | None = Field(default=None, description="Defaults to the owner's inbox.")
    message_id: str | None = Field(default=None, max_length=RAW_ADDRESS_MAX)
    in_reply_to: str | None = Field(default=None, max_length=RAW_ADDRESS_MAX * 10)
    references: str | None = Field(default=None, max_length=RAW_ADDRESS_MAX * 10)
    attachments: list[str] = Field(default_factory=list, max_length=100)
    received_at: AwareDatetime | None = None


class SendIn(Recipients):
    owner: str = Field(pattern=PRINCIPAL_PATTERN)
    sender: str = Field(max_length=RAW_ADDRESS_MAX, description="The From header.")
    subject: str = Field(default="", max_length=RAW_ADDRESS_MAX * 2)
    text: str = Field(default="", max_length=RAW_TEXT_MAX)
    attachments: list[str] = Field(default_factory=list, max_length=100)
    reply_to_id: str | None = Field(default=None, description="Stored message this replies to.")
    claims: list["SmartSendClaim"] = Field(
        default_factory=list, max_length=1000, description="Claims extracted upstream."
    )
    send_anyway: bool = Field(
        default=False, description="Send even when Smart Send finds a conflict."
    )


class MessagePatch(Strict):
    seen: bool | None = None
    flagged: bool | None = None
    mailbox_ids: list[str] | None = Field(default=None, min_length=1, max_length=50)


class MessageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    ref: str
    owner: str
    thread_id: str
    mailbox_ids: list[str]
    message_id: str = Field(description="Message-ID header, without angle brackets.")
    in_reply_to: list[str]
    references: list[str]
    sender: Address = Field(serialization_alias="from", validation_alias="from")
    to: list[Address]
    cc: list[Address]
    bcc: list[Address]
    subject: str
    text: str
    attachments: list[str]
    received_at: datetime
    seen: bool
    flagged: bool
    version: int

    @classmethod
    def of(cls, record: MessageRecord, ref: str) -> "MessageOut":
        return cls.model_validate(
            {
                "id": record.id,
                "ref": ref,
                "owner": record.owner,
                "thread_id": record.thread_id,
                "mailbox_ids": list(record.mailbox_ids),
                "message_id": record.message_id,
                "in_reply_to": list(record.in_reply_to),
                "references": list(record.references),
                "from": record.sender,
                "to": list(record.to),
                "cc": list(record.cc),
                "bcc": list(record.bcc),
                "subject": record.subject,
                "text": record.text,
                "attachments": list(record.attachments),
                "received_at": record.received_at,
                "seen": record.seen,
                "flagged": record.flagged,
                "version": record.version,
            }
        )


class ThreadSummary(BaseModel):
    id: str
    ref: str
    owner: str
    subject: str = Field(description="Base subject, without Re:/Fwd: prefixes.")
    message_ids: list[str]
    message_count: int
    unread_count: int
    flagged: bool
    participants: list[str] = Field(description="Senders, earliest first.")
    mailbox_ids: list[str]
    snippet: str
    last_at: datetime


class ThreadOut(ThreadSummary):
    messages: list[MessageOut]


class AddressParseIn(Strict):
    value: str = Field(max_length=RAW_ADDRESS_MAX * 10, description="A header-style list.")


class AddressList(BaseModel):
    addresses: list[Address]


class SendOut(BaseModel):
    message: MessageOut
    submission_id: str | None = Field(description="Transport's id for the submission.")
    findings: list["SmartSendFinding"]


# -- Smart Send -----------------------------------------------------------------------------


class SmartSendClaim(Strict):
    id: str = Field(max_length=64)
    kind: Literal["presence", "meeting_time", "availability", "attachment_ref", "recipient_ref"]
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    place: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, max_length=200)
    span: list[int] | None = Field(
        default=None, min_length=2, max_length=2, description="[start, end) character offsets."
    )

    def to_core(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "kind": self.kind}
        if self.start is not None:
            data["start"] = int(self.start.timestamp())
        if self.end is not None:
            data["end"] = int(self.end.timestamp())
        for key in ("place", "name", "span"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


class DraftIn(Recipients):
    text: str = Field(default="", max_length=RAW_TEXT_MAX)
    attachments: list[str] = Field(default_factory=list, max_length=100)


class SmartSendIn(Strict):
    owner: str = Field(pattern=PRINCIPAL_PATTERN, description="The sender, whose calendar is used.")
    draft: DraftIn
    claims: list[SmartSendClaim] = Field(default_factory=list, max_length=1000)
    include_local: bool = Field(
        default=True, description="Also find attachment and recipient mentions in the text."
    )


class SmartSendFinding(BaseModel):
    claim: str
    rule: Literal[
        "overlap",
        "out_of_office",
        "focus_time",
        "elsewhere_then",
        "missing_attachment",
        "missing_recipient",
    ]
    severity: Literal["info", "warn", "conflict"]
    why: str
    evidence: list[str] = Field(description="Calendar object refs backing the finding.")
    span: list[int] | None


class SmartSendOut(BaseModel):
    findings: list[SmartSendFinding]
    claims_checked: int
    blocking: bool = Field(description="True when a conflict should stop Send for confirmation.")


SendIn.model_rebuild()
SendOut.model_rebuild()
