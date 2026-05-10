#!/usr/bin/env python3
"""
gemini_client.py — Subprocess wrapper for `gemini -p` with retry and timeout handling.

Retries on empty/short responses (< MIN_RESPONSE_CHARS chars) up to MAX_RETRIES times
with a slightly varied prompt suffix to break repetition.
"""

import subprocess
import time
from pathlib import Path
from typing import Optional

MIN_RESPONSE_CHARS = 50
MAX_RETRIES = 3
CALL_TIMEOUT_SECS = 120
RETRY_BACKOFF_SECS = [2, 5, 10]


def call_gemini(
    prompt: str,
    image_path: Optional[str] = None,
    timeout: int = CALL_TIMEOUT_SECS,
) -> str:
    """
    Call `gemini -p <prompt> [--image <path>] --yolo` via subprocess.
    Returns response text or raises RuntimeError after MAX_RETRIES failures.
    """
    for attempt in range(MAX_RETRIES):
        # Append variation suffix on retries to avoid repeated empty responses
        effective_prompt = prompt if attempt == 0 else f"{prompt}\n\n[Retry {attempt}: ensure full ADE extraction]"

        cmd = ["gemini", "-p", effective_prompt, "--yolo"]
        if image_path and Path(image_path).exists():
            cmd += ["--image", image_path]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            response = proc.stdout.strip()

            if len(response) >= MIN_RESPONSE_CHARS:
                return response

            reason = proc.stderr.strip() or f"response too short ({len(response)} chars)"
            print(f"[gemini_client] attempt {attempt+1}/{MAX_RETRIES} failed: {reason}", flush=True)

        except subprocess.TimeoutExpired:
            print(f"[gemini_client] attempt {attempt+1}/{MAX_RETRIES} timed out after {timeout}s", flush=True)
        except FileNotFoundError:
            raise RuntimeError("gemini CLI not found — ensure it is installed and in PATH")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF_SECS[attempt])

    raise RuntimeError(f"gemini call failed after {MAX_RETRIES} attempts")
