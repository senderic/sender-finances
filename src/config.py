"""Application configuration and settings management."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class SimplifiConfig(BaseModel):
    """Simplifi API configuration."""

    token_path: str = "~/.simplifiapi_token"

    @property
    def resolved_token_path(self) -> Path:
        return Path(self.token_path).expanduser().resolve()


class DatabaseConfig(BaseModel):
    """SQLite database configuration."""

    sqlite_path: str = "data/sender-finances.db"

    @property
    def resolved_path(self) -> Path:
        return Path(self.sqlite_path).expanduser().resolve()

    @property
    def connection_url(self) -> str:
        return f"sqlite:///{self.resolved_path}"


class EnrichmentConfig(BaseModel):
    """Toggles for enrichment features."""

    subscription_detection: bool = True
    merchant_normalization: bool = True
    recategorization: bool = True


class LLMConfig(BaseModel):
    """Configuration for LLM-powered enrichment via the opencode CLI.

    Follows the same pattern as sender-trades:
    - zen_models: free-tier models tried first, in order
    - paid_go_models: paid-tier models tried as fallback
    """

    enabled: bool = True
    opencode_path: str = "opencode"
    zen_models: list[str] = Field(
        default_factory=lambda: [
            "opencode/deepseek-v4-flash-free",
            "opencode/mimo-v2.5-free",
            "opencode/nemotron-3-ultra-free",
            "opencode/hy3-free",
        ]
    )
    paid_go_models: list[str] = Field(
        default_factory=lambda: [
            "opencode-go/glm-5.2",
            "opencode-go/kimi-k3",
            "opencode-go/qwen3.7-max",
        ]
    )
    timeout_sec: int = 60
    max_calls_per_run: int = 10


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"


class Settings(BaseSettings):
    """Root application settings loaded from YAML or environment variables."""

    simplifi: SimplifiConfig = SimplifiConfig()
    database: DatabaseConfig = DatabaseConfig()
    enrichment: EnrichmentConfig = EnrichmentConfig()
    llm: LLMConfig = LLMConfig()
    logging: LoggingConfig = LoggingConfig()

    @classmethod
    def from_yaml(cls, path: str | Path) -> Settings:
        """Load settings from a YAML configuration file.

        Args:
            path: Path to the YAML file.

        Returns:
            A populated Settings instance.
        """
        path = Path(path).expanduser().resolve()
        if not path.exists():
            return cls()
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return cls(**raw)

    def resolve_env_vars(self) -> Settings:
        """Resolve ``${VAR}`` and ``${VAR:-default}`` placeholders from environment."""

        def _resolve(value: object) -> object:
            if isinstance(value, str):
                result = value
                while "${" in result:
                    import re

                    def _replace(m: re.Match) -> str:
                        expr = m.group(1)
                        if ":-" in expr:
                            var, default = expr.split(":-", 1)
                            return os.environ.get(var.strip(), default.strip())
                        return os.environ.get(expr, "")

                    result = re.sub(r"\$\{([^}]+)\}", _replace, result)
                return result
            if isinstance(value, dict):
                return {k: _resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve(v) for v in value]
            return value

        resolved = _resolve(self.model_dump())
        return Settings(**resolved)
