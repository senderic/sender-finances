"""Tests for config module."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.config import Settings


def test_default_settings():
    """Default Settings should load with sensible defaults."""
    s = Settings()
    assert s.simplifi.token_path == "~/.simplifiapi_token"
    assert s.database.sqlite_path == "data/sender-finances.db"
    assert s.enrichment.subscription_detection is True
    assert s.llm.enabled is True
    assert len(s.llm.zen_models) >= 2
    assert s.logging.level == "INFO"


def test_from_yaml():
    """Settings.from_yaml should parse a valid YAML file."""
    yaml_content = """
simplifi:
  token_path: /tmp/test-token
database:
  sqlite_path: /tmp/test.db
logging:
  level: DEBUG
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        yaml_path = f.name

    try:
        s = Settings.from_yaml(yaml_path)
        assert s.simplifi.token_path == "/tmp/test-token"
        assert s.database.sqlite_path == "/tmp/test.db"
        assert s.logging.level == "DEBUG"
    finally:
        Path(yaml_path).unlink()


def test_resolve_env_vars():
    """${VAR} placeholders should resolve from environment."""
    os.environ["TEST_PATH"] = "/custom/path"
    yaml_content = "database:\n  sqlite_path: ${TEST_PATH}"
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        yaml_path = f.name

    try:
        s = Settings.from_yaml(yaml_path).resolve_env_vars()
        assert s.database.sqlite_path == "/custom/path"
    finally:
        Path(yaml_path).unlink()


def test_resolve_env_vars_with_default():
    """${VAR:-default} should use the default when env var is unset."""
    os.environ.pop("NONEXISTENT_VAR", None)
    yaml_content = "database:\n  sqlite_path: ${NONEXISTENT_VAR:-/fallback/path}"
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        yaml_path = f.name

    try:
        s = Settings.from_yaml(yaml_path).resolve_env_vars()
        assert s.database.sqlite_path == "/fallback/path"
    finally:
        Path(yaml_path).unlink()


def test_resolve_env_vars_with_default_env_set():
    """${VAR:-default} should use the env var when set."""
    os.environ["EXISTENT_VAR"] = "/real/path"
    yaml_content = "database:\n  sqlite_path: ${EXISTENT_VAR:-/fallback/path}"
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        yaml_path = f.name

    try:
        s = Settings.from_yaml(yaml_path).resolve_env_vars()
        assert s.database.sqlite_path == "/real/path"
    finally:
        Path(yaml_path).unlink()


def test_nonexistent_config():
    """from_yaml with nonexistent path should return defaults."""
    s = Settings.from_yaml("/nonexistent/config.yaml")
    assert s.logging.level == "INFO"


def test_database_resolved_path():
    """DatabaseConfig.resolved_path should expand user and resolve."""
    s = Settings(database={"sqlite_path": "~/my-data/finances.db"})
    assert s.database.resolved_path == Path("~/my-data/finances.db").expanduser().resolve()


def test_simplifi_token_path():
    """SimplifiConfig.resolved_token_path should expand tilde."""
    s = Settings(simplifi={"token_path": "~/.simplifiapi_token"})
    assert s.simplifi.resolved_token_path == Path("~/.simplifiapi_token").expanduser().resolve()
