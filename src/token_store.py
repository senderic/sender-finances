"""Read and validate the Simplifi access token from disk.

The token is a JWT stored as a single line in ``~/.simplifiapi_token``.
On load, the ``exp`` claim is checked against the current time. If the
token has expired or the file is missing/empty, ``None`` is returned.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import structlog

logger = structlog.get_logger()


def _decode_jwt_exp(token: str) -> float | None:
    """Extract the ``exp`` claim from a JWT (base64-encoded, no verification).

    Args:
        token: Raw JWT string (header.payload.signature).

    Returns:
        The ``exp`` timestamp as float, or ``None`` if decoding fails.
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)
        return float(payload.get("exp", 0))
    except Exception:
        return None


def load_token(token_path: str = "~/.simplifiapi_token") -> str | None:
    """Load the Simplifi token from disk and validate expiry.

    Args:
        token_path: Path to the file containing the raw JWT.

    Returns:
        The token string if valid, or ``None`` if missing/expired.
    """
    path = Path(token_path).expanduser()
    if not path.exists():
        logger.warning("token_file_missing", path=str(path))
        return None

    token = path.read_text().strip()
    if not token:
        logger.warning("token_file_empty", path=str(path))
        return None

    exp = _decode_jwt_exp(token)
    if exp is None:
        logger.warning("token_decode_failed", path=str(path))
        return None

    now = time.time()
    if now >= exp:
        remaining = (now - exp) / 3600
        logger.warning("token_expired", hours_ago=f"{remaining:.1f}")
        return None

    hours_left = (exp - now) / 3600
    logger.info("token_valid", hours_remaining=f"{hours_left:.1f}")
    return token


def save_token(token: str, token_path: str = "~/.simplifiapi_token") -> None:
    """Write a token string to disk.

    Args:
        token: The JWT access token.
        token_path: Destination file path.
    """
    path = Path(token_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token.strip() + "\n")
    logger.info("token_saved", path=str(path))
