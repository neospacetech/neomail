"""Load ``contracts/`` and build the runtime manifest.

The manifest served at ``/.well-known/neosuite/manifest.json`` is generated from
the same files other repos depend on, so the running service can never drift
from its published contracts.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neomail import COMPONENT, TITLE, __version__
from neomail.settings import Settings

MANIFEST_PATH = "/.well-known/neosuite/manifest.json"
ACTION_INVOKE_PATH = "/neosuite/actions/v1/{action_id}:invoke"
MANIFEST_VERSION = 1


class ContractsNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class Contracts:
    """Parsed contents of a ``contracts/`` directory, keyed by contract name."""

    root: Path
    types: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)


def find_contracts_dir(settings: Settings) -> Path:
    """Resolve the contracts directory.

    ``NEOMAIL_CONTRACTS_DIR`` wins. Otherwise look for a ``contracts/``
    directory above this file, which is where it is in a source checkout.
    """
    if settings.contracts_dir is not None:
        if not settings.contracts_dir.is_dir():
            raise ContractsNotFoundError(f"{settings.contracts_dir} is not a directory")
        return settings.contracts_dir
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contracts"
        if (candidate / "types").is_dir():
            return candidate
    raise ContractsNotFoundError("no contracts/ directory found; set NEOMAIL_CONTRACTS_DIR")


def _load_dir(directory: Path) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    if not directory.is_dir():
        return loaded
    for path in sorted(directory.glob("*.json")):
        with path.open(encoding="utf-8") as fh:
            loaded[path.stem] = json.load(fh)
    return loaded


def load_contracts(root: Path) -> Contracts:
    return Contracts(
        root=root,
        types=_load_dir(root / "types"),
        events=_load_dir(root / "events"),
        actions=_load_dir(root / "actions"),
    )


def build_manifest(contracts: Contracts, settings: Settings) -> dict[str, Any]:
    """The per-service runtime manifest harvested by NeoMind and NeoFlow."""
    return {
        "manifest_version": MANIFEST_VERSION,
        "service": {"id": COMPONENT, "name": TITLE, "version": __version__, "api_base": "/api/v1"},
        "types": [
            {
                "name": name,
                "title": schema.get("title", name),
                "description": schema.get("description", ""),
                "schema": schema,
            }
            for name, schema in contracts.types.items()
        ],
        "events": [
            {"type": name, "description": schema.get("description", ""), "data_schema": schema}
            for name, schema in contracts.events.items()
        ],
        "actions": list(contracts.actions.values()),
        "context_providers": [],
        "settings_schema": type(settings).model_json_schema(),
    }
