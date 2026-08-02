"""Tests for LLM client module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.config import LLMConfig
from src.llm.client import OpencodeLLMClient


def test_client_init():
    """OpencodeLLMClient should initialize with config."""
    config = LLMConfig(enabled=True, zen_models=["opencode/test-model"])
    client = OpencodeLLMClient(config)
    assert client.config == config
    assert client.total_calls == 0
    assert client.total_failures == 0
    assert not client.paid_used


def test_client_available_when_disabled():
    """available should be False when config.enabled is False."""
    config = LLMConfig(enabled=False)
    client = OpencodeLLMClient(config)
    assert not client.available


def test_client_available_when_no_binary():
    """available should be False when opencode binary is not on PATH."""
    config = LLMConfig(enabled=True, opencode_path="/nonexistent/opencode")
    client = OpencodeLLMClient(config)
    assert not client.available


def test_client_available_when_binary_exists():
    """available should be True when opencode binary is found."""
    import shutil

    opencode_path = shutil.which("opencode")
    if not opencode_path:
        import pytest
        pytest.skip("opencode not on PATH")

    config = LLMConfig(enabled=True, opencode_path=opencode_path)
    client = OpencodeLLMClient(config)
    assert client.available


def test_parse_ndjson_response():
    """_parse_ndjson_response should extract text from NDJSON."""
    ndjson = (
        '{"type": "text", "part": {"text": "Hello"}}\n'
        '{"type": "text", "part": {"text": " World"}}\n'
        '{"type": "assistant", "part": {}}\n'
    )
    result = OpencodeLLMClient._parse_ndjson_response(ndjson)
    assert result == "Hello World"


def test_parse_ndjson_response_empty():
    """_parse_ndjson_response should return empty string for empty input."""
    result = OpencodeLLMClient._parse_ndjson_response("")
    assert result == ""


def test_parse_ndjson_response_string_part():
    """_parse_ndjson_response should handle string part values."""
    ndjson = '{"type": "text", "part": "simple text"}\n'
    result = OpencodeLLMClient._parse_ndjson_response(ndjson)
    assert result == "simple text"


def test_parse_ndjson_response_invalid_json():
    """_parse_ndjson_response should skip invalid JSON lines."""
    ndjson = "not json\n{\"type\": \"text\", \"part\": {\"text\": \"valid\"}}\n"
    result = OpencodeLLMClient._parse_ndjson_response(ndjson)
    assert result == "valid"


def test_invoke_unavailable_client():
    """invoke should return None when client is not available."""
    config = LLMConfig(enabled=False)
    client = OpencodeLLMClient(config)
    result = client.invoke("test prompt")
    assert result is None


def test_get_usage_summary():
    """get_usage_summary should return a human-readable string."""
    config = LLMConfig(enabled=True)
    client = OpencodeLLMClient(config)
    summary = client.get_usage_summary()
    assert "LLM calls" in summary
    assert "failures" in summary
