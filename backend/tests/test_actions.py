from typing import Any

from fastapi.testclient import TestClient

from neomail.transport import InMemoryTransport
from tests.support import ME, OWNER, deliver, mailboxes

BASE = "/neosuite/actions/v1"


def invoke(
    client: TestClient, action: str, body: dict[str, Any], key: str | None = None
) -> tuple[int, dict[str, Any], dict[str, str]]:
    headers = {"Idempotency-Key": key} if key else {}
    response = client.post(f"{BASE}/{action}:invoke", json=body, headers=headers)
    return response.status_code, response.json(), dict(response.headers)


def send_input(**fields: Any) -> dict[str, Any]:
    return {"owner": OWNER, "sender": ME, "to": ["bob@example.net"], "subject": "Hi", **fields}


def test_send_action(client: TestClient, transport: InMemoryTransport) -> None:
    status, body, _ = invoke(client, "neomail.message.send", {"input": send_input()})
    assert status == 200
    output = body["output"]
    assert output["recipients"] == ["bob@example.net"]
    assert output["submission_id"] == "memory-1"
    assert output["message_id"]
    assert body["undo_token"] is None
    assert len(transport.sent) == 1


def test_send_dry_run_previews_findings(client: TestClient, transport: InMemoryTransport) -> None:
    status, body, _ = invoke(
        client,
        "neomail.message.send",
        {"input": send_input(text="Report attached."), "dry_run": True},
    )
    assert status == 200
    assert body["dry_run"] is True
    output = body["output"]
    assert (output["message_id"], output["submission_id"]) == (None, None)
    assert [f["rule"] for f in output["findings"]] == ["missing_attachment"]
    assert transport.sent == []
    assert client.get("/api/v1/mailboxes", params={"owner": OWNER}).json() == []


def test_move_and_mark_actions(client: TestClient) -> None:
    client.post("/api/v1/mailboxes/defaults", json={"owner": OWNER})
    message = deliver(client)
    archive = mailboxes(client)["archive"]["id"]
    status, body, _ = invoke(
        client,
        "neomail.message.move",
        {"input": {"message_id": message["id"], "mailbox_ids": [archive]}, "dry_run": True},
    )
    assert status == 200
    assert body["output"]["mailbox_ids"] == [archive]
    assert client.get(f"/api/v1/messages/{message['id']}").json()["mailbox_ids"] != [archive]
    invoke(
        client,
        "neomail.message.move",
        {"input": {"message_id": message["id"], "mailbox_ids": [archive]}},
    )
    assert client.get(f"/api/v1/messages/{message['id']}").json()["mailbox_ids"] == [archive]
    status, body, _ = invoke(
        client, "neomail.message.mark", {"input": {"message_id": message["id"], "seen": True}}
    )
    assert body["output"]["seen"] is True


def test_smart_send_check_action(client: TestClient) -> None:
    status, body, _ = invoke(
        client,
        "neomail.smartsend.check",
        {"input": {"owner": OWNER, "draft": {"text": "cc'ing Ravi"}}},
    )
    assert status == 200
    assert body["output"]["blocking"] is False
    assert [f["rule"] for f in body["output"]["findings"]] == ["missing_recipient"]


def test_errors(client: TestClient) -> None:
    status, body, _ = invoke(client, "neomail.message.send", {"input": {"owner": OWNER}})
    assert (status, body["code"]) == (422, "request_invalid")
    assert ["body", "input", "sender"] in [err["loc"] for err in body["errors"]]
    status, body, _ = invoke(client, "neomail.message.send", {"input": send_input(to=["x"])})
    assert (status, body["code"]) == (422, "address_invalid")
    status, body, _ = invoke(
        client, "neomail.message.mark", {"input": {"message_id": "nope", "seen": True}}
    )
    assert (status, body["code"]) == (404, "not_found")
    status, body, _ = invoke(client, "neomail.message.delete", {"input": {}})
    assert (status, body["code"]) == (404, "not_found")


def test_idempotency_key_replays(client: TestClient, transport: InMemoryTransport) -> None:
    body = {"input": send_input()}
    first = invoke(client, "neomail.message.send", body, key="k-1")
    second = invoke(client, "neomail.message.send", body, key="k-1")
    assert first[0] == second[0] == 200
    assert first[1] == second[1]
    assert second[2].get("idempotent-replayed") == "true"
    assert "idempotent-replayed" not in first[2]
    assert len(transport.sent) == 1


def test_idempotency_key_reuse_with_other_body_is_rejected(client: TestClient) -> None:
    invoke(client, "neomail.message.send", {"input": send_input()}, key="k-2")
    status, body, _ = invoke(
        client, "neomail.message.send", {"input": send_input(subject="Other")}, key="k-2"
    )
    assert status == 422
    assert body["code"] == "idempotency_key_reused"
