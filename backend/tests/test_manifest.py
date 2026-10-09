import json
from pathlib import Path

from fastapi.testclient import TestClient

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


def test_manifest_shape(client: TestClient) -> None:
    response = client.get("/.well-known/neosuite/manifest.json")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["manifest_version"] == 1
    assert manifest["service"] == {
        "id": "neomail",
        "name": "NeoMail",
        "version": manifest["service"]["version"],
        "api_base": "/api/v1",
    }
    assert manifest["context_providers"] == []
    assert set(manifest) == {
        "manifest_version",
        "service",
        "types",
        "events",
        "actions",
        "context_providers",
        "settings_schema",
    }


def test_manifest_is_built_from_contracts(client: TestClient) -> None:
    manifest = client.get("/.well-known/neosuite/manifest.json").json()

    types = {entry["name"]: entry["schema"] for entry in manifest["types"]}
    events = {entry["type"]: entry["data_schema"] for entry in manifest["events"]}
    actions = {entry["id"]: entry for entry in manifest["actions"]}

    for path in (CONTRACTS / "types").glob("*.json"):
        assert types[path.stem] == json.loads(path.read_text())
    for entry in manifest["types"]:
        assert entry["title"]
        assert entry["description"]
    for path in (CONTRACTS / "events").glob("*.json"):
        assert events[path.stem] == json.loads(path.read_text())
    for path in (CONTRACTS / "actions").glob("*.json"):
        descriptor = json.loads(path.read_text())
        assert descriptor["id"] == path.stem
        assert actions[path.stem] == descriptor
        assert descriptor["effect"] in {"read", "write", "destructive", "external"}
        assert descriptor["title"]
        assert descriptor["description"]
        assert descriptor["input_schema"]["type"] == "object"

    assert {"neomail.Mailbox", "neomail.Thread", "neomail.Message"} <= set(types)
    assert "neomail.message.received" in events
    assert actions["neomail.message.send"]["effect"] == "external"
    assert actions["neomail.smartsend.check"]["effect"] == "read"


def test_manifest_settings_schema(client: TestClient) -> None:
    schema = client.get("/.well-known/neosuite/manifest.json").json()["settings_schema"]
    assert schema["type"] == "object"
    assert "stream_interval_seconds" in schema["properties"]


def test_contract_names_follow_conventions() -> None:
    for path in (CONTRACTS / "types").glob("*.json"):
        product, type_name = path.stem.split(".")
        assert product == "neomail"
        assert type_name[0].isupper()
    for directory in ("events", "actions"):
        for path in (CONTRACTS / directory).glob("*.json"):
            product, object_type, verb = path.stem.split(".")
            assert product == "neomail"
            assert object_type.islower()
            assert verb.islower()
