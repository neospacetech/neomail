"""Typed access to the Rust core.

Addresses, envelopes and mailboxes cross as small dictionaries; threading and
Smart Send exchange JSON text, which these wrappers encode and decode. Every
rule stays in ``neomail_core``.
"""

import json
from typing import Any

import neomail_core as core

JsonObject = dict[str, Any]


def build_threads(headers: list[JsonObject]) -> list[JsonObject]:
    """Group message headers into threads, newest activity first."""
    threads: list[JsonObject] = json.loads(core.build_threads(json.dumps(headers)))
    return threads


def check_smart_send(
    claims: list[JsonObject], facts: list[JsonObject], draft: JsonObject
) -> list[JsonObject]:
    request = {"claims": claims, "facts": facts, "draft": draft}
    findings: list[JsonObject] = json.loads(core.check_smart_send(json.dumps(request)))
    return findings


def extract_local_claims(text: str) -> list[JsonObject]:
    claims: list[JsonObject] = json.loads(core.extract_local_claims(text))
    return claims
