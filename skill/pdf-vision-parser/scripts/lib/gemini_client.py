#!/usr/bin/env python3
"""
gemini_client.py — Subprocess wrapper for `gemini -p` with retry and timeout handling.

Retries on empty/short responses (< MIN_RESPONSE_CHARS chars) up to MAX_RETRIES times
with a slightly varied prompt suffix to break repetition.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

MIN_RESPONSE_CHARS = 50
MAX_RETRIES = 3
CALL_TIMEOUT_SECS = 120
RETRY_BACKOFF_SECS = [2, 5, 10]

GEMINI_HOME = Path(os.environ.get("GEMINI_HOME", str(Path.home() / ".gemini")))
# Regex captures any "model":"gemini-..." occurrence in session logs / settings.
_MODEL_PATTERN = re.compile(r'"model"\s*:\s*"(gemini-[A-Za-z0-9.\-]+)"')
# Files with content below this size are usually session-metadata-only stubs.
_MIN_SESSION_BYTES = 300

_RESOLVED_MODEL_CACHE: Optional[str] = None


def _read_settings_model() -> str:
    """Read ~/.gemini/settings.json → model field (if user pinned it persistently)."""
    settings = GEMINI_HOME / "settings.json"
    if not settings.exists():
        return ""
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except Exception:
        return ""
    val = data.get("model")
    if isinstance(val, str) and val.strip():
        return val.strip()
    if isinstance(val, dict) and isinstance(val.get("name"), str):
        return val["name"].strip()
    return ""


def _scan_recent_session_model() -> str:
    """
    Inspect Gemini CLI's session logs (~/.gemini/tmp/<project>/chats/*.jsonl)
    and return the model id used in the most recently active session that has
    actual conversation content. This mirrors whatever the user was running in
    their last/current interactive `gemini` session.
    """
    tmp = GEMINI_HOME / "tmp"
    if not tmp.exists():
        return ""
    candidates: list[tuple[float, Path]] = []
    for chat_file in tmp.glob("*/chats/*.jsonl"):
        try:
            st = chat_file.stat()
        except OSError:
            continue
        if st.st_size < _MIN_SESSION_BYTES:
            continue  # metadata-only stub, no model recorded yet
        candidates.append((st.st_mtime, chat_file))
    # Also consider legacy .json sessions (older CLI format)
    for chat_file in tmp.glob("*/chats/*.json"):
        try:
            st = chat_file.stat()
        except OSError:
            continue
        if st.st_size < _MIN_SESSION_BYTES:
            continue
        candidates.append((st.st_mtime, chat_file))

    candidates.sort(reverse=True)
    # Inspect a few most-recent files; use last model reference within each.
    for _, path in candidates[:8]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        matches = _MODEL_PATTERN.findall(content)
        if matches:
            # last reference = model used at end of session
            return matches[-1]
    return ""


def detect_active_model() -> str:
    """
    Resolve which model to pass to `gemini -p`. Priority:
      1. GEMINI_MODEL env var (explicit override)
      2. ~/.gemini/settings.json `model` field (persistent pin)
      3. Most-recent non-empty session log (the "currently running" model)
      4. "" → omit -m, let CLI use its built-in default
    Result is cached for the process lifetime.
    """
    global _RESOLVED_MODEL_CACHE
    if _RESOLVED_MODEL_CACHE is not None:
        return _RESOLVED_MODEL_CACHE

    chosen = os.environ.get("GEMINI_MODEL", "").strip()
    source = "env"
    if not chosen:
        chosen = _read_settings_model()
        source = "settings.json"
    if not chosen:
        chosen = _scan_recent_session_model()
        source = "recent session"
    if not chosen:
        source = "cli default (no -m)"

    if chosen:
        print(f"[gemini_client] using model: {chosen} (source: {source})", flush=True)
    else:
        print(f"[gemini_client] using model: {source}", flush=True)

    _RESOLVED_MODEL_CACHE = chosen
    return chosen

# Quota-exhausted detection: when these phrases appear in stderr we MUST stop
# immediately. Retrying burns nothing useful (same per-account daily limit) and
# delays the eventual halt. Caller catches QuotaExhaustedError and aborts cleanly.
QUOTA_MARKERS = (
    "RESOURCE_EXHAUSTED",
    "QUOTA_EXHAUSTED",
    "quota will reset",
    "rateLimitExceeded",
    "429",
)


class QuotaExhaustedError(RuntimeError):
    """Raised when Gemini reports daily/per-minute quota exhaustion. Do not retry."""
    pass


def _is_quota_error(stderr: str) -> bool:
    return any(marker in stderr for marker in QUOTA_MARKERS)


# Env vars that, if present, push gemini CLI off the OAuth path onto API-key /
# Vertex auth. We strip them from the subprocess env so every call uses the
# OAuth credentials at ~/.gemini/oauth_creds.json (Ultra account = no daily cap).
_API_KEY_ENV_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_GCA",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "VERTEXAI_PROJECT",
    "VERTEXAI_LOCATION",
)

_OAUTH_ENV_LOGGED = False


def _build_oauth_env() -> dict:
    """Return os.environ copy with all API-key/Vertex selectors stripped, forcing OAuth."""
    global _OAUTH_ENV_LOGGED
    env = os.environ.copy()
    stripped = [k for k in _API_KEY_ENV_VARS if env.pop(k, None) is not None]
    if not _OAUTH_ENV_LOGGED:
        if stripped:
            print(f"[gemini_client] auth: OAuth (stripped {', '.join(stripped)} from subprocess env)", flush=True)
        else:
            print("[gemini_client] auth: OAuth (no API-key env vars present)", flush=True)
        _OAUTH_ENV_LOGGED = True
    return env


def call_gemini(
    prompt: str,
    image_path: Optional[str] = None,
    timeout: int = CALL_TIMEOUT_SECS,
) -> str:
    """
    Call `gemini -p <prompt> [-m <model>] --yolo --include-directories /tmp` via subprocess.
    Model defaults to whatever the gemini CLI session has active; pass GEMINI_MODEL
    env var only if you need to override. Image is embedded as @path in prompt text.
    """
    for attempt in range(MAX_RETRIES):
        # Append variation suffix on retries to avoid repeated empty responses
        effective_prompt = prompt if attempt == 0 else f"{prompt}\n\n[Retry {attempt}: ensure full ADE extraction]"

        if image_path and Path(image_path).exists():
            effective_prompt += f" @{image_path}"

        cmd = ["gemini", "-p", effective_prompt]
        active_model = detect_active_model()
        if active_model:
            cmd += ["-m", active_model]
        cmd += ["--yolo", "--include-directories", "/tmp"]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_build_oauth_env(),
            )
            response = proc.stdout.strip()
            stderr = proc.stderr or ""

            # Fail-fast on quota exhaustion — retries cannot help (per-account daily cap)
            if _is_quota_error(stderr) or _is_quota_error(response):
                raise QuotaExhaustedError(stderr.strip()[:500] or "quota exhausted")

            if len(response) >= MIN_RESPONSE_CHARS:
                return response

            reason = stderr.strip() or f"response too short ({len(response)} chars)"
            print(f"[gemini_client] attempt {attempt+1}/{MAX_RETRIES} failed: {reason}", flush=True)

        except subprocess.TimeoutExpired:
            print(f"[gemini_client] attempt {attempt+1}/{MAX_RETRIES} timed out after {timeout}s", flush=True)
        except FileNotFoundError:
            raise RuntimeError("gemini CLI not found — ensure it is installed and in PATH")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF_SECS[attempt])

    raise RuntimeError(f"gemini call failed after {MAX_RETRIES} attempts")
