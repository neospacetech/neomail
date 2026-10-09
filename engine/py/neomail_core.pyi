"""Type stubs for the ``neomail_core`` extension module.

Threading and Smart Send take and return JSON text; see the backend's
``neomail.engine`` module for the typed wrappers the service uses.
"""

from typing import Final, Literal, TypedDict

MailboxRoleName = Literal["inbox", "drafts", "sent", "archive", "junk", "trash", "custom"]
ClaimKindName = Literal["presence", "meeting_time", "availability", "attachment_ref", "recipient_ref"]
FactKindName = Literal["busy", "travel", "ooo", "focus"]
ErrorCode = Literal[
    "address_empty",
    "address_invalid",
    "address_too_long",
    "recipients_empty",
    "recipients_too_many",
    "subject_too_long",
    "message_id_invalid",
    "mailbox_name_empty",
    "mailbox_name_invalid",
    "mailbox_role_unknown",
    "claim_kind_unknown",
    "fact_kind_unknown",
    "interval_invalid",
    "mailbox_role_taken",
    "mailbox_name_taken",
    "claim_invalid",
    "payload_invalid",
]

class ParsedAddress(TypedDict):
    name: str | None
    email: str
    canonical: str
    display: str

Envelope = TypedDict(
    "Envelope",
    {
        "from": ParsedAddress,
        "to": list[ParsedAddress],
        "cc": list[ParsedAddress],
        "bcc": list[ParsedAddress],
        "subject": str,
    },
)

__version__: Final[str]
EMAIL_MAX_LEN: Final[int]
SUBJECT_MAX_CHARS: Final[int]
MAILBOX_NAME_MAX_CHARS: Final[int]
RECIPIENTS_MAX: Final[int]
MAX_CLAIMS: Final[int]
MAILBOX_ROLES: Final[tuple[MailboxRoleName, ...]]
CLAIM_KINDS: Final[tuple[ClaimKindName, ...]]
FACT_KINDS: Final[tuple[FactKindName, ...]]
ERROR_CODES: Final[tuple[ErrorCode, ...]]

class MailError(ValueError):
    """A domain rule rejected the input. ``code`` holds the stable error code."""

    code: ErrorCode

def parse_address(raw: str) -> ParsedAddress:
    """Parse ``addr``, ``<addr>``, ``Name <addr>`` or ``"Last, First" <addr>``."""

def parse_address_list(raw: str) -> list[ParsedAddress]:
    """Parse a comma- or semicolon-separated list; empty entries are skipped."""

def normalize_email(raw: str) -> str:
    """Canonical (case-folded) ``local@domain``."""

def validate_envelope(
    sender: str, to: list[str], cc: list[str], bcc: list[str], subject: str
) -> Envelope:
    """Validate an envelope; recipients are deduplicated across To, Cc and Bcc."""

def validate_subject(raw: str) -> str:
    """Collapse whitespace; raises ``subject_too_long``."""

def normalize_subject(raw: str) -> str:
    """Base subject without ``Re:``/``Fwd:`` prefixes and list tags."""

def is_reply_subject(raw: str) -> bool:
    """Whether the subject starts with a reply or forward prefix."""

def parse_message_id(raw: str) -> str:
    """Validate a Message-ID and return it without angle brackets."""

def extract_message_ids(header: str) -> list[str]:
    """Every Message-ID in a References or In-Reply-To header."""

def normalize_mailbox_name(raw: str) -> str:
    """Normalise a hierarchical mailbox name such as ``Projects / Acme``."""

def role_for_name(name: str) -> MailboxRoleName:
    """Role suggested by a mailbox name; ``custom`` when unrecognised."""

def role_rank(role: str) -> int:
    """Display rank of a role: inbox first, custom last."""

def validate_new_mailbox(name: str, role: str, existing: list[tuple[str, str]]) -> str:
    """Check a new mailbox against existing ``(name, role)`` pairs; returns the normalised name."""

def build_threads(messages: str) -> str:
    """JSON list of ``{key, message_id, in_reply_to, references, subject, date}`` -> threads."""

def check_smart_send(request: str) -> str:
    """JSON ``{claims, facts, draft}`` -> JSON list of findings."""

def extract_local_claims(text: str) -> str:
    """Attachment and recipient mentions in draft text, as a JSON list of claims."""
