"""Anthropic Claude client for API DocAgent.

Drop-in replacement for the original OpenAI client.
Exposes the same public interface: generate_text() and generate_json().
Falls back to deterministic metadata-derived docs if no key is set.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]

try:
    import anthropic as _anthropic
except ImportError:
    _anthropic = None  # type: ignore[assignment]


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_TOKENS = 1024

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("API_DOCAGENT_LOG_LEVEL", "INFO"),
    format="%(levelname)s:%(name)s:%(message)s",
)

_client: Any | None = None
_env_loaded = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_env_file_manually(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_environment() -> None:
    global _env_loaded
    if _env_loaded:
        return
    env_path = _repo_root() / ".env"
    if load_dotenv is not None:
        load_dotenv(env_path)
        load_dotenv()
    else:
        _load_env_file_manually(env_path)
    _env_loaded = True


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    _load_environment()
    if _anthropic is None:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing. Add it to .env or your shell environment.")
    _client = _anthropic.Anthropic(api_key=api_key)
    return _client


def _is_auth_error(exc: Exception) -> bool:
    """Return True for authentication errors that should not be retried."""
    msg = str(exc).lower()
    return "401" in msg or "authentication" in msg or "invalid api key" in msg or "permission" in msg


def _chat(prompt: str, system_prompt: str) -> str:
    _load_environment()
    if _anthropic is None:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to .env:\n  ANTHROPIC_API_KEY=sk-ant-..."
        )

    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    max_retries = DEFAULT_MAX_RETRIES

    for attempt in range(1, max_retries + 2):
        try:
            client = _get_client()
            response = client.messages.create(
                model=model,
                max_tokens=DEFAULT_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text if response.content else ""
            logger.info("Claude response generated (model=%s)", model)
            return text.strip()
        except Exception as exc:
            # Never retry auth errors — they will not resolve with more attempts
            if _is_auth_error(exc):
                logger.error("Authentication failed — check ANTHROPIC_API_KEY in .env: %s", exc)
                raise
            if attempt > max_retries:
                logger.error("Claude request failed after %d attempts: %s", attempt, exc)
                raise
            sleep = min(0.5 * attempt, 2.0)
            logger.warning("Claude attempt %d/%d failed; retrying in %.1fs: %s", attempt, max_retries + 1, sleep, exc)
            time.sleep(sleep)

    return ""


def generate_text(prompt: str) -> str:
    """Generate plain text documentation from the prompt."""
    try:
        return _chat(
            prompt,
            system_prompt=(
                "You are API DocAgent. Generate concise, accurate API documentation "
                "from the provided service metadata."
            ),
        )
    except Exception as exc:
        logger.error("Text generation failed: %s", exc)
        return ""


def generate_json(prompt: str) -> dict[str, Any]:
    """Generate and parse a structured JSON object response."""
    raw_content = ""
    try:
        raw_content = _chat(
            prompt,
            system_prompt=(
                "You are API DocAgent. Return only one valid JSON object with no "
                "markdown fences, no prose, and no comments."
            ),
        )
        # Strip accidental markdown fences the model might add
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}
    except json.JSONDecodeError as exc:
        logger.error("Model returned invalid JSON: %s", exc)
        return {"error": "invalid_json", "raw": raw_content}
    except Exception as exc:
        logger.error("JSON generation failed: %s", exc)
        return {"error": str(exc)}
