"""Helpers shared by the tests."""

from typing import Any

from fastapi.testclient import TestClient

OWNER = "user:alice"
ME = "Alice Example <alice@example.org>"
PROBLEM = "application/problem+json"


def deliver(client: TestClient, **fields: Any) -> dict[str, Any]:
    body = {
        "owner": OWNER,
        "sender": "Bob <bob@example.net>",
        "to": [ME],
        "subject": "Budget",
        "text": "Here are the numbers.",
        **fields,
    }
    response = client.post("/api/v1/messages", json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def mailboxes(client: TestClient) -> dict[str, dict[str, Any]]:
    """The owner's mailboxes keyed by role (custom ones by name)."""
    listed = client.get("/api/v1/mailboxes", params={"owner": OWNER}).json()
    return {m["role"] if m["role"] != "custom" else m["name"]: m for m in listed}
