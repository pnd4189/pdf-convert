#!/usr/bin/env python3
"""
step2_gemini_refine.py — Per-page Gemini ADE refinement consuming Docling JSON + PNGs.

Calls gemini CLI per page with structured Docling data + PNG → writes ADE Markdown.
Concurrent calls capped at MAX_CONCURRENT (default 3) to respect rate limits.

Usage:
    python step2_gemini_refine.py <cache_json> <png_dir> <output_md_dir>
"""

import json
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gemini_client import call_gemini

MAX_CONCURRENT = 3
PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent / "ade_prompt_v2.txt"


def _trim_docling_page(page: dict) -> dict:
    """Keep only text + table cells; drop full bboxes to reduce token count."""
    trimmed_elements = [
        {"type": e.get("type", ""), "text": e.get("text", ""), "bbox": e.get("bbox")}
        for e in page.get("elements", [])
        if e.get("text", "").strip()
    ]
    trimmed_tables = []
    for t in page.get("tables", []):
        trimmed_tables.append({
            "cells": [
                {"row": c.get("row", 0), "col": c.get("col", 0),
                 "text": c.get("text", ""), "row_span": c.get("row_span", 1),
                 "col_span": c.get("col_span", 1)}
                for c in t.get("cells", [])
            ]
        })
    return {
        "page_no": page.get("page_no", 0),
        "size": page.get("size", [0, 0]),
        "elements": trimmed_elements,
        "tables": trimmed_tables,
    }


def _process_page(
    page: dict,
    png_dir: Path,
    out_dir: Path,
    prompt_template: str,
) -> tuple[int, str]:
    """Process a single page: call Gemini, write MD file. Returns (page_no, status)."""
    page_no = page.get("page_no", 0)
    trimmed = _trim_docling_page(page)
    docling_json = json.dumps(trimmed, ensure_ascii=False)

    prompt = prompt_template.format(page_no=page_no, docling_data=docling_json)

    # Use 4-digit zero-padded PNG filename
    png_path = png_dir / f"{page_no:04d}.png"
    image_arg = str(png_path) if png_path.exists() else None

    # Skip rendering for text-only formats (signaled by .skip marker)
    if (png_dir / ".skip").exists():
        image_arg = None

    try:
        response = call_gemini(prompt, image_path=image_arg)
        out_path = out_dir / f"page_{page_no}.md"
        out_path.write_text(response, encoding="utf-8")
        return page_no, "ok"
    except RuntimeError as e:
        print(f"[step2] page {page_no} FAILED: {e}", file=sys.stderr)
        # Write empty marker so QA sweep can flag it
        out_path = out_dir / f"page_{page_no}.md"
        out_path.write_text(f"<!-- GEMINI EXTRACTION FAILED page {page_no} -->", encoding="utf-8")
        return page_no, "failed"


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: step2_gemini_refine.py <cache_json> <png_dir> <output_md_dir>", file=sys.stderr)
        sys.exit(1)

    cache_json_path = sys.argv[1]
    png_dir = Path(sys.argv[2])
    out_dir = Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(cache_json_path, "r", encoding="utf-8") as f:
        cache_data = json.load(f)

    pages = cache_data.get("pages", [])
    if not pages:
        print("[step2] no pages in cache JSON", file=sys.stderr)
        sys.exit(1)

    prompt_template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    print(f"[step2] processing {len(pages)} pages (concurrency={MAX_CONCURRENT})", file=sys.stderr)

    failed = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
        futures = {
            pool.submit(_process_page, page, png_dir, out_dir, prompt_template): page.get("page_no")
            for page in pages
        }
        for future in as_completed(futures):
            page_no, status = future.result()
            if status == "failed":
                failed.append(page_no)
            else:
                print(f"[step2] page {page_no} ✓", file=sys.stderr, end="\r")

    print(f"\n[step2] done — {len(pages) - len(failed)}/{len(pages)} ok", file=sys.stderr)
    if failed:
        print(f"[step2] FAILED pages: {sorted(failed)}", file=sys.stderr)
        sys.exit(1)

    print(str(out_dir))


if __name__ == "__main__":
    main()
