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
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from .model_registry import discover_used_models

MIN_RESPONSE_CHARS = 50
MAX_RETRIES = 3
CALL_TIMEOUT_SECS = 120
RETRY_BACKOFF_SECS = [2, 5, 10]
QUOTA_VERIFY_TIMEOUT_SECS = 30
QUOTA_PROMPT_MARKER_NAME = "QUOTA_PROMPT.json"

GEMINI_HOME = Path(os.environ.get("GEMINI_HOME", str(Path.home() / ".gemini")))
# Regex captures any "model":"gemini-..." occurrence in session logs / settings.
_MODEL_PATTERN = re.compile(r'"model"\s*:\s*"(gemini-[A-Za-z0-9.\-]+)"')
# Files with content below this size are usually session-metadata-only stubs.
_MIN_SESSION_BYTES = 300

_RESOLVED_MODEL_CACHE: Optional[str] = None

# Quota-switch coordination — shared across ThreadPoolExecutor workers.
# First thread to hit quota acquires the lock, verifies, prompts user, and
# updates _RESOLVED_MODEL_CACHE. Other threads then transparently use the new
# model on their next call. _TERMINAL_QUOTA short-circuits if user picked 'q'
# or no alternative model is available.
_SWITCH_LOCK = threading.Lock()
_EXHAUSTED_MODELS: set[str] = set()
_TERMINAL_QUOTA = False


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


def _verify_quota_truly_exhausted(model: str) -> bool:
    """
    Probe the model with a tiny no-op prompt to confirm quota is actually exhausted
    (not a transient 429 / misclassified error). Returns True only if probe also
    reports a quota marker. Uses OAuth env so probe matches main call path.
    """
    cmd = ["gemini", "-p", "ok"]
    if model:
        cmd += ["-m", model]
    cmd += ["--yolo"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=QUOTA_VERIFY_TIMEOUT_SECS,
            env=_build_oauth_env(),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Treat probe failure as "cannot confirm" → assume exhausted to be safe.
        return True
    return _is_quota_error(proc.stderr or "") or _is_quota_error(proc.stdout or "")


def _write_quota_marker(workspace: Path, exhausted: str, candidates: list[str]) -> Path:
    """Drop a JSON marker so user can resume by setting GEMINI_MODEL env var."""
    marker = workspace / QUOTA_PROMPT_MARKER_NAME
    payload = {
        "exhausted_model": exhausted,
        "exhausted_so_far": sorted(_EXHAUSTED_MODELS | {exhausted}),
        "candidate_models": candidates,
        "instruction": (
            "Stdin/tty unavailable for interactive prompt. "
            "Pick one of candidate_models and re-run /pdf-convert with "
            "GEMINI_MODEL=<chosen> to resume from this workspace."
        ),
    }
    try:
        marker.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"[gemini_client] failed to write quota marker: {e}", file=sys.stderr)
    return marker


def _resolve_workspace_dir() -> Optional[Path]:
    """Best-effort: derive the /tmp/pdf_convert_<name>/ workspace from sys.argv."""
    for arg in sys.argv:
        if arg and "/tmp/pdf_convert_" in arg:
            p = Path(arg)
            while p.parent != p:
                if p.name.startswith("pdf_convert_"):
                    return p
                p = p.parent
    return None


def _prompt_model_switch(exhausted_model: str) -> Optional[str]:
    """
    Interactive: list user-known alternative models, read choice from /dev/tty.
    Returns chosen model id, or None to terminate (user 'q' / no candidates / no tty).
    Caller must hold _SWITCH_LOCK.
    """
    all_known = discover_used_models()
    candidates = [m for m in all_known if m != exhausted_model and m not in _EXHAUSTED_MODELS]

    if not candidates:
        print(
            f"\n[gemini_client] ⛔ no alternative models found in your Gemini CLI history.\n"
            f"[gemini_client]    Open `gemini` interactively, run /model to switch, then resume.\n",
            file=sys.stderr,
        )
        return None

    banner = (
        f"\n─────────────────────────────────────────────────────────\n"
        f"⚠️  QUOTA EXHAUSTED — model: {exhausted_model}\n"
        f"    (verified by probe call; not a transient error)\n"
        f"─────────────────────────────────────────────────────────\n"
        f"Pick a replacement model for the rest of this run\n"
        f"(in-memory only — your CLI's active model is NOT modified):\n"
    )
    # Build menu text once, write to tty so worker stderr noise doesn't interleave.
    menu_lines = [banner]
    for i, m in enumerate(candidates, 1):
        menu_lines.append(f"  [{i}] {m}\n")
    menu_lines.append("  [q] Stop + keep workspace for resume\n")
    menu_lines.append("Choose: ")

    try:
        tty = open("/dev/tty", "r+", encoding="utf-8", buffering=1)
    except OSError:
        workspace = _resolve_workspace_dir()
        print(
            f"\n[gemini_client] ⚠️  /dev/tty unavailable — cannot prompt interactively.\n",
            file=sys.stderr,
        )
        if workspace:
            marker = _write_quota_marker(workspace, exhausted_model, candidates)
            print(f"[gemini_client] wrote: {marker}", file=sys.stderr)
        return None

    try:
        tty.write("".join(menu_lines))
        tty.flush()
        for _ in range(3):
            choice = tty.readline().strip().lower()
            if choice == "q":
                tty.write("[gemini_client] user chose to stop. Workspace preserved.\n")
                tty.flush()
                return None
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(candidates):
                    chosen = candidates[idx - 1]
                    tty.write(f"[gemini_client] switching to: {chosen}\n")
                    tty.flush()
                    return chosen
            tty.write("Invalid choice. Enter a number or 'q': ")
            tty.flush()
        tty.write("[gemini_client] too many invalid attempts. Stopping.\n")
        tty.flush()
        return None
    finally:
        tty.close()


def _handle_quota_exhaustion(failing_model: str, stderr_msg: str) -> None:
    """
    Coordinated quota-switch flow. First thread in verifies + prompts; others
    block on the lock and inherit the new cached model on return.

    `failing_model` is the model the caller used when it hit the quota error.
    If another thread already switched away from it, this returns immediately
    so the caller retries with the new model. Otherwise we probe-verify, mark
    the model exhausted, and prompt the user.

    Raises QuotaExhaustedError if user declines, no alternative exists, or
    /dev/tty is unavailable. On success: updates _RESOLVED_MODEL_CACHE, returns
    silently → caller retries.
    """
    global _RESOLVED_MODEL_CACHE, _TERMINAL_QUOTA

    with _SWITCH_LOCK:
        if _TERMINAL_QUOTA:
            raise QuotaExhaustedError("quota terminal — user declined switch")

        current = _RESOLVED_MODEL_CACHE
        # Another thread may have switched after our subprocess started but
        # before we grabbed the lock. Detect that and let caller retry with new.
        if current and failing_model and current != failing_model:
            return

        target = failing_model or current or ""
        if target and target in _EXHAUSTED_MODELS:
            # Another thread already handled this exact failure.
            return

        # Verify it's a real exhaustion — guards against transient 429 misclassification.
        if target and not _verify_quota_truly_exhausted(target):
            print(
                f"[gemini_client] probe says {target} is responsive — treating as transient.",
                file=sys.stderr,
            )
            return  # caller retries same model

        if target:
            _EXHAUSTED_MODELS.add(target)
        chosen = _prompt_model_switch(target or "(cli default)")
        if not chosen:
            _TERMINAL_QUOTA = True
            raise QuotaExhaustedError(
                f"user declined model switch (exhausted: {sorted(_EXHAUSTED_MODELS)})"
            )

        _RESOLVED_MODEL_CACHE = chosen
        return  # caller retries with chosen model


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

            # Quota handling: verify + interactive switch (held by _SWITCH_LOCK).
            # _handle_quota_exhaustion re-raises QuotaExhaustedError if user declines
            # or no alternative exists; otherwise it updates the cached model and we
            # transparently retry on the next loop iteration with the new -m value.
            if _is_quota_error(stderr) or _is_quota_error(response):
                _handle_quota_exhaustion(active_model, stderr.strip()[:500] or "quota exhausted")
                continue  # retry with new model now in _RESOLVED_MODEL_CACHE

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
