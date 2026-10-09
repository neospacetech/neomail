from pathlib import Path

from fastapi.testclient import TestClient

from neomail.app import create_app
from neomail.settings import Settings


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readyz_fails_without_contracts(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    app = create_app(Settings(environment="test", contracts_dir=missing))
    with TestClient(app) as client:
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["code"] == "unavailable"
        assert client.get("/healthz").status_code == 200


def test_metrics_exposition(client: TestClient) -> None:
    client.post("/api/v1/mailboxes", json={"owner": "user:a", "name": "Count me"})
    client.post("/api/v1/mailboxes", json={"owner": "user:a", "name": ""})
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = response.text
    assert "# TYPE neomail_http_requests_total counter" in body
    labels = 'method="POST",route="/api/v1/mailboxes"'
    assert f'neomail_http_requests_total{{{labels},status="201"}} 1' in body
    assert f'neomail_http_requests_total{{{labels},status="422"}} 1' in body
    assert "neomail_build_info{" in body


def test_metrics_use_route_templates(client: TestClient) -> None:
    client.get("/api/v1/messages/01ARZ3NDEKTSV4RRFFQ69G5FAV")
    body = client.get("/metrics").text
    assert 'route="/api/v1/messages/{message_id}"' in body
    assert "01ARZ3NDEKTSV4RRFFQ69G5FAV" not in body


def test_unknown_path_is_problem(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "not_found"


def test_wrong_method_is_problem(client: TestClient) -> None:
    response = client.delete("/api/v1/mailboxes")
    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"
