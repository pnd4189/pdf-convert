#!/usr/bin/env python3
"""
cache_utils.py — SHA-256 cache key, atomic write, LRU eviction for Docling parse cache.
Cache dir: scripts/.cache/docling/
Cache key: sha256(file_bytes) + "_" + docling_version (invalidates on upgrade)
"""

import hashlib
import json
import os
from importlib.metadata import version as _pkg_version
from pathlib import Path

DOCLING_VERSION = _pkg_version("docling")
CACHE_MAX_BYTES = 5 * 1024 ** 3  # 5 GB LRU cap


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def cache_dir() -> Path:
    d = _scripts_dir() / ".cache" / "docling"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_cache_key(file_path: str) -> str:
    return f"{sha256_file(file_path)}_{DOCLING_VERSION}"


def cache_entry_path(key: str) -> Path:
    return cache_dir() / f"{key}.json"


def cache_hit(key: str) -> bool:
    p = cache_entry_path(key)
    if not p.exists():
        return False
    # Verify JSON is parseable (guards against corrupt partial writes)
    try:
        with open(p, "r", encoding="utf-8") as f:
            json.load(f)
        return True
    except Exception:
        p.unlink(missing_ok=True)
        return False


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: write to .tmp then rename to avoid partial reads."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def lru_evict() -> None:
    """Remove oldest cache entries until total size < CACHE_MAX_BYTES."""
    d = cache_dir()
    entries = sorted(
        [p for p in d.glob("*.json")],
        key=lambda p: p.stat().st_atime
    )
    total = sum(p.stat().st_size for p in entries)
    for p in entries:
        if total <= CACHE_MAX_BYTES:
            break
        size = p.stat().st_size
        p.unlink(missing_ok=True)
        total -= size
