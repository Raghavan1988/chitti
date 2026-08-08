# Bearer-token gate for the solo-dev mobile API.
"""Auth: a single shared API key until multi-user Sign in with Apple lands.

Every request must send:
    Authorization: Bearer <CHITTI_API_KEY>
"""

from .config import config


def extract_bearer(handler) -> str | None:
    """Return the bearer token from an HTTP request handler, or None."""
    header = handler.headers.get("Authorization") or handler.headers.get("authorization")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def authorized(handler) -> bool:
    """True when the request carries the configured API key."""
    token = extract_bearer(handler)
    if not token:
        return False
    # Constant-time-ish compare for the simple solo key.
    expected = config.api_key
    if len(token) != len(expected):
        return False
    result = 0
    for a, b in zip(token.encode(), expected.encode()):
        result |= a ^ b
    return result == 0
