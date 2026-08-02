"""Opencode LLM client for enrichment tasks.

Mirrors the sender-trades pattern: shells out to the ``opencode`` CLI,
parses NDJSON responses, and provides a fallback chain from free Zen
models to paid Go models.

Usage::

    from src.config import LLMConfig
    from src.llm.client import OpencodeLLMClient

    config = LLMConfig(enabled=True)
    client = OpencodeLLMClient(config)
    response = client.invoke("Summarize this text.", "You are a helpful assistant.")
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time

import structlog

from src.config import LLMConfig

logger = structlog.get_logger()


class OpencodeLLMClient:
    """LLM client that invokes the opencode CLI with fallback chaining."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.last_served_by: str | None = None
        self.last_fallback_hit: bool = False
        self.paid_used: bool = False
        self.total_calls: int = 0
        self.total_failures: int = 0
        self.total_input_chars: int = 0
        self.total_output_chars: int = 0
        self.total_elapsed: float = 0.0
        self.fallback_hits: int = 0

    @property
    def available(self) -> bool:
        """Check if opencode CLI is on PATH."""
        if not self.config.enabled:
            return False
        return shutil.which(self.config.opencode_path) is not None

    def invoke(self, prompt: str, system_prompt: str | None = None) -> str | None:
        """Send prompt to LLM, trying models in order until one succeeds.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system-level instructions.

        Returns:
            The concatenated text response, or ``None`` if all models fail.
        """
        if not self.available:
            logger.warning("llm_unavailable")
            return None

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"

        all_models = list(dict.fromkeys(self.config.zen_models + self.config.paid_go_models))
        input_chars = len(full_prompt)

        for idx, model_id in enumerate(all_models):
            is_paid = model_id.startswith("opencode-go/")
            self.last_served_by = model_id

            if idx > 0:
                self.last_fallback_hit = True
                self.fallback_hits += 1

            logger.info("llm_call", model=model_id, input_chars=input_chars)
            start = time.monotonic()

            try:
                result = subprocess.run(
                    [
                        self.config.opencode_path,
                        "run",
                        "-m",
                        model_id,
                        "--format",
                        "json",
                        "--auto",
                        "--dir",
                        "/tmp",
                        "--pure",
                        full_prompt,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_sec,
                )
            except subprocess.TimeoutExpired:
                logger.warning("llm_timeout", model=model_id)
                continue

            elapsed = time.monotonic() - start
            self.total_calls += 1
            self.total_elapsed += elapsed

            if result.returncode != 0 or not result.stdout.strip():
                self.total_failures += 1
                logger.warning(
                    "llm_failed",
                    model=model_id,
                    returncode=result.returncode,
                    stderr=result.stderr[:200] if result.stderr else "",
                )
                continue

            text = self._parse_ndjson_response(result.stdout)
            if not text:
                self.total_failures += 1
                logger.warning("llm_empty_response", model=model_id)
                continue

            if is_paid:
                self.paid_used = True

            self.total_input_chars += input_chars
            self.total_output_chars += len(text)
            self.last_fallback_hit = idx > 0

            logger.info(
                "llm_success", model=model_id, output_chars=len(text), elapsed=f"{elapsed:.1f}s"
            )
            return text

        logger.error("llm_all_failed", models_tried=len(all_models))
        return None

    @staticmethod
    def _parse_ndjson_response(stdout: str) -> str:
        """Extract text content from opencode NDJSON output.

        Each line is a JSON object. Collects ``text`` from
        ``type: "text"`` events.

        Args:
            stdout: Raw stdout from ``opencode run --format json``.

        Returns:
            Concatenated text chunks.
        """
        parts: list[str] = []
        for line in stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "text":
                content = event.get("part", {})
                if isinstance(content, dict):
                    parts.append(content.get("text", ""))
                elif isinstance(content, str):
                    parts.append(content)
        return "".join(parts)

    def get_usage_summary(self) -> str:
        """Return a human-readable usage summary."""
        return (
            f"LLM calls: {self.total_calls} total, {self.total_failures} failures, "
            f"{self.fallback_hits} fallbacks, paid used: {self.paid_used}, "
            f"{self.total_output_chars} output chars, {self.total_elapsed:.1f}s elapsed"
        )
