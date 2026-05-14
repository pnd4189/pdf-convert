#!/usr/bin/env python3
"""
step4_quality_report.py — Post-conversion quality summary.

Reads the merged markdown directory + final JSON and produces:
  - Stderr summary (Vietnamese, user-facing): total pages, ok/blank/warned/missing
    counts, and per-warned-page reasons + recommendations.
  - JSON sidecar saved next to the output JSON: <name>.quality.json.

The goal: even when 1-2 pages are stuck (e.g. blurry scans), the user gets
the full output AND a clear report of which pages need manual review.

Usage:
    python3 step4_quality_report.py \
        --md-dir <temp_md> \
        --manifest <native_manifest.json> \
        --output-json <final.json>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.md_sanitizer import extract_qa_warnings, QA_WARNING_PREFIX

BLANK_PAGE_RE = re.compile(r"<!--\s*TRANG TRỐNG\s*-\s*ĐÃ XÁC MINH\s*-->")
FAILURE_MARKER_RE = re.compile(r"<!--\s*GEMINI EXTRACTION FAILED", re.IGNORECASE)
ANCHOR_RE = re.compile(r"<a\s+id\s*=\s*['\"]\d+-\d+['\"]", re.IGNORECASE)


def _page_num(fname: str) -> int:
    return int(fname.replace("page_", "").replace(".md", ""))


def _load_manifest(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _recommendation(reasons: list[str]) -> str:
    text = " ".join(reasons).lower()
    if "vision" in text or "extraction failed" in text or "stuck" in text:
        return (
            "Trang scan mờ hoặc Gemini liên tục timeout. Khuyến nghị: "
            "(1) chụp lại trang gốc rõ nét hơn và chạy /pdf-convert riêng cho trang đó, "
            "(2) tăng DPI bằng cách re-render thủ công ở 450-600 DPI, hoặc "
            "(3) chấp nhận output hiện tại và bổ sung trang này thủ công."
        )
    if "ontology" in text or "figure" in text:
        return (
            "Mô tả hình ảnh quá chung chung. Khuyến nghị mở file .md và viết lại "
            "đoạn `<:: ... : figure ::>` bằng tiếng Việt với chi tiết cấu trúc."
        )
    if "box" in text or "tọa độ" in text or "coordinate" in text:
        return (
            "Tọa độ chunk không hợp lệ. Driver đã chuẩn hoá tự động; nếu vẫn báo lỗi "
            "khuyến nghị chạy lại /pdf-convert (cache-aware, không tốn quota cho trang đã ok)."
        )
    return "Mở file .md tương ứng và rà soát thủ công."


def _scan_pages(md_dir: Path) -> dict:
    pages_ok: list[int] = []
    pages_blank: list[int] = []
    pages_warned: list[dict] = []
    pages_failed: list[int] = []
    pages_empty: list[int] = []

    files = sorted(
        [f for f in os.listdir(md_dir) if f.startswith("page_") and f.endswith(".md")],
        key=_page_num,
    )
    for fname in files:
        path = md_dir / fname
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            pages_failed.append(_page_num(fname))
            continue

        pnum = _page_num(fname)
        stripped = content.strip()

        if BLANK_PAGE_RE.search(content):
            pages_blank.append(pnum)
            continue
        if FAILURE_MARKER_RE.search(content):
            pages_failed.append(pnum)
            continue
        if not stripped:
            pages_empty.append(pnum)
            continue

        warnings = extract_qa_warnings(content)
        if warnings:
            pages_warned.append({
                "page": pnum,
                "reasons": warnings,
                "recommendation": _recommendation(warnings),
                "has_anchors": bool(ANCHOR_RE.search(content)),
            })
            continue

        pages_ok.append(pnum)

    return {
        "files_scanned": len(files),
        "ok": pages_ok,
        "blank": pages_blank,
        "warned": pages_warned,
        "failed": pages_failed,
        "empty": pages_empty,
    }


def _quality_score(stats: dict, expected: int) -> tuple[float, str]:
    if expected <= 0:
        return 0.0, "unknown"
    good = len(stats["ok"]) + len(stats["blank"])
    pct = round(100.0 * good / expected, 1)
    if pct >= 99:
        label = "Excellent"
    elif pct >= 95:
        label = "Good"
    elif pct >= 85:
        label = "Acceptable"
    else:
        label = "Poor"
    return pct, label


def _print_report(stats: dict, expected: int, output_json: str | None) -> None:
    pct, label = _quality_score(stats, expected)
    bar = "=" * 60
    print(f"\n{bar}", file=sys.stderr)
    print("  📊 PDF-CONVERT — BÁO CÁO CHẤT LƯỢNG", file=sys.stderr)
    print(bar, file=sys.stderr)
    print(f"  • Tổng số trang dự kiến      : {expected}", file=sys.stderr)
    print(f"  • Trang OK (có nội dung)     : {len(stats['ok'])}", file=sys.stderr)
    print(f"  • Trang TRỐNG (đã xác minh) : {len(stats['blank'])}", file=sys.stderr)
    print(f"  • Trang có CẢNH BÁO         : {len(stats['warned'])}", file=sys.stderr)
    print(f"  • Trang FAILED extraction   : {len(stats['failed'])}", file=sys.stderr)
    print(f"  • Trang rỗng bất thường      : {len(stats['empty'])}", file=sys.stderr)
    print(f"  • Chất lượng tổng thể        : {pct}%  ({label})", file=sys.stderr)

    if stats["warned"]:
        print("\n  ⚠️  TRANG CẦN NGƯỜI DÙNG XEM LẠI:", file=sys.stderr)
        for entry in stats["warned"]:
            reasons = "; ".join(entry["reasons"]) or "(không có chi tiết)"
            print(f"   - page {entry['page']}: {reasons}", file=sys.stderr)
            print(f"     ↳ Khuyến nghị: {entry['recommendation']}", file=sys.stderr)

    if stats["failed"]:
        print(f"\n  ❌ TRANG FAILED: {stats['failed']}", file=sys.stderr)
        print("     (Gemini bóc tách thất bại sau retries. Xem khuyến nghị mục WARN.)",
              file=sys.stderr)

    if stats["empty"]:
        print(f"\n  ⚠️  TRANG RỖNG BẤT THƯỜNG: {stats['empty']}", file=sys.stderr)

    if output_json:
        print(f"\n  📄 Output JSON: {output_json}", file=sys.stderr)
    print(bar + "\n", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--md-dir", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--output-json", default=None,
                        help="Path of the final ADE JSON (used to derive sidecar path)")
    args = parser.parse_args()

    md_dir = Path(args.md_dir)
    if not md_dir.is_dir():
        print(f"[step4] md_dir not found: {md_dir}", file=sys.stderr)
        sys.exit(0)

    manifest = _load_manifest(args.manifest)
    expected = manifest.get("page_count") or len(manifest.get("pages", []) or []) or 0

    stats = _scan_pages(md_dir)
    if expected == 0:
        expected = stats["files_scanned"]

    pct, label = _quality_score(stats, expected)
    _print_report(stats, expected, args.output_json)

    sidecar = {
        "output_json": args.output_json,
        "expected_pages": expected,
        "files_scanned": stats["files_scanned"],
        "pages_ok": len(stats["ok"]),
        "pages_blank": len(stats["blank"]),
        "pages_warned": len(stats["warned"]),
        "pages_failed": len(stats["failed"]),
        "pages_empty": len(stats["empty"]),
        "quality_pct": pct,
        "quality_label": label,
        "warned_details": stats["warned"],
        "failed_pages": stats["failed"],
        "empty_pages": stats["empty"],
    }

    if args.output_json:
        sidecar_path = Path(args.output_json).with_suffix(".quality.json")
        try:
            sidecar_path.write_text(
                json.dumps(sidecar, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[step4] quality sidecar: {sidecar_path}", file=sys.stderr)
        except Exception as exc:
            print(f"[step4] WARNING: cannot write sidecar: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
