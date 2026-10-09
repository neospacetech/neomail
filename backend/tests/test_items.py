from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

PROBLEM = "application/problem+json"


def test_validate_normalises_title(client: TestClient) -> None:
    response = client.post("/api/v1/items/validate", json={"title": "  Plan   the\tlaunch "})
    assert response.status_code == 200
    assert response.json() == {
        "title": "Plan the launch",
        "slug": "plan-the-launch",
        "status": "todo",
        "next_status": "doing",
    }


@pytest.mark.parametrize(
    ("title", "code"),
    [("", "title_empty"), ("   \n ", "title_empty"), ("x" * 201, "title_too_long")],
)
def test_validate_rejects_bad_titles(client: TestClient, title: str, code: str) -> None:
    response = client.post("/api/v1/items/validate", json={"title": title})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == code
    assert body["type"] == f"urn:neosuite:problem:{code}"
    assert body["status"] == 422
    assert body["title"] == HTTPStatus(422).phrase
    assert body["instance"] == "/api/v1/items/validate"
    assert body["detail"]


def test_validate_rejects_malformed_body(client: TestClient) -> None:
    response = client.post("/api/v1/items/validate", json={"name": "wrong field"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == "request_invalid"
    assert {tuple(err["loc"]) for err in body["errors"]} >= {("body", "title")}


@pytest.mark.parametrize(
    ("current", "target", "expected", "following"),
    [
        ("todo", None, "doing", "done"),
        ("doing", None, "done", None),
        ("todo", "doing", "doing", "done"),
    ],
)
def test_transition_allowed(
    client: TestClient, current: str, target: str | None, expected: str, following: str | None
) -> None:
    body = {"status": current} if target is None else {"status": current, "target": target}
    response = client.post("/api/v1/items/plan-the-launch/transition", json=body)
    assert response.status_code == 200
    assert response.json() == {
        "slug": "plan-the-launch",
        "previous_status": current,
        "status": expected,
        "next_status": following,
    }


@pytest.mark.parametrize(
    ("slug", "body", "status", "code"),
    [
        ("plan", {"status": "todo", "target": "done"}, 409, "transition_invalid"),
        ("plan", {"status": "done"}, 409, "status_terminal"),
        ("plan", {"status": "archived"}, 422, "status_unknown"),
        ("plan", {"status": "todo", "target": "later"}, 422, "status_unknown"),
        ("Not_A_Slug", {"status": "todo"}, 422, "slug_invalid"),
    ],
)
def test_transition_errors(
    client: TestClient, slug: str, body: dict[str, str], status: int, code: str
) -> None:
    response = client.post(f"/api/v1/items/{slug}/transition", json=body)
    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["code"] == code
