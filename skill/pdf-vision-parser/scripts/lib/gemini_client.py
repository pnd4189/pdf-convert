#!/usr/bin/env python3
"""
gemini_client.py — Subprocess wrapper for `gemini -p` with retry and timeout handling.

Retries on empty/short responses (< MIN_RESPONSE_CHARS chars) up to MAX_RETRIES times
with a slightly varied prompt suffix to break repetition.
"""

import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Literal, Optional

from .model_registry import (
    discover_used_models,
    rank_pro_candidates,
    model_tier,
)

MIN_RESPONSE_CHARS = 50
MAX_RETRIES = 3
CALL_TIMEOUT_SECS = 120
RETRY_BACKOFF_SECS = [2, 5, 10]
QUOTA_VERIFY_TIMEOUT_SECS = 30
QUOTA_PROMPT_MARKER_NAME = "QUOTA_PROMPT.json"

# Probe ladder for strongest-Pro auto-detect. Top-2 ranked Pro models that
# pass a startup liveness probe; populated once per process. Phase 03 reads
# this to cascade Pro→Pro on confirmed RPD without re-probing.
PROBE_TIMEOUT_SECS = 20
_PRO_LADDER: list[str] = []

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


def _probe_model_alive(model: str) -> bool:
    """
    Liveness check: does `gemini -p ok -m <model>` return cleanly?
    Used by both startup probe ladder and phase-03 RPD verification.
    Quota / permission / not-found in stderr → not alive.
    """
    cmd = ["gemini", "-p", "ok", "-m", model, "--yolo"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECS,
            env=_build_oauth_env(),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    if proc.returncode != 0:
        return False
    blob = (proc.stderr or "") + (proc.stdout or "")
    if _is_quota_error(blob):
        return False
    if "PERMISSION_DENIED" in blob or "NOT_FOUND" in blob:
        return False
    return True


def strongest_pro_available() -> str:
    """
    Probe top-2 Pro candidates from the user's CLI history; cache them in
    _PRO_LADDER for phase-03 cascade; return the strongest that responds.
    Returns "" if no Pro model in history responds.
    """
    global _PRO_LADDER
    history = discover_used_models()
    ranked = rank_pro_candidates(history)
    if not ranked:
        print("[gemini_client] no Pro models in CLI history.", flush=True)
        _PRO_LADDER = []
        return ""
    print(
        f"[gemini_client] Pro candidates (strongest first): {ranked}",
        flush=True,
    )
    ladder: list[str] = []
    primary = ""
    for m in ranked[:2]:
        print(
            f"[gemini_client]   probing {m} (timeout {PROBE_TIMEOUT_SECS}s)...",
            flush=True,
        )
        if _probe_model_alive(m):
            print(f"[gemini_client]   {m} → OK", flush=True)
            ladder.append(m)
            if not primary:
                primary = m
        else:
            print(f"[gemini_client]   {m} → unavailable", flush=True)
    _PRO_LADDER = ladder
    return primary


def detect_active_model() -> str:
    """
    Resolve which model to pass to `gemini -p`. Priority:
      1. GEMINI_MODEL env var (explicit override, no probe)
      2. strongest_pro_available() — auto-detect strongest Pro in history
      3. ~/.gemini/settings.json `model` field (persistent pin)
      4. Most-recent non-empty session log
      5. "" → omit -m, let CLI use its built-in default
    Result is cached for the process lifetime.
    """
    global _RESOLVED_MODEL_CACHE
    if _RESOLVED_MODEL_CACHE is not None:
        return _RESOLVED_MODEL_CACHE

    chosen = os.environ.get("GEMINI_MODEL", "").strip()
    source = "env GEMINI_MODEL"
    if not chosen:
        chosen = strongest_pro_available()
        source = "strongest Pro auto-detect"
    if not chosen:
        chosen = _read_settings_model()
        source = "~/.gemini/settings.json"
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

# Quota classification — RPM (per-minute, transient) vs RPD (per-day, terminal).
# Conflating the two caused the original bug: an RPM burst was misread as RPD
# exhaustion and triggered Pro→Flash cascade. We now match each kind separately
# and bias ambiguous "RESOURCE_EXHAUSTED" hits toward RPM (safe — backoff and
# retry the same model rather than degrading quality).
RPM_MARKERS = (
    "Per-minute quota",
    "Quota exceeded for quota metric 'Requests per minute",
    "rateLimitExceeded",
    "Rate limit exceeded",
)
RPD_MARKERS = (
    "Daily quota",
    "Quota exceeded for quota metric 'Requests per day",
    "quota will reset",
)
GENERIC_QUOTA_MARKERS = (
    "RESOURCE_EXHAUSTED",
    "QUOTA_EXHAUSTED",
    "quota exceeded",
)
# Combined view for any-quota detection (probe rejection, main-loop classify).
QUOTA_MARKERS = RPM_MARKERS + RPD_MARKERS + GENERIC_QUOTA_MARKERS

# RPM backoff parameters — wait roughly one rate-limit window before retrying
# the same model. 90s base + 0–30s jitter avoids thundering-herd across workers.
RPM_BACKOFF_BASE_SECS = 90
RPM_BACKOFF_JITTER_SECS = 30
RPM_MAX_RETRIES = 5

# RPD verification — 3 probes spaced 120s apart. Any single OK probe means
# the original failure was lingering RPM, not daily exhaustion.
RPD_PROBE_COUNT = 3
RPD_PROBE_INTERVAL_SECS = 120


def classify_quota_error(stderr: str) -> Literal["none", "rpm", "rpd", "ambiguous"]:
    """Bucket a stderr blob. Ambiguous → caller treats as RPM (safe)."""
    if any(m in stderr for m in RPD_MARKERS):
        return "rpd"
    if any(m in stderr for m in RPM_MARKERS):
        return "rpm"
    if any(m in stderr for m in GENERIC_QUOTA_MARKERS):
        return "ambiguous"
    return "none"

# Stderr phrases that look scary but are TRANSIENT vision/streaming hiccups —
# never quota-related. If a failed call's stderr contains any of these AND no
# QUOTA_MARKERS, we treat it as a transient retry-able failure (do not probe,
# do not cascade). This stops the well-known "Invalid stream … empty response"
# vision-API misbehavior from being misclassified as quota exhaustion.
TRANSIENT_MARKERS = (
    "Invalid stream",
    "empty response",
    "malformed tool call",
    "MALFORMED_FUNCTION_CALL",
    "INTERNAL",
    "DEADLINE_EXCEEDED",
)


class QuotaExhaustedError(RuntimeError):
    """Raised when Gemini reports daily/per-minute quota exhaustion. Do not retry."""
    pass


def _is_quota_error(stderr: str) -> bool:
    return any(marker in stderr for marker in QUOTA_MARKERS)


def _is_transient_error(stderr: str) -> bool:
    return any(marker in stderr for marker in TRANSIENT_MARKERS)


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


def _write_quota_marker(
    workspace: Path,
    exhausted: str,
    candidates: list[str],
    auto_cascaded_to: Optional[str] = None,
) -> Path:
    """
    Drop a JSON marker recording the quota event so the user can audit headless
    runs or resume manually with GEMINI_MODEL=<chosen>.
    """
    marker = workspace / QUOTA_PROMPT_MARKER_NAME
    payload = {
        "exhausted_model": exhausted,
        "exhausted_so_far": sorted(_EXHAUSTED_MODELS | {exhausted}),
        "candidate_models": candidates,
        "auto_cascaded_to": auto_cascaded_to,
        "instruction": (
            f"Headless run auto-cascaded to '{auto_cascaded_to}'. "
            f"To force a different model on resume: "
            f"GEMINI_MODEL=<name> /pdf-convert ..."
            if auto_cascaded_to
            else "Stdin/tty unavailable for interactive prompt. "
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


def _rpm_wait() -> None:
    """Sleep one rate-limit window (90s + 0–30s jitter) before retry."""
    secs = RPM_BACKOFF_BASE_SECS + random.uniform(0, RPM_BACKOFF_JITTER_SECS)
    print(
        f"[gemini_client] RPM transient — sleeping {secs:.0f}s before retry",
        flush=True,
    )
    time.sleep(secs)


def _verify_rpd_truly_exhausted(model: str) -> bool:
    """
    3 probes spaced 120s apart. Any single OK probe → not RPD, return False
    (caller treats as lingering RPM). All fail → RPD confirmed.
    """
    print(
        f"[gemini_client] verifying RPD for {model} — "
        f"{RPD_PROBE_COUNT} probes × {RPD_PROBE_INTERVAL_SECS}s",
        flush=True,
    )
    for i in range(RPD_PROBE_COUNT):
        if i > 0:
            time.sleep(RPD_PROBE_INTERVAL_SECS)
        if _probe_model_alive(model):
            print(
                f"[gemini_client]   probe {i+1}/{RPD_PROBE_COUNT}: OK — "
                f"not RPD, treating as lingering RPM",
                flush=True,
            )
            return False
        print(
            f"[gemini_client]   probe {i+1}/{RPD_PROBE_COUNT}: still exhausted",
            flush=True,
        )
    print(f"[gemini_client] RPD confirmed for {model}", flush=True)
    return True


def _cascade_within_pro_ladder(failing_model: str) -> str:
    """Pick next live Pro from _PRO_LADDER, excluding exhausted. '' if none."""
    for m in _PRO_LADDER:
        if m == failing_model:
            continue
        if m in _EXHAUSTED_MODELS:
            continue
        return m
    return ""


def _handle_quota_exhaustion(failing_model: str, stderr_msg: str) -> str:
    """
    Coordinate quota response across worker threads. Returns one of:
      "retry_same"  — caller backs off (already slept) and retries same model
      "retry_new"   — _RESOLVED_MODEL_CACHE updated; caller picks up new model
      (raises QuotaExhaustedError when all Pro candidates are exhausted)

    Classification:
      - rpm / ambiguous  → sleep and retry same model
      - rpd              → verify with 3-probe protocol; if confirmed,
                           cascade within _PRO_LADDER; else fall back to RPM
    Single-user / headless: no interactive TTY prompt — quality-first cascade
    is fully automatic within the Pro tier only, never down to Flash.
    """
    global _RESOLVED_MODEL_CACHE, _TERMINAL_QUOTA

    kind = classify_quota_error(stderr_msg)
    if kind in ("rpm", "ambiguous", "none"):
        # "none" only happens if caller passed a non-quota stderr by mistake;
        # safest bet is still RPM-style backoff rather than escalation.
        _rpm_wait()
        return "retry_same"

    # kind == "rpd" — coordinate cascade decision.
    with _SWITCH_LOCK:
        if _TERMINAL_QUOTA:
            raise QuotaExhaustedError("terminal quota state")

        current = _RESOLVED_MODEL_CACHE
        if current and failing_model and current != failing_model:
            # Another thread already cascaded; just pick up the new model.
            return "retry_new"

        if failing_model and failing_model in _EXHAUSTED_MODELS:
            # Another thread already marked this exhausted; cascade now.
            next_pro = _cascade_within_pro_ladder(failing_model)
            if not next_pro:
                _TERMINAL_QUOTA = True
                raise QuotaExhaustedError(
                    f"All Pro models exhausted: {sorted(_EXHAUSTED_MODELS)}. "
                    f"Workspace preserved — resume after quota reset."
                )
            _RESOLVED_MODEL_CACHE = next_pro
            return "retry_new"

        if not failing_model:
            # No model to verify — backoff and retry.
            _rpm_wait()
            return "retry_same"

        if not _verify_rpd_truly_exhausted(failing_model):
            # Lingering RPM after all — back off and retry.
            _rpm_wait()
            return "retry_same"

        _EXHAUSTED_MODELS.add(failing_model)
        next_pro = _cascade_within_pro_ladder(failing_model)
        workspace = _resolve_workspace_dir()
        if not next_pro:
            _TERMINAL_QUOTA = True
            if workspace:
                _write_quota_marker(
                    workspace=workspace,
                    exhausted=failing_model,
                    candidates=list(_PRO_LADDER),
                    auto_cascaded_to=None,
                )
            raise QuotaExhaustedError(
                f"All Pro models exhausted: {sorted(_EXHAUSTED_MODELS)}. "
                f"Workspace preserved — resume after quota reset."
            )

        print(
            f"[gemini_client] RPD cascade: {failing_model} → {next_pro} (Pro tier)",
            flush=True,
        )
        if workspace:
            _write_quota_marker(
                workspace=workspace,
                exhausted=failing_model,
                candidates=list(_PRO_LADDER),
                auto_cascaded_to=next_pro,
            )
        _RESOLVED_MODEL_CACHE = next_pro
        return "retry_new"


def call_gemini(
    prompt: str,
    image_path: Optional[str] = None,
    timeout: int = CALL_TIMEOUT_SECS,
) -> str:
    """
    Call `gemini -p <prompt> [-m <model>] --yolo --include-directories /tmp`.

    Quality-first quota handling:
      - Empty / short response → MAX_RETRIES attempts with prompt variation.
      - RPM (or ambiguous) quota error → backoff and retry SAME model, up to
        RPM_MAX_RETRIES times. Beyond that, escalate to RPD verification.
      - RPD confirmed → cascade within _PRO_LADDER (Pro tier only). When the
        ladder is exhausted, raise QuotaExhaustedError so caller can resume.

    Never auto-cascades Pro→Flash. Override model with GEMINI_MODEL env var.
    """
    short_attempt = 0
    rpm_retries = 0
    while True:
        # Append variation suffix on short-response retries to break repetition.
        effective_prompt = (
            prompt
            if short_attempt == 0
            else f"{prompt}\n\n[Retry {short_attempt}: ensure full ADE extraction]"
        )
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

            # Skip quota path on known transient vision/stream errors that lack
            # any explicit quota marker — those resolve with a plain retry.
            quota_hit = _is_quota_error(stderr) or _is_quota_error(response)
            if quota_hit and _is_transient_error(stderr) and not _is_quota_error(stderr):
                quota_hit = False

            if quota_hit:
                err_blob = (stderr.strip() or response.strip())[:500] or "quota exhausted"
                action = _handle_quota_exhaustion(active_model, err_blob)
                if action == "retry_same":
                    rpm_retries += 1
                    if rpm_retries > RPM_MAX_RETRIES:
                        # Escalate: too many RPM hits in a row likely mean RPD.
                        # Force the RPD branch by passing an RPD marker phrase.
                        action = _handle_quota_exhaustion(
                            active_model, "Daily quota exceeded (RPM retries exhausted)"
                        )
                        # Reset counter either way — RPD verify already waited
                        # ~6 minutes, so the next sample is a fresh window.
                        rpm_retries = 0
                    continue
                if action == "retry_new":
                    rpm_retries = 0
                    continue

            if len(response) >= MIN_RESPONSE_CHARS:
                return response

            reason = stderr.strip() or f"response too short ({len(response)} chars)"
            print(
                f"[gemini_client] attempt {short_attempt+1}/{MAX_RETRIES} failed: {reason}",
                flush=True,
            )

        except subprocess.TimeoutExpired:
            print(
                f"[gemini_client] attempt {short_attempt+1}/{MAX_RETRIES} "
                f"timed out after {timeout}s",
                flush=True,
            )
        except FileNotFoundError:
            raise RuntimeError("gemini CLI not found — ensure it is installed and in PATH")

        if short_attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF_SECS[short_attempt])
            short_attempt += 1
            continue
        raise RuntimeError(f"gemini call failed after {MAX_RETRIES} attempts")
