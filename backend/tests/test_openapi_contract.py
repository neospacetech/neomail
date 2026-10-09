"""The published OpenAPI contract matches what the service actually serves."""

from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "api" / "openapi.yaml"
METHODS = {"get", "put", "post", "patch", "delete", "head", "options"}


def operations(doc: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (path, method): operation
        for path, item in doc["paths"].items()
        for method, operation in item.items()
        if method in METHODS
    }


def response_codes(operation: dict[str, Any]) -> set[str]:
    return {str(code) for code in operation.get("responses", {})}


def test_contract_lists_exactly_the_served_operations(client: TestClient) -> None:
    served = operations(client.get("/openapi.json").json())
    contract = operations(yaml.safe_load(CONTRACT.read_text()))
    assert set(contract) == set(served)
    for key, operation in served.items():
        assert contract[key]["operationId"] == operation["operationId"], key


def test_contract_documents_served_success_and_problem_codes(client: TestClient) -> None:
    served = operations(client.get("/openapi.json").json())
    contract = operations(yaml.safe_load(CONTRACT.read_text()))
    for key, operation in served.items():
        missing = response_codes(operation) - response_codes(contract[key])
        assert not missing, f"{key}: undocumented responses {missing}"


def test_contract_schemas_cover_served_models(client: TestClient) -> None:
    served = client.get("/openapi.json").json()["components"]["schemas"]
    contract = yaml.safe_load(CONTRACT.read_text())["components"]["schemas"]
    for name, schema in served.items():
        assert name in contract, f"model {name} missing from the contract"
        assert set(schema.get("required", [])) == set(contract[name].get("required", [])), name
        assert set(schema.get("properties", {})) == set(contract[name].get("properties", {})), name


def test_contract_version_matches_service(client: TestClient) -> None:
    served = client.get("/openapi.json").json()
    contract = yaml.safe_load(CONTRACT.read_text())
    assert contract["info"]["version"] == served["info"]["version"]
