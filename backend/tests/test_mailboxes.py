from fastapi.testclient import TestClient

from tests.support import OWNER, PROBLEM, deliver, mailboxes


def test_defaults_are_created_once_in_display_order(client: TestClient) -> None:
    first = client.post("/api/v1/mailboxes/defaults", json={"owner": OWNER}).json()
    assert [(m["name"], m["role"]) for m in first] == [
        ("INBOX", "inbox"),
        ("Drafts", "drafts"),
        ("Sent", "sent"),
        ("Archive", "archive"),
        ("Junk", "junk"),
        ("Trash", "trash"),
    ]
    again = client.post("/api/v1/mailboxes/defaults", json={"owner": OWNER}).json()
    assert [m["id"] for m in again] == [m["id"] for m in first]
    assert first[0]["ref"] == f"neo://acme/o/{first[0]['id']}"


def test_custom_mailboxes_sort_after_roles(client: TestClient) -> None:
    client.post("/api/v1/mailboxes/defaults", json={"owner": OWNER})
    response = client.post(
        "/api/v1/mailboxes", json={"owner": OWNER, "name": " Projects /  Acme  "}
    )
    assert response.status_code == 201
    created = response.json()
    assert (created["name"], created["role"], created["total"]) == ("Projects/Acme", "custom", 0)
    names = [m["name"] for m in client.get("/api/v1/mailboxes", params={"owner": OWNER}).json()]
    assert names[-1] == "Projects/Acme"


def test_names_and_roles_are_unique_per_owner(client: TestClient) -> None:
    client.post("/api/v1/mailboxes/defaults", json={"owner": OWNER})
    taken = client.post("/api/v1/mailboxes", json={"owner": OWNER, "name": "sent"})
    assert taken.status_code == 409
    assert taken.headers["content-type"] == PROBLEM
    assert taken.json()["code"] == "mailbox_name_taken"
    role = client.post("/api/v1/mailboxes", json={"owner": OWNER, "name": "Other", "role": "inbox"})
    assert (role.status_code, role.json()["code"]) == (409, "mailbox_role_taken")
    other_owner = client.post(
        "/api/v1/mailboxes", json={"owner": "user:bob", "name": "Inbox", "role": "inbox"}
    )
    assert other_owner.status_code == 201


def test_invalid_mailboxes(client: TestClient) -> None:
    cases = [
        ({"name": "  "}, "mailbox_name_empty"),
        ({"name": "a//b"}, "mailbox_name_invalid"),
        ({"name": "x", "role": "spam"}, "request_invalid"),
        ({"name": "x", "owner": "alice"}, "request_invalid"),
    ]
    for overrides, code in cases:
        response = client.post("/api/v1/mailboxes", json={"owner": OWNER, **overrides})
        assert response.status_code == 422, overrides
        assert response.json()["code"] == code


def test_rename_and_counts(client: TestClient) -> None:
    created = client.post("/api/v1/mailboxes", json={"owner": OWNER, "name": "Receipts"}).json()
    renamed = client.patch(f"/api/v1/mailboxes/{created['id']}", json={"name": "Bills"}).json()
    assert (renamed["name"], renamed["version"]) == ("Bills", 2)
    deliver(client, mailbox_id=created["id"])
    deliver(client)
    boxes = mailboxes(client)
    assert (boxes["Bills"]["total"], boxes["Bills"]["unread"]) == (1, 1)
    assert boxes["inbox"]["total"] == 1
    missing = client.patch("/api/v1/mailboxes/nope", json={"name": "x"})
    assert (missing.status_code, missing.json()["code"]) == (404, "not_found")
