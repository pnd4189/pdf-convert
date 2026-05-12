#!/usr/bin/env python3
"""
step1_7_epub_route.py — EPUB chapter fast-path routing.

Reads Docling cache JSON, classifies pages as text-only vs media-bearing,
writes text-only pages directly to temp_md (bypassing Gemini step2), and
writes a filtered cache JSON containing only media pages for step2 Gemini.

Usage:
    python step1_7_epub_route.py <cache_json> <temp_md_dir> <temp_base_dir>

Output (stdout): tab-separated line:
    text_pages=N\tmedia_pages=M\tmedia_cache=<path>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.epub_router import (
    build_docling_markdown_for_page,
    split_pages_by_route,
)


def main() -> None:
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <cache_json> <temp_md_dir> <temp_base_dir>", file=sys.stderr)
        sys.exit(1)

    cache_path = Path(sys.argv[1])
    temp_md = Path(sys.argv[2])
    temp_base = Path(sys.argv[3])

    if not cache_path.exists():
        print(f"ERROR: cache file not found: {cache_path}", file=sys.stderr)
        sys.exit(1)

    with open(cache_path, encoding="utf-8") as f:
        cache_data = json.load(f)

    text_pages, media_pages = split_pages_by_route(cache_data)

    temp_md.mkdir(parents=True, exist_ok=True)

    # Write text-only pages directly to temp_md (skip Gemini)
    for page in text_pages:
        page_no = page.get("page_no", 0)
        md_content = build_docling_markdown_for_page(page)
        out_file = temp_md / f"page_{page_no}.md"
        out_file.write_text(md_content, encoding="utf-8")
        print(f"[epub_route] text-only page {page_no} → {out_file.name}", file=sys.stderr)

    # Write filtered cache for media pages only
    media_cache = dict(cache_data)
    media_cache["pages"] = media_pages
    media_cache_path = temp_base / "epub_media_cache.json"
    with open(media_cache_path, "w", encoding="utf-8") as f:
        json.dump(media_cache, f, ensure_ascii=False)

    print(f"[epub_route] text={len(text_pages)} media={len(media_pages)} → {media_cache_path}", file=sys.stderr)

    # Machine-parseable output on stdout
    print(f"text_pages={len(text_pages)}\tmedia_pages={len(media_pages)}\tmedia_cache={media_cache_path}")


if __name__ == "__main__":
    main()
