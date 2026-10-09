"""Outgoing mail transport.

:class:`MailTransport` is the adapter interface the service submits through.
:class:`JmapTransport` talks JMAP (RFC 8620/8621) to the mail server, Stalwart
in the standard deployment: one request creates the Email and an
EmailSubmission for it. :class:`InMemoryTransport` keeps submissions in
memory, for tests and development without a mail server.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Protocol

from neomail.settings import Settings

JMAP_USING = [
    "urn:ietf:params:jmap:core",
    "urn:ietf:params:jmap:mail",
    "urn:ietf:params:jmap:submission",
]


class TransportError(RuntimeError):
    """The mail server did not accept the message."""


@dataclass(frozen=True)
class OutgoingMessage:
    message_id: str
    sender: dict[str, Any]
    to: list[dict[str, Any]]
    cc: list[dict[str, Any]]
    bcc: list[dict[str, Any]]
    subject: str
    text: str
    in_reply_to: list[str]
    references: list[str]


@dataclass(frozen=True)
class SubmissionReceipt:
    submission_id: str


class MailTransport(Protocol):
    def submit(self, message: OutgoingMessage) -> SubmissionReceipt: ...


@dataclass
class InMemoryTransport:
    sent: list[OutgoingMessage] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def submit(self, message: OutgoingMessage) -> SubmissionReceipt:
        with self._lock:
            self.sent.append(message)
            return SubmissionReceipt(submission_id=f"memory-{len(self.sent)}")


def _jmap_address(address: dict[str, Any]) -> dict[str, Any]:
    return {"name": address.get("name"), "email": address["email"]}


def jmap_send_request(
    message: OutgoingMessage, account_id: str, identity_id: str, mailbox_id: str | None
) -> dict[str, Any]:
    """The JMAP request that creates ``message`` and submits it."""
    email: dict[str, Any] = {
        "mailboxIds": {mailbox_id: True} if mailbox_id else {},
        "keywords": {"$seen": True},
        "messageId": [message.message_id],
        "from": [_jmap_address(message.sender)],
        "to": [_jmap_address(a) for a in message.to],
        "cc": [_jmap_address(a) for a in message.cc],
        "bcc": [_jmap_address(a) for a in message.bcc],
        "subject": message.subject,
        "bodyValues": {"body": {"value": message.text}},
        "textBody": [{"partId": "body", "type": "text/plain"}],
    }
    if message.in_reply_to:
        email["inReplyTo"] = message.in_reply_to
    if message.references:
        email["references"] = message.references
    return {
        "using": JMAP_USING,
        "methodCalls": [
            ["Email/set", {"accountId": account_id, "create": {"draft": email}}, "c0"],
            [
                "EmailSubmission/set",
                {
                    "accountId": account_id,
                    "create": {"send": {"emailId": "#draft", "identityId": identity_id}},
                },
                "c1",
            ],
        ],
    }


def submission_id_from(response: dict[str, Any]) -> str:
    """The created EmailSubmission id, or :class:`TransportError` with the server's reason."""
    for name, args, _ in response.get("methodResponses", []):
        if name == "error":
            raise TransportError(f"JMAP error: {args.get('type', 'unknown')}")
        not_created = args.get("notCreated") or {}
        if not_created:
            reason = next(iter(not_created.values()))
            raise TransportError(f"{name} rejected the message: {reason.get('type', 'unknown')}")
        if name == "EmailSubmission/set":
            created = args.get("created") or {}
            if "send" in created:
                return str(created["send"]["id"])
    raise TransportError("the JMAP response has no EmailSubmission")


@dataclass(frozen=True)
class JmapTransport:
    api_url: str
    account_id: str
    identity_id: str
    token: str
    sent_mailbox_id: str | None = None
    timeout_seconds: float = 10.0

    def submit(self, message: OutgoingMessage) -> SubmissionReceipt:
        body = jmap_send_request(message, self.account_id, self.identity_id, self.sent_mailbox_id)
        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as reply:
                response = json.load(reply)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise TransportError(f"the mail server could not be reached: {exc}") from exc
        return SubmissionReceipt(submission_id=submission_id_from(response))


def create_transport(settings: Settings) -> MailTransport:
    """JMAP when the server is configured, otherwise in memory."""
    if settings.jmap_api_url and settings.jmap_account_id and settings.jmap_identity_id:
        token = settings.jmap_token.get_secret_value() if settings.jmap_token else ""
        return JmapTransport(
            api_url=settings.jmap_api_url,
            account_id=settings.jmap_account_id,
            identity_id=settings.jmap_identity_id,
            token=token,
            sent_mailbox_id=settings.jmap_sent_mailbox_id,
        )
    return InMemoryTransport()
