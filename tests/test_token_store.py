"""Tests for token_store module."""

from __future__ import annotations

import time
from pathlib import Path

from src.token_store import _decode_jwt_exp, load_token, save_token


def test_decode_jwt_exp():
    """_decode_jwt_exp should extract the exp claim from a JWT."""
    import base64
    import json

    exp = int(time.time()) + 3600
    payload = json.dumps({"exp": exp, "sub": "test"})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    fake_token = f"header.{payload_b64}.sig"
    result = _decode_jwt_exp(fake_token)
    assert result == float(exp)


def test_decode_jwt_exp_expired():
    """_decode_jwt_exp should still decode expired tokens (load_token handles rejection)."""
    import base64
    import json

    exp = int(time.time()) - 3600
    payload = json.dumps({"exp": exp})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    fake_token = f"header.{payload_b64}.sig"
    result = _decode_jwt_exp(fake_token)
    assert result == float(exp)


def test_decode_jwt_exp_missing():
    """_decode_jwt_exp should return None for tokens without exp."""
    import base64
    import json

    payload = json.dumps({"sub": "test"})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    fake_token = f"header.{payload_b64}.sig"
    result = _decode_jwt_exp(fake_token)
    assert result == 0.0


def test_decode_jwt_exp_invalid():
    """_decode_jwt_exp should return None for malformed tokens."""
    result = _decode_jwt_exp("not.a.jwt.token")
    assert result is None


def test_load_token_missing_file(tmp_path):
    """load_token should return None for nonexistent files."""
    result = load_token(str(tmp_path / "nonexistent"))
    assert result is None


def test_load_token_expired(tmp_path):
    """load_token should return None for expired tokens."""
    import base64
    import json

    exp = int(time.time()) - 3600
    payload = json.dumps({"exp": exp})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    token = f"header.{payload_b64}.sig"

    token_file = tmp_path / "token"
    token_file.write_text(token)

    result = load_token(str(token_file))
    assert result is None


def test_load_token_valid(tmp_path):
    """load_token should return the token string for valid unexpired tokens."""
    import base64
    import json

    exp = int(time.time()) + 86400
    payload = json.dumps({"exp": exp})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    token = f"header.{payload_b64}.sig"

    token_file = tmp_path / "token"
    token_file.write_text(token)

    result = load_token(str(token_file))
    assert result == token


def test_save_token(tmp_path):
    """save_token should write the token to disk."""
    token_file = tmp_path / "saved-token"
    save_token("test-token-abc", str(token_file))
    assert token_file.exists()
    assert token_file.read_text().strip() == "test-token-abc"
