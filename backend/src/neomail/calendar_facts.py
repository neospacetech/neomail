"""Calendar facts for Smart Send.

Smart Send needs to know what the sender's calendar says about the times a
draft mentions. :class:`CalendarFacts` is the adapter interface; a deployment
backs it with NeoCalendar (its occurrences and consistency API, evaluated with
the sender's permissions). :class:`InMemoryCalendarFacts` serves facts
registered in process, for tests and development.
"""

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Protocol


class CalendarFacts(Protocol):
    def facts(self, owner: str, start: int, end: int) -> list[dict[str, Any]]:
        """Facts overlapping ``[start, end)`` (Unix seconds) that ``owner`` may see.

        Each fact is ``{id, kind, start, end, title?, place?, visible}`` with
        ``kind`` one of busy, travel, ooo or focus.
        """
        ...


@dataclass
class InMemoryCalendarFacts:
    _facts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def add(self, owner: str, fact: dict[str, Any]) -> None:
        with self._lock:
            self._facts.setdefault(owner, []).append(dict(fact))

    def facts(self, owner: str, start: int, end: int) -> list[dict[str, Any]]:
        with self._lock:
            known = list(self._facts.get(owner, []))
        return [f for f in known if f["start"] < end and start < f["end"]]
