"""Domain events: CloudEvents 1.0 envelopes with thin payloads.

Every change is appended to an outbox. Delivery to NeoFlow (NATS JetStream
subject ``neo.evt.<tenant>.neomail.<type>.<verb>``) is at-least-once and
consumers dedupe on ``id``. :class:`InMemoryOutbox` keeps the envelopes in
memory and numbers them, which also feeds the ``/api/v1/changes`` stream; a
deployment uses an outbox stored with the data in NeoDB.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol

from neomail import COMPONENT
from neomail.ids import new_ulid, object_ref


@dataclass(frozen=True)
class Change:
    """One outbox entry: a position in the outbox plus the CloudEvent."""

    seq: int
    envelope: dict[str, Any]


class Outbox(Protocol):
    def append(self, envelope: dict[str, Any]) -> Change: ...
    def since(self, seq: int, limit: int = 100) -> list[Change]: ...


@dataclass
class InMemoryOutbox:
    _entries: list[Change] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def append(self, envelope: dict[str, Any]) -> Change:
        with self._lock:
            change = Change(seq=len(self._entries) + 1, envelope=envelope)
            self._entries.append(change)
            return change

    def since(self, seq: int, limit: int = 100) -> list[Change]:
        with self._lock:
            return self._entries[max(seq, 0) : max(seq, 0) + limit]


def cloud_event(
    tenant: str,
    event_type: str,
    subject: str,
    changed: list[str],
    version: int,
    **scalars: Any,
) -> dict[str, Any]:
    """Build a CloudEvents 1.0 envelope for ``event_type`` about object ``subject``.

    ``data`` carries only the object reference, the changed field names, the
    version and declared non-sensitive scalars, never titles or other content.
    """
    return {
        "specversion": "1.0",
        "id": new_ulid(),
        "type": event_type,
        "source": f"neo://{tenant}/{COMPONENT}",
        "subject": subject,
        "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "datacontenttype": "application/json",
        "data": {
            "ref": object_ref(tenant, subject),
            "changed": sorted(changed),
            "version": version,
            **scalars,
        },
    }
