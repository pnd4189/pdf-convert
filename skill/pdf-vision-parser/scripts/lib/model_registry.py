#!/usr/bin/env python3
"""
model_registry.py — Discover Gemini models the user has actually invoked.

We never fabricate a model list. We scan the user's Gemini CLI session logs
(~/.gemini/tmp/<project>/chats/*.jsonl) and extract every distinct model id
that appears — those are demonstrably available to this OAuth account.

Ordered most-recently-used first so prompts surface familiar choices on top.
"""

import os
import re
from pathlib import Path
from typing import List

GEMINI_HOME = Path(os.environ.get("GEMINI_HOME", str(Path.home() / ".gemini")))
_MODEL_PATTERN = re.compile(r'"model"\s*:\s*"(gemini-[A-Za-z0-9.\-]+)"')


def discover_used_models() -> List[str]:
    """Return distinct gemini-* model ids found in CLI session logs, recent first."""
    tmp = GEMINI_HOME / "tmp"
    if not tmp.exists():
        return []

    files: list[tuple[float, Path]] = []
    for pattern in ("*/chats/*.jsonl", "*/chats/*.json"):
        for f in tmp.glob(pattern):
            try:
                files.append((f.stat().st_mtime, f))
            except OSError:
                continue
    files.sort(reverse=True)

    ordered: list[str] = []
    for _, path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for model_id in _MODEL_PATTERN.findall(content):
            if model_id not in ordered:
                ordered.append(model_id)
    return ordered


if __name__ == "__main__":
    for m in discover_used_models():
        print(m)
