import pytest

from neomail.settings import Settings
from neomail.transport import (
    InMemoryTransport,
    JmapTransport,
    OutgoingMessage,
    TransportError,
    create_transport,
    jmap_send_request,
    submission_id_from,
)

MESSAGE = OutgoingMessage(
    message_id="abc@acme.neomail",
    sender={"name": "Alice", "email": "alice@example.org"},
    to=[{"name": None, "email": "bob@example.net"}],
    cc=[],
    bcc=[{"name": None, "email": "audit@example.org"}],
    subject="Hello",
    text="Hi Bob",
    in_reply_to=["orig@example.net"],
    references=["orig@example.net"],
)


def test_jmap_request_creates_and_submits_the_email() -> None:
    request = jmap_send_request(MESSAGE, "acc1", "id1", "sent1")
    assert request["using"][-1] == "urn:ietf:params:jmap:submission"
    (set_name, set_args, _), (submit_name, submit_args, _) = request["methodCalls"]
    assert (set_name, submit_name) == ("Email/set", "EmailSubmission/set")
    email = set_args["create"]["draft"]
    assert email["mailboxIds"] == {"sent1": True}
    assert email["messageId"] == ["abc@acme.neomail"]
    assert email["from"] == [{"name": "Alice", "email": "alice@example.org"}]
    assert email["bcc"] == [{"name": None, "email": "audit@example.org"}]
    assert email["inReplyTo"] == ["orig@example.net"]
    assert email["bodyValues"]["body"]["value"] == "Hi Bob"
    assert submit_args["create"]["send"] == {"emailId": "#draft", "identityId": "id1"}


def test_jmap_response_parsing() -> None:
    ok = {
        "methodResponses": [
            ["Email/set", {"created": {"draft": {"id": "e1"}}}, "c0"],
            ["EmailSubmission/set", {"created": {"send": {"id": "s1"}}}, "c1"],
        ]
    }
    assert submission_id_from(ok) == "s1"
    rejected = {
        "methodResponses": [
            ["Email/set", {"notCreated": {"draft": {"type": "invalidProperties"}}}, "c0"]
        ]
    }
    with pytest.raises(TransportError, match="invalidProperties"):
        submission_id_from(rejected)
    with pytest.raises(TransportError, match="unknownMethod"):
        submission_id_from({"methodResponses": [["error", {"type": "unknownMethod"}, "c0"]]})
    with pytest.raises(TransportError):
        submission_id_from({"methodResponses": []})


def test_unreachable_server_is_a_transport_error() -> None:
    transport = JmapTransport(
        api_url="http://127.0.0.1:9/jmap",
        account_id="a",
        identity_id="i",
        token="t",
        timeout_seconds=1,
    )
    with pytest.raises(TransportError, match="could not be reached"):
        transport.submit(MESSAGE)


def test_transport_follows_settings() -> None:
    assert isinstance(create_transport(Settings(environment="test")), InMemoryTransport)
    configured = Settings(
        environment="test",
        jmap_api_url="http://stalwart:8080/jmap",
        jmap_account_id="a",
        jmap_identity_id="i",
        jmap_token="secret",
    )
    transport = create_transport(configured)
    assert isinstance(transport, JmapTransport)
    assert transport.token == "secret"
