from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.support import OWNER, PROBLEM, deliver, mailboxes


def threads(client: TestClient, **params: str) -> list[dict[str, Any]]:
    response = client.get("/api/v1/threads", params={"owner": OWNER, **params})
    assert response.status_code == 200
    listed: list[dict[str, Any]] = response.json()
    return listed


def test_deliver_parses_and_files_in_inbox(client: TestClient) -> None:
    message = deliver(
        client,
        sender='"Doe, Bob" <Bob@Example.NET>',
        to=["Alice <alice@example.org>, carol@example.org"],
        cc=["ALICE@example.org"],
        subject="  Budget \t Q3 ",
        message_id="<m1@example.net>",
        attachments=["q3.xlsx"],
    )
    assert message["from"] == {
        "name": "Doe, Bob",
        "email": "Bob@example.net",
        "canonical": "bob@example.net",
        "display": '"Doe, Bob" <Bob@example.net>',
    }
    assert [a["email"] for a in message["to"]] == ["alice@example.org", "carol@example.org"]
    assert message["cc"] == []  # Alice is already in To.
    assert message["subject"] == "Budget Q3"
    assert message["message_id"] == "m1@example.net"
    assert (message["seen"], message["flagged"]) == (False, False)
    assert message["mailbox_ids"] == [mailboxes(client)["inbox"]["id"]]
    assert client.get(f"/api/v1/messages/{message['id']}").json() == message


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"sender": "not an address"}, "address_invalid"),
        ({"sender": "  "}, "address_empty"),
        ({"to": [], "cc": [], "bcc": []}, "recipients_empty"),
        ({"to": ["ok@example.org, broken"]}, "address_invalid"),
        ({"subject": "x" * 999}, "subject_too_long"),
        ({"message_id": "no-brackets-or-at"}, "message_id_invalid"),
        ({"owner": "nobody"}, "request_invalid"),
    ],
)
def test_deliver_rejects_bad_messages(
    client: TestClient, fields: dict[str, Any], code: str
) -> None:
    body = {"owner": OWNER, "sender": "bob@example.net", "to": ["alice@example.org"], **fields}
    response = client.post("/api/v1/messages", json=body)
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == code


def test_threads_by_references_and_subject(client: TestClient) -> None:
    root = deliver(client, message_id="<1@x>", received_at="2026-10-09T09:00:00Z")
    reply = deliver(
        client,
        sender=["Carol <carol@example.org>"][0],
        subject="Re: Budget",
        message_id="<2@x>",
        references="<1@x>",
        received_at="2026-10-09T10:00:00Z",
    )
    loose = deliver(
        client, subject="RE: [fin] budget", message_id="<3@x>", received_at="2026-10-09T11:00:00Z"
    )
    other = deliver(
        client, subject="Lunch?", message_id="<4@x>", received_at="2026-10-09T08:00:00Z"
    )
    assert root["thread_id"] == client.get(f"/api/v1/messages/{reply['id']}").json()["thread_id"]
    assert client.get(f"/api/v1/messages/{loose['id']}").json()["thread_id"] == root["thread_id"]
    listed = threads(client)
    assert [(t["subject"], t["message_count"]) for t in listed] == [("Budget", 3), ("Lunch?", 1)]
    budget = listed[0]
    assert budget["id"] == root["thread_id"]
    assert budget["participants"] == ["Bob", "Carol"]
    assert budget["unread_count"] == 3
    assert budget["snippet"] == "Here are the numbers."
    assert budget["last_at"] == "2026-10-09T11:00:00Z"
    full = client.get(f"/api/v1/threads/{budget['id']}").json()
    assert [m["id"] for m in full["messages"]] == [root["id"], reply["id"], loose["id"]]
    assert full["messages"][0]["from"]["email"] == "bob@example.net"
    assert other["thread_id"] != root["thread_id"]
    assert client.get("/api/v1/threads/nope").json()["code"] == "not_found"


def test_threads_join_when_a_missing_parent_arrives_later(client: TestClient) -> None:
    a = deliver(client, message_id="<b@x>", references="<a@x>", subject="Re: Plan")
    b = deliver(client, message_id="<c@x>", references="<a@x>", subject="Re: Plan")
    assert a["thread_id"] == b["thread_id"]
    assert len(threads(client)) == 1


def test_mark_and_move(client: TestClient) -> None:
    client.post("/api/v1/mailboxes/defaults", json={"owner": OWNER})
    message = deliver(client)
    url = f"/api/v1/messages/{message['id']}"
    marked = client.patch(url, json={"seen": True, "flagged": True}).json()
    assert (marked["seen"], marked["flagged"], marked["version"]) == (True, True, 2)
    assert client.patch(url, json={"seen": True}).json()["version"] == 2
    archive = mailboxes(client)["archive"]["id"]
    moved = client.patch(url, json={"mailbox_ids": [archive]}).json()
    assert moved["mailbox_ids"] == [archive]
    assert threads(client, mailbox_id=archive)[0]["id"] == message["thread_id"]
    assert threads(client, mailbox_id=mailboxes(client)["inbox"]["id"]) == []
    foreign = client.post(
        "/api/v1/mailboxes", json={"owner": "user:bob", "name": "Inbox", "role": "inbox"}
    ).json()
    response = client.patch(url, json={"mailbox_ids": [foreign["id"]]})
    assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert client.patch(url, json={"mailbox_ids": []}).json()["code"] == "request_invalid"


def test_parse_addresses(client: TestClient) -> None:
    response = client.post(
        "/api/v1/addresses/parse", json={"value": '"Doe, Jane" <jane@example.org>; bob@x.io,,'}
    )
    assert [a["display"] for a in response.json()["addresses"]] == [
        '"Doe, Jane" <jane@example.org>',
        "bob@x.io",
    ]
    bad = client.post("/api/v1/addresses/parse", json={"value": "jane@"})
    assert bad.json()["code"] == "address_invalid"
