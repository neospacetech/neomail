from typing import Any

from fastapi.testclient import TestClient

INVOKE = "/neosuite/actions/v1/neomail.item.transition:invoke"


def invoke(
    client: TestClient, body: dict[str, Any], key: str | None = None
) -> tuple[int, dict[str, Any], dict[str, str]]:
    headers = {"Idempotency-Key": key} if key else {}
    response = client.post(INVOKE, json=body, headers=headers)
    return response.status_code, response.json(), dict(response.headers)


def test_invoke_transition(client: TestClient) -> None:
    status, body, _ = invoke(client, {"input": {"slug": "ship-it", "status": "todo"}})
    assert status == 200
    assert body == {
        "action_id": "neomail.item.transition",
        "dry_run": False,
        "output": {
            "slug": "ship-it",
            "previous_status": "todo",
            "status": "doing",
            "next_status": "done",
        },
        "undo_token": None,
    }


def test_invoke_dry_run(client: TestClient) -> None:
    status, body, _ = invoke(
        client, {"input": {"slug": "ship-it", "status": "doing"}, "dry_run": True}
    )
    assert status == 200
    assert body["dry_run"] is True
    assert body["output"]["status"] == "done"


def test_invoke_core_error_is_problem(client: TestClient) -> None:
    status, body, headers = invoke(
        client, {"input": {"slug": "ship-it", "status": "todo", "target": "done"}}
    )
    assert status == 409
    assert headers["content-type"] == "application/problem+json"
    assert body["code"] == "transition_invalid"


def test_invoke_invalid_input(client: TestClient) -> None:
    status, body, _ = invoke(client, {"input": {"status": "todo"}})
    assert status == 422
    assert body["code"] == "request_invalid"
    assert ["body", "input", "slug"] in [err["loc"] for err in body["errors"]]


def test_invoke_unknown_action(client: TestClient) -> None:
    action = "neomail.item.delete"
    response = client.post(f"/neosuite/actions/v1/{action}:invoke", json={"input": {}})
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_idempotency_key_replays(client: TestClient) -> None:
    body = {"input": {"slug": "ship-it", "status": "todo"}}
    first = invoke(client, body, key="k-1")
    second = invoke(client, body, key="k-1")
    assert first[0] == second[0] == 200
    assert first[1] == second[1]
    assert second[2].get("idempotent-replayed") == "true"
    assert "idempotent-replayed" not in first[2]


def test_idempotency_key_reuse_with_other_body_is_rejected(client: TestClient) -> None:
    invoke(client, {"input": {"slug": "ship-it", "status": "todo"}}, key="k-2")
    status, body, _ = invoke(client, {"input": {"slug": "ship-it", "status": "doing"}}, key="k-2")
    assert status == 422
    assert body["code"] == "idempotency_key_reused"
