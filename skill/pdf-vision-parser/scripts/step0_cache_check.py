#!/usr/bin/env python3
"""
step0_cache_check.py — Check if input file has a cached Docling parse result.

Usage:
    python step0_cache_check.py <input_file>

Output (JSON to stdout):
    {"cached": true,  "path": "/path/to/{key}.json", "key": "..."}
    {"cached": false, "path": "/path/to/{key}.json", "key": "..."}
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.cache_utils import make_cache_key, cache_entry_path, cache_hit, lru_evict


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: step0_cache_check.py <input_file>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    if not Path(input_path).exists():
        print(f"ERROR: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Evict stale cache entries before checking
    lru_evict()

    key = make_cache_key(input_path)
    path = cache_entry_path(key)
    hit = cache_hit(key)

    result = {"cached": hit, "path": str(path), "key": key}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
