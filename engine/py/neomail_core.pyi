"""Type stubs for the ``neomail_core`` extension module."""

from typing import Final, Literal

StatusName = Literal["todo", "doing", "done"]
ErrorCode = Literal[
    "title_empty",
    "title_too_long",
    "status_unknown",
    "transition_invalid",
    "status_terminal",
    "slug_invalid",
]

__version__: Final[str]
TITLE_MAX_CHARS: Final[int]
SLUG_MAX_LEN: Final[int]
STATUSES: Final[tuple[StatusName, ...]]
ERROR_CODES: Final[tuple[ErrorCode, ...]]

class ItemError(ValueError):
    """A domain rule rejected the input. ``code`` holds the stable error code."""

    code: ErrorCode

def normalize_title(raw: str) -> str:
    """Trim, collapse whitespace and check the length is 1..=TITLE_MAX_CHARS."""

def slugify(title: str) -> str:
    """Derive a URL-safe slug from a title."""

def is_valid_slug(value: str) -> bool:
    """Whether ``value`` is a well-formed slug."""

def validate_slug(value: str) -> str:
    """Return ``value`` unchanged if it is a well-formed slug; raises ``slug_invalid``."""

def next_status(current: str) -> StatusName:
    """The status that follows ``current``; raises ``status_terminal`` for ``done``."""

def transition(current: str, target: str) -> StatusName:
    """Move from ``current`` to ``target``; raises ``transition_invalid`` if not allowed."""

class Item:
    """A validated item. Construct with a raw title; it starts in ``todo``."""

    def __init__(self, title: str) -> None: ...
    @property
    def title(self) -> str: ...
    @property
    def slug(self) -> str: ...
    @property
    def status(self) -> StatusName: ...
    def rename(self, title: str) -> None: ...
    def advance(self) -> StatusName: ...
    def move_to(self, target: str) -> StatusName: ...
    def to_dict(self) -> dict[str, str]: ...
