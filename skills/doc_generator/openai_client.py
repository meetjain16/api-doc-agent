"""LLM client for API DocAgent.

Uses the OpenAI-compatible SDK pointed at the org proxy (imllm.intermesh.net).
Exposes the same public interface: generate_text() and generate_json().
All config is read from .env:
  LLM_BASE_URL  — proxy endpoint, e.g. https://imllm.intermesh.net/v1
  LLM_API_KEY   — org API key
  LLM_MODEL     — model name, e.g. anthropic/claude-haiku-4-5
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
    from openai import OpenAI as _OpenAI
except ImportError:
    _OpenAI = None  # type: ignore[assignment]


DEFAULT_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_BASE_URL = "https://imllm.intermesh.net/v1"
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
    if _OpenAI is None:
        raise RuntimeError("openai SDK not installed. Run: pip install openai")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)
    if not api_key:
        raise RuntimeError("LLM_API_KEY is missing. Add it to .env.")
    _client = _OpenAI(api_key=api_key, base_url=base_url)
    return _client


def _is_auth_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "401" in msg or "authentication" in msg or "invalid api key" in msg or "permission" in msg


def _chat(prompt: str, system_prompt: str) -> str:
    _load_environment()
    if _OpenAI is None:
        raise RuntimeError("openai SDK not installed. Run: pip install openai")

    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set. Add it to .env.")

    model = os.getenv("LLM_MODEL", DEFAULT_MODEL)
    max_retries = DEFAULT_MAX_RETRIES

    for attempt in range(1, max_retries + 2):
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=model,
                max_tokens=DEFAULT_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content or ""
            logger.info("LLM response generated (model=%s)", model)
            return text.strip()
        except Exception as exc:
            if _is_auth_error(exc):
                logger.error("Authentication failed — check LLM_API_KEY in .env: %s", exc)
                raise
            if attempt > max_retries:
                logger.error("LLM request failed after %d attempts: %s", attempt, exc)
                raise
            sleep = min(0.5 * attempt, 2.0)
            logger.warning("LLM attempt %d/%d failed; retrying in %.1fs: %s", attempt, max_retries + 1, sleep, exc)
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
