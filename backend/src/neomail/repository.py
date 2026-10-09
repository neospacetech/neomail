"""Storage behind a repository protocol.

The service only talks to :class:`MailRepository`. :class:`InMemoryRepository`
keeps everything in process memory, which suits tests and single-process
development. A deployment plugs in a NeoDB storage adapter implementing the same
protocol, so mailboxes, threads and messages live in NeoDB as ``neomail.Mailbox``,
``neomail.Thread`` and ``neomail.Message`` objects (raw MIME in NeoStore).
"""

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, Protocol


@dataclass(frozen=True)
class MailboxRecord:
    id: str
    owner: str
    name: str
    role: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageRecord:
    id: str
    owner: str
    thread_id: str
    mailbox_ids: tuple[str, ...]
    message_id: str
    in_reply_to: tuple[str, ...]
    references: tuple[str, ...]
    # Parsed addresses as returned by the core: {name, email, canonical, display}.
    sender: dict[str, Any]
    to: tuple[dict[str, Any], ...]
    cc: tuple[dict[str, Any], ...]
    bcc: tuple[dict[str, Any], ...]
    subject: str
    text: str
    attachments: tuple[str, ...]
    received_at: datetime
    seen: bool
    flagged: bool
    version: int


@dataclass(frozen=True)
class ThreadRecord:
    id: str
    owner: str
    subject: str
    message_ids: tuple[str, ...]
    last_at: datetime


class MailRepository(Protocol):
    """Persistence for mailboxes, messages and threads. Each call is atomic."""

    def save_mailbox(self, record: MailboxRecord) -> None: ...
    def get_mailbox(self, mailbox_id: str) -> MailboxRecord | None: ...
    def list_mailboxes(self, owner: str | None = None) -> list[MailboxRecord]: ...

    def save_message(self, record: MessageRecord) -> None: ...
    def get_message(self, message_id: str) -> MessageRecord | None: ...
    def list_messages(self, owner: str | None = None) -> list[MessageRecord]: ...

    def replace_threads(self, owner: str, threads: list[ThreadRecord]) -> None: ...
    def get_thread(self, thread_id: str) -> ThreadRecord | None: ...
    def list_threads(self, owner: str | None = None) -> list[ThreadRecord]: ...


@dataclass
class InMemoryRepository:
    """Process-local storage. Listings are ordered by id (creation order for ULIDs)."""

    _mailboxes: dict[str, MailboxRecord] = field(default_factory=dict)
    _messages: dict[str, MessageRecord] = field(default_factory=dict)
    _threads: dict[str, ThreadRecord] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def save_mailbox(self, record: MailboxRecord) -> None:
        with self._lock:
            self._mailboxes[record.id] = record

    def get_mailbox(self, mailbox_id: str) -> MailboxRecord | None:
        with self._lock:
            return self._mailboxes.get(mailbox_id)

    def list_mailboxes(self, owner: str | None = None) -> list[MailboxRecord]:
        with self._lock:
            records = sorted(self._mailboxes.values(), key=lambda r: r.id)
        return [r for r in records if owner is None or r.owner == owner]

    def save_message(self, record: MessageRecord) -> None:
        with self._lock:
            self._messages[record.id] = record

    def get_message(self, message_id: str) -> MessageRecord | None:
        with self._lock:
            return self._messages.get(message_id)

    def list_messages(self, owner: str | None = None) -> list[MessageRecord]:
        with self._lock:
            records = sorted(self._messages.values(), key=lambda r: r.id)
        return [r for r in records if owner is None or r.owner == owner]

    def replace_threads(self, owner: str, threads: list[ThreadRecord]) -> None:
        with self._lock:
            for key in [k for k, t in self._threads.items() if t.owner == owner]:
                del self._threads[key]
            for thread in threads:
                self._threads[thread.id] = thread

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        with self._lock:
            return self._threads.get(thread_id)

    def list_threads(self, owner: str | None = None) -> list[ThreadRecord]:
        with self._lock:
            records = list(self._threads.values())
        return [r for r in records if owner is None or r.owner == owner]
