import json

from fastapi.testclient import TestClient


def parse_sse(text: str) -> list[dict[str, str]]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append(fields)
    return events


def test_lifecycle_stream(client: TestClient) -> None:
    with client.stream("GET", "/api/v1/items/lifecycle", params={"title": " Ship  it "}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-cache"
        text = resp.read().decode()

    events = parse_sse(text)
    assert [e["event"] for e in events] == ["item.created", "item.status", "item.status", "end"]
    assert [e["id"] for e in events] == ["1", "2", "3", "4"]

    created = json.loads(events[0]["data"])
    assert created == {
        "title": "Ship it",
        "slug": "ship-it",
        "status": "todo",
        "next_status": "doing",
    }
    steps = [json.loads(e["data"]) for e in events[1:3]]
    assert [(s["previous_status"], s["status"], s["next_status"]) for s in steps] == [
        ("todo", "doing", "done"),
        ("doing", "done", None),
    ]
    assert json.loads(events[3]["data"]) == {"slug": "ship-it"}


def test_lifecycle_stream_rejects_bad_title_before_streaming(client: TestClient) -> None:
    response = client.get("/api/v1/items/lifecycle", params={"title": "   "})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "title_empty"


def test_lifecycle_stream_requires_title(client: TestClient) -> None:
    response = client.get("/api/v1/items/lifecycle")
    assert response.status_code == 422
    assert response.json()["code"] == "request_invalid"
