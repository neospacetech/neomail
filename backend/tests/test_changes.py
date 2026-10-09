import json
from typing import Any

from fastapi.testclient import TestClient

from tests.support import ME, OWNER, deliver


def read_stream(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    with client.stream("GET", "/api/v1/changes", params={"follow": "false", **params}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = resp.read().decode()
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        fields["data"] = json.loads(fields["data"])
        events.append(fields)
    return events


def test_changes_carry_thin_cloud_events(client: TestClient) -> None:
    message = deliver(client, subject="Secret plans", text="Do not leak this")
    client.patch(f"/api/v1/messages/{message['id']}", json={"seen": True})
    client.post(
        "/api/v1/messages/send",
        json={"owner": OWNER, "sender": ME, "to": ["bob@example.net"], "subject": "Hi"},
    )
    events = read_stream(client)
    types = [e["data"]["type"] for e in events if e["event"] == "change"]
    assert types == [
        "neomail.mailbox.created",
        "neomail.message.received",
        "neomail.message.marked",
        "neomail.mailbox.created",
        "neomail.message.sent",
    ]
    received = events[1]["data"]
    assert received["source"] == "neo://acme/neomail"
    assert received["subject"] == message["id"]
    assert received["data"] == {
        "ref": message["ref"],
        "changed": ["mailbox_ids", "thread_id"],
        "version": 1,
        "thread": f"neo://acme/o/{message['thread_id']}",
    }
    assert events[2]["data"]["data"]["changed"] == ["seen"]
    assert events[4]["data"]["data"]["recipients"] == 1
    serialized = json.dumps(events)
    assert "Secret plans" not in serialized
    assert "Do not leak" not in serialized
    assert events[-1] == {"event": "end", "data": {"seq": 5}}
    assert [e["id"] for e in read_stream(client, after=3)[:-1]] == ["4", "5"]
