#!/usr/bin/env python3
"""
force_accept_pages.py — Rewrite stuck markdown pages with QA_WARNING markers
so step3_merge can produce a valid output despite unresolved QA criticals.

Called by the driver after the auto-repair loop gives up. Receives a list of
page filenames (e.g. page_71.md page_78.md) and a "reasons" string describing
the unresolved checks. Each target file is rewritten via the sanitizer's
force_accept_stuck_page helper. The QA sweep will then treat these as soft
(warning) instead of hard critical.

Usage:
    python3 force_accept_pages.py --md-dir <dir> --png-dir <dir> --reasons "<text>" \
        page_71.md page_78.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.md_sanitizer import force_accept_stuck_page


def _page_num(fname: str) -> int:
    m = re.search(r"page_(\d+)\.md", fname)
    return int(m.group(1)) if m else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--md-dir", required=True)
    parser.add_argument("--png-dir", default="")
    parser.add_argument("--reasons", default="stuck after retries")
    parser.add_argument("files", nargs="+", help="page_N.md filenames to force-accept")
    args = parser.parse_args()

    md_dir = Path(args.md_dir)
    png_dir = Path(args.png_dir) if args.png_dir else None
    reasons = [r.strip() for r in args.reasons.split("|") if r.strip()]

    for fname in args.files:
        path = md_dir / Path(fname).name
        page_no = _page_num(fname)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        png_path = None
        if png_dir:
            candidate = png_dir / f"{page_no:04d}.png"
            if candidate.exists():
                png_path = str(candidate)
        rewritten = force_accept_stuck_page(existing, page_no, reasons, png_path=png_path)
        path.write_text(rewritten, encoding="utf-8")
        print(f"[force_accept] marked {fname} as QA_WARNING (reasons: {reasons})", file=sys.stderr)


if __name__ == "__main__":
    main()
