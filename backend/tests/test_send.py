from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from neomail.calendar_facts import InMemoryCalendarFacts
from neomail.transport import InMemoryTransport
from tests.support import ME, OWNER, PROBLEM, deliver, mailboxes

THREE_PM = int(datetime(2026, 10, 9, 15, tzinfo=UTC).timestamp())


def send(client: TestClient, **fields: Any) -> Any:
    body = {
        "owner": OWNER,
        "sender": ME,
        "to": ["bob@example.net"],
        "subject": "Hello",
        "text": "Hi Bob",
        **fields,
    }
    return client.post("/api/v1/messages/send", json=body)


def test_send_submits_and_files_in_sent(client: TestClient, transport: InMemoryTransport) -> None:
    response = send(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["submission_id"] == "memory-1"
    assert body["findings"] == []
    message = body["message"]
    assert message["seen"] is True
    assert message["mailbox_ids"] == [mailboxes(client)["sent"]["id"]]
    assert message["message_id"].endswith("@acme.neomail")
    [submitted] = transport.sent
    assert submitted.message_id == message["message_id"]
    assert submitted.sender["email"] == "alice@example.org"
    assert [a["email"] for a in submitted.to] == ["bob@example.net"]


def test_reply_threads_with_the_original(client: TestClient, transport: InMemoryTransport) -> None:
    original = deliver(client, message_id="<orig@example.net>", references="<root@example.net>")
    reply = send(client, subject="Re: Budget", reply_to_id=original["id"]).json()["message"]
    assert reply["in_reply_to"] == ["orig@example.net"]
    assert reply["references"] == ["root@example.net", "orig@example.net"]
    assert reply["thread_id"] == original["thread_id"]
    assert transport.sent[0].in_reply_to == ["orig@example.net"]


def test_send_validation(client: TestClient, transport: InMemoryTransport) -> None:
    assert send(client, to=[]).json()["code"] == "recipients_empty"
    assert send(client, sender="me").json()["code"] == "address_invalid"
    assert send(client, reply_to_id="nope").json()["code"] == "not_found"
    assert transport.sent == []


def test_smart_send_flags_missing_attachment_and_recipient(client: TestClient) -> None:
    draft = {
        "to": ["Bob <bob@example.net>"],
        "text": "Looping in Priya. The deck is attached.\n> earlier: see attached",
    }
    response = client.post("/api/v1/smart-send/check", json={"owner": OWNER, "draft": draft})
    assert response.status_code == 200
    body = response.json()
    assert body["claims_checked"] == 2
    assert body["blocking"] is False
    assert [(f["claim"], f["rule"], f["severity"]) for f in body["findings"]] == [
        ("attachment", "missing_attachment", "warn"),
        ("recipient-1", "missing_recipient", "warn"),
    ]
    assert body["findings"][1]["span"] == [0, 16]
    fixed = {**draft, "attachments": ["deck.pdf"], "cc": ["Priya R <priya@example.org>"]}
    clean = client.post("/api/v1/smart-send/check", json={"owner": OWNER, "draft": fixed}).json()
    assert clean["findings"] == []


def test_smart_send_checks_claims_against_the_calendar(
    client: TestClient, calendar: InMemoryCalendarFacts
) -> None:
    calendar.add(
        OWNER,
        {
            "id": "neo://acme/o/01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "kind": "busy",
            "start": THREE_PM,
            "end": THREE_PM + 3600,
            "title": "Design review",
        },
    )
    claim = {
        "id": "c1",
        "kind": "meeting_time",
        "start": "2026-10-09T15:30:00Z",
        "end": "2026-10-09T16:30:00Z",
        "span": [10, 22],
    }
    body = {"owner": OWNER, "draft": {"to": ["bob@example.net"]}, "claims": [claim]}
    report = client.post("/api/v1/smart-send/check", json=body).json()
    assert report["blocking"] is True
    assert report["findings"] == [
        {
            "claim": "c1",
            "rule": "overlap",
            "severity": "conflict",
            "why": 'This overlaps ("Design review").',
            "evidence": ["neo://acme/o/01ARZ3NDEKTSV4RRFFQ69G5FAV"],
            "span": [10, 22],
        }
    ]
    other = client.post("/api/v1/smart-send/check", json={**body, "owner": "user:bob"}).json()
    assert other["findings"] == []


def test_send_stops_on_conflicts_unless_confirmed(
    client: TestClient, calendar: InMemoryCalendarFacts, transport: InMemoryTransport
) -> None:
    calendar.add(OWNER, {"id": "ev", "kind": "ooo", "start": THREE_PM, "end": THREE_PM + 86400})
    claim = {
        "id": "c1",
        "kind": "availability",
        "start": "2026-10-09T18:00:00Z",
        "end": "2026-10-09T19:00:00Z",
    }
    blocked = send(client, claims=[claim])
    assert blocked.status_code == 409
    assert blocked.headers["content-type"] == PROBLEM
    assert blocked.json()["code"] == "smart_send_blocked"
    assert "out of office" in blocked.json()["detail"]
    assert transport.sent == []
    sent = send(client, claims=[claim], send_anyway=True)
    assert sent.status_code == 200
    assert [f["rule"] for f in sent.json()["findings"]] == ["out_of_office"]
    assert len(transport.sent) == 1


def test_invalid_claims(client: TestClient) -> None:
    base = {"owner": OWNER, "draft": {"text": ""}}
    cases = [
        ([{"id": "c", "kind": "meeting_time"}], "claim_invalid"),
        (
            [
                {
                    "id": "c",
                    "kind": "presence",
                    "start": "2026-10-09T10:00:00Z",
                    "end": "2026-10-09T11:00:00Z",
                }
            ],
            "claim_invalid",
        ),
        (
            [
                {
                    "id": "c",
                    "kind": "meeting_time",
                    "start": "2026-10-09T11:00:00Z",
                    "end": "2026-10-09T10:00:00Z",
                }
            ],
            "interval_invalid",
        ),
        ([{"id": "c", "kind": "gossip"}], "request_invalid"),
        ([{"id": "c", "kind": "meeting_time", "start": "2026-10-09T10:00:00"}], "request_invalid"),
    ]
    for claims, code in cases:
        response = client.post("/api/v1/smart-send/check", json={**base, "claims": claims})
        assert response.status_code == 422, claims
        assert response.json()["code"] == code, claims
