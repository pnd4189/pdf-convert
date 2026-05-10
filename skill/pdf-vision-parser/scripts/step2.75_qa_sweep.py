#!/usr/bin/env python3
"""
step2.75_qa_sweep.py — Final QA Sweep (Landing.AI ADE Standard)

Checks:
  1. Anchor IDs + Normalized box coordinates (0.00-1.00)
  2. Markdown table ban (must use HTML <table>)
  3. Cell-level Grounding (<table>, <td>, <th> must have id)

Exit codes: 0 = PASS, 1 = CRITICAL found
"""

import argparse
import os
import re
import sys

# Regex chuẩn Landing.AI
ANCHOR_RE = re.compile(
    r"""<a\s+id\s*=\s*['"](\d+-\d+)['"]\s*(?:box\s*=\s*['"]([^'"]+)['"])?\s*>\s*</a>""",
    re.IGNORECASE,
)

COORD_NORMALIZED_RE = re.compile(
    r"^\s*\[\s*(0(\.\d+)?|1(\.0+)?)\s*,\s*(0(\.\d+)?|1(\.0+)?)\s*,"
    r"\s*(0(\.\d+)?|1(\.0+)?)\s*,\s*(0(\.\d+)?|1(\.0+)?)\s*\]\s*$"
)

MD_TABLE_RE = re.compile(r"\|[\s-]*-{3,}[\s-]*\|")
TABLE_HTML_RE = re.compile(r"<table[^>]*>", re.IGNORECASE)
TABLE_ID_RE = re.compile(r"<table[^>]+id\s*=\s*['\"]\d+-\d+['\"]", re.IGNORECASE)
TD_TAG_RE = re.compile(r"<t[dh][^>]*>", re.IGNORECASE)
TD_WITH_ID_RE = re.compile(r"<t[dh][^>]*id\s*=\s*['\"]\d+-\d+['\"][^>]*>", re.IGNORECASE)
BLANK_PAGE_RE = re.compile(r"<!--\s*TRANG TRỐNG\s*-\s*ĐÃ XÁC MINH\s*-->")


def page_num(fname: str) -> int:
    return int(fname.replace("page_", "").replace(".md", ""))


def run_qa(md_dir):
    if not os.path.isdir(md_dir):
        sys.exit(0)

    files = sorted(
        [f for f in os.listdir(md_dir) if f.endswith(".md")],
        key=page_num,
    )
    critical = 0

    print("\n" + "=" * 50 + "\n  🚀 LANDING.AI - ADE QA SWEEP\n" + "=" * 50)

    for fname in files:
        with open(os.path.join(md_dir, fname), "r", encoding="utf-8") as f:
            content = f.read()
        if BLANK_PAGE_RE.search(content):
            continue

        issues = []

        # Check 1: Anchor + Normalized Coordinates
        anchors = ANCHOR_RE.findall(content)
        if not anchors:
            issues.append("[CRITICAL] Thiếu hoàn toàn thẻ neo <a id='X-Y'>")
        for a_id, box in anchors:
            if not box:
                issues.append(
                    f"[CRITICAL] Chunk '{a_id}' thiếu thuộc tính "
                    f"box='[left, top, right, bottom]'"
                )
            elif not COORD_NORMALIZED_RE.match(box):
                issues.append(
                    f"[CRITICAL] Chunk '{a_id}' box sai. "
                    f"Bắt buộc Float 0.00-1.00 (VD: [0.12, 0.25, 0.9, 0.3])"
                )

        # Check 2: Markdown table ban
        if MD_TABLE_RE.search(content):
            issues.append(
                "[CRITICAL] Dùng bảng Markdown |---| "
                "(Bắt buộc dùng HTML <table>)"
            )

        # Check 3: Cell-Level Grounding
        if TABLE_HTML_RE.search(content):
            tables = TABLE_HTML_RE.findall(content)
            tables_with_id = TABLE_ID_RE.findall(content)
            if len(tables) > len(tables_with_id):
                issues.append(
                    "[CRITICAL] Có thẻ <table> bị thiếu thuộc tính 'id'"
                )
            tds = len(TD_TAG_RE.findall(content))
            tds_with_id = len(TD_WITH_ID_RE.findall(content))
            if tds > tds_with_id:
                issues.append(
                    f"[CRITICAL] Bảng có {tds} ô dữ liệu, "
                    f"nhưng chỉ {tds_with_id} ô có 'id'. "
                    f"(Vi phạm Cell-level Grounding)"
                )

        if issues:
            print(f"📄 {fname}:")
            for issue in issues:
                print(f"   - {issue}")
            critical += len([i for i in issues if "CRITICAL" in i])

    print("-" * 50)
    if critical > 0:
        print(
            f"  🔴 TỔNG KẾT: CÓ {critical} LỖI CRITICAL. "
            f"Yêu cầu AI mở file sửa lại ngay!"
        )
        sys.exit(1)
    else:
        print(
            "  ✅ 100% PASS. Cấu trúc bảng và Tọa độ đạt chuẩn Enterprise!"
        )
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--md-dir", default=None)
    args = parser.parse_args()
    md_dir = args.md_dir or os.path.join(
        os.getcwd(), ".agents", "temp", "temp_md"
    )
    run_qa(md_dir)
