#!/usr/bin/env python3
"""
step2_gemini_refine.py — Per-page Gemini ADE refinement consuming Docling JSON + PNGs.

Calls gemini CLI per page with structured Docling data + PNG → writes ADE Markdown.
Concurrent calls capped at MAX_CONCURRENT (default 3) to respect rate limits.
Page-level caching: skips pages with existing valid output (resume capability).

Usage:
    python step2_gemini_refine.py <cache_json> <png_dir> <output_md_dir>
"""

import json
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gemini_client import call_gemini, QuotaExhaustedError

# OAuth (Ultra) accounts have effectively no daily cap — keep concurrency at 3.
# Lower to 1 if you're on a Free OAuth tier and need to stretch RPD.
MAX_CONCURRENT = int(os.environ.get("GEMINI_CONCURRENCY", "3"))
PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent / "ade_prompt_v2.txt"
VISION_PROMPT_PATH = Path(__file__).resolve().parent / "ade_prompt_vision.txt"
VISION_THRESHOLD = int(os.environ.get("DOCLING_SPARSE_THRESHOLD", "8"))
RETRY_MAX = 2
FAILURE_MARKER = "<!-- GEMINI EXTRACTION FAILED"


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


def _page_is_cached(out_path: Path) -> bool:
    """Check if page output exists and is valid (not a failure marker)."""
    if not out_path.exists():
        return False
    try:
        content = out_path.read_text(encoding="utf-8").strip()
        if content and FAILURE_MARKER not in content:
            return True
    except Exception:
        pass
    return False


def _process_page(
    page: dict,
    png_dir: Path,
    out_dir: Path,
    prompt_template: str,
    vision_template: str,
) -> tuple[int, str]:
    """Process a single page: check cache, call Gemini, write MD file. Returns (page_no, status)."""
    page_no = page.get("page_no", 0)
    out_path = out_dir / f"page_{page_no}.md"

    # Page-level cache: skip if already successfully processed
    if _page_is_cached(out_path):
        return page_no, "cached"

    trimmed = _trim_docling_page(page)
    is_sparse = len(trimmed["elements"]) + len(trimmed["tables"]) <= VISION_THRESHOLD

    if is_sparse:
        page_size = trimmed.get("size") or [0, 0]
        if len(page_size) < 2:
            page_size = [0, 0]
        prompt = vision_template.format(
            page_no=page_no,
            page_size=f"[{page_size[0]}, {page_size[1]}]"
        )
        n_elem, n_tbl = len(trimmed["elements"]), len(trimmed["tables"])
        print(f"[step2] page {page_no}: sparse ({n_elem} elements, {n_tbl} tables) → vision prompt", file=sys.stderr)
    else:
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
        out_path.write_text(response, encoding="utf-8")
        return page_no, "ok"
    except QuotaExhaustedError:
        # Do NOT write a failure marker — leave cache empty so resume re-tries this page
        # after quota resets. Propagate up so the executor stops submitting new work.
        raise
    except RuntimeError as e:
        print(f"[step2] page {page_no} FAILED: {e}", file=sys.stderr)
        out_path.write_text(f"<!-- GEMINI EXTRACTION FAILED page {page_no} -->", encoding="utf-8")
        return page_no, "failed"
    except Exception as e:
        print(f"[step2] page {page_no} UNEXPECTED ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        out_path.write_text(f"<!-- GEMINI EXTRACTION FAILED page {page_no} -->", encoding="utf-8")
        return page_no, "failed"


def _check_gemini_available() -> None:
    """Fail fast if gemini CLI is not installed."""
    import shutil
    if not shutil.which("gemini"):
        print("ERROR: gemini CLI not found — ensure it is installed and in PATH", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: step2_gemini_refine.py <cache_json> <png_dir> <output_md_dir>", file=sys.stderr)
        sys.exit(1)

    if os.environ.get("PDF_CONVERT_ALLOW_GEMINI_SUBPROCESS") != "1":
        print(
            "ERROR: step2_gemini_refine.py is disabled by default because it spawns "
            "`gemini -p` subprocess calls. /pdf-convert must use the active Gemini CLI "
            "model in the current slash-command turn. If you intentionally want the "
            "legacy subprocess path, rerun with PDF_CONVERT_ALLOW_GEMINI_SUBPROCESS=1.",
            file=sys.stderr,
        )
        sys.exit(64)

    _check_gemini_available()

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

    # Validate PNG coverage — warn if any page is missing its image
    if not (png_dir / ".skip").exists():
        rendered = {int(p.stem) for p in png_dir.glob("*.png")}
        page_nos = {p.get("page_no") for p in pages}
        missing = page_nos - rendered
        if missing:
            print(f"[step2] WARNING: {len(missing)} pages without PNG: {sorted(missing)}", file=sys.stderr)

    prompt_template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    vision_template = VISION_PROMPT_PATH.read_text(encoding="utf-8")

    # Phase 1: process all pages (cached ones skipped)
    print(f"[step2] processing {len(pages)} pages (concurrency={MAX_CONCURRENT})", file=sys.stderr)

    failed: list[int] = []
    cached_count = 0
    quota_hit = False

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
        futures = {
            pool.submit(_process_page, page, png_dir, out_dir, prompt_template, vision_template): page.get("page_no")
            for page in pages
        }
        for future in as_completed(futures):
            try:
                page_no, status = future.result()
            except QuotaExhaustedError as qe:
                quota_hit = True
                # Cancel still-pending futures; in-flight ones will finish naturally
                for f in futures:
                    f.cancel()
                print(
                    f"\n[step2] QUOTA EXHAUSTED — halting. Reason: {qe}\n"
                    f"[step2] Cache preserved at {out_dir}. Re-run after quota reset OR\n"
                    f"[step2]   set GEMINI_MODEL=gemini-flash-latest (much higher daily quota)\n"
                    f"[step2]   set GEMINI_CONCURRENCY=1 (default; raise only if quota allows)",
                    file=sys.stderr,
                )
                break
            except Exception as e:
                print(f"[step2] UNEXPECTED thread error: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            if status == "failed":
                failed.append(page_no)
            elif status == "cached":
                cached_count += 1
            else:
                print(f"[step2] page {page_no} ✓", file=sys.stderr, end="\r")

    if quota_hit:
        sys.exit(2)

    print(f"\n[step2] phase 1 done — {len(pages) - len(failed)}/{len(pages)} ok ({cached_count} cached)", file=sys.stderr)

    # Phase 2: retry failed pages
    for retry in range(RETRY_MAX):
        if not failed:
            break
        print(f"[step2] retry {retry+1}/{RETRY_MAX} for {len(failed)} failed pages: {sorted(failed)}", file=sys.stderr)
        retry_pages = [p for p in pages if p.get("page_no") in failed]
        retry_failed: list[int] = []

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
            futures = {
                pool.submit(_process_page, page, png_dir, out_dir, prompt_template, vision_template): page.get("page_no")
                for page in retry_pages
            }
            for future in as_completed(futures):
                try:
                    page_no, status = future.result()
                except QuotaExhaustedError as qe:
                    for f in futures:
                        f.cancel()
                    print(f"\n[step2] QUOTA EXHAUSTED during retry — halting. {qe}", file=sys.stderr)
                    sys.exit(2)
                except Exception:
                    continue
                if status == "failed":
                    retry_failed.append(page_no)
                else:
                    print(f"[step2] page {page_no} ✓ (retry {retry+1})", file=sys.stderr)
        failed = retry_failed

    # Final summary
    if failed:
        print(f"[step2] FAILED pages after {RETRY_MAX} retries: {sorted(failed)}", file=sys.stderr)
        # Don't sys.exit(1) — let pipeline continue with partial results
    else:
        print(f"[step2] all {len(pages)} pages processed successfully", file=sys.stderr)

    print(str(out_dir))


if __name__ == "__main__":
    main()
