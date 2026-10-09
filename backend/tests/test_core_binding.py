"""The extension module behaves as its stub promises."""

import json

import neomail_core as core
import pytest


def test_constants() -> None:
    assert core.MAILBOX_ROLES == ("inbox", "drafts", "sent", "archive", "junk", "trash", "custom")
    assert core.SUBJECT_MAX_CHARS == 998
    assert "meeting_time" in core.CLAIM_KINDS
    assert core.FACT_KINDS == ("busy", "travel", "ooo", "focus")
    assert len(set(core.ERROR_CODES)) == len(core.ERROR_CODES)


def test_errors_carry_codes() -> None:
    with pytest.raises(ValueError, match="missing @") as info:
        core.parse_address("bob")
    assert isinstance(info.value, core.MailError)
    assert info.value.code == "address_invalid"
    with pytest.raises(core.MailError) as bad_json:
        core.build_threads("{")
    assert bad_json.value.code == "payload_invalid"


def test_addresses_and_subjects() -> None:
    assert core.normalize_email("Bob <Bob@Example.ORG>") == "bob@example.org"
    assert [a["email"] for a in core.parse_address_list("a@x.io; <b@y.io>,,")] == [
        "a@x.io",
        "b@y.io",
    ]
    assert core.normalize_subject("RE: Fwd: [ops] Disk full") == "Disk full"
    assert core.is_reply_subject("AW: Angebot")
    assert core.extract_message_ids("<a@x> junk <b@x> <a@x>") == ["a@x", "b@x"]
    assert core.parse_message_id("<id@host>") == "id@host"


def test_mailboxes() -> None:
    assert core.normalize_mailbox_name(" inbox ") == "INBOX"
    assert core.role_for_name("Sent Items") == "sent"
    assert core.role_rank("inbox") < core.role_rank("custom")
    with pytest.raises(core.MailError) as info:
        core.validate_new_mailbox("x", "inbox", [("INBOX", "inbox")])
    assert info.value.code == "mailbox_role_taken"
    with pytest.raises(core.MailError) as unknown:
        core.role_rank("spam")
    assert unknown.value.code == "mailbox_role_unknown"


def test_threads_and_smart_send() -> None:
    threads = json.loads(
        core.build_threads(
            json.dumps(
                [
                    {"key": "a", "message_id": "<1@x>", "subject": "Plan", "date": 1},
                    {
                        "key": "b",
                        "message_id": "<2@x>",
                        "references": "<1@x>",
                        "subject": "Re: Plan",
                        "date": 2,
                    },
                ]
            )
        )
    )
    assert threads == [{"root": "a", "messages": ["a", "b"], "subject": "Plan", "last_date": 2}]
    claims = json.loads(core.extract_local_claims("Attached is the file."))
    findings = json.loads(core.check_smart_send(json.dumps({"claims": claims, "draft": {}})))
    assert [f["rule"] for f in findings] == ["missing_attachment"]
