"""Object identifiers: ULIDs and ``neo://<tenant>/o/<ulid>`` references."""

import os
import re
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"
_ULID_RE = re.compile(ULID_PATTERN)


def new_ulid(timestamp_ms: int | None = None, randomness: bytes | None = None) -> str:
    """A new ULID: 48-bit millisecond timestamp plus 80 random bits, Crockford base32."""
    ms = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    rand = os.urandom(10) if randomness is None else randomness
    if not 0 <= ms < 2**48 or len(rand) != 10:
        raise ValueError("a ULID needs a 48-bit timestamp and 10 random bytes")
    value = (ms << 80) | int.from_bytes(rand, "big")
    chars = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def is_ulid(value: str) -> bool:
    return bool(_ULID_RE.match(value))


def object_ref(tenant: str, ulid: str) -> str:
    """The object URI of ``ulid`` in ``tenant``."""
    return f"neo://{tenant}/o/{ulid}"
