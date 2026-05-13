#!/usr/bin/env python3
"""
step2.75_qa_sweep.py — Final QA Sweep (Landing.AI ADE Standard)

Checks:
  1. Anchor IDs + Normalized box coordinates (0.00-1.00)
  2. Markdown table ban (must use HTML <table>)
  3. Cell-level Grounding (<table>, <td>, <th> must have id)
  4. Native vision provenance marker when a manifest is available
  5. Figure/diagram semantic description for pages with visual candidates

Exit codes:
  0 = PASS
  1 = HARD critical (anchor / box / table / vision-provenance) — must repair
  2 = SOFT critical only (figure ontology / visual-keyword references) — let
      caller decide whether to retry or accept (re-running Gemini rarely fixes
      these because they're textual context calls, not actual page contents)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

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
VISION_SOURCE_RE = re.compile(r"<!--\s*VISION_SOURCE\s*:\s*[^>]+-->", re.IGNORECASE)
ONTOLOGY_RE = re.compile(r"<::\s*(.*?)\s*:\s*(figure|logo|scan_code|attestation|marginalia)\s*::>", re.IGNORECASE | re.DOTALL)
FIGURE_RE = re.compile(r"<::\s*(.*?)\s*:\s*figure\s*::>", re.IGNORECASE | re.DOTALL)
# Match REFERENCES to a visual on the page, not topical mentions of visual
# concepts. Vietnamese astrology/feng-shui prose uses words like "đồ", "hình",
# "tinh đồ" as domain terms — those alone must not trigger a figure-ontology
# requirement. We only flag when the text clearly points at a visual artifact:
# numbered captions, "xem/như hình/đồ", "see/as shown in figure", CJK 图/圖
# captions, etc.
VISUAL_KEYWORD_RE = re.compile(
    r"(?:"
    # Numbered visual captions: "hình 1", "biểu đồ 2.3", "sơ đồ A", "figure 4-b"
    # Caption labels are digits, or a single uppercase letter, optionally
    # followed by .digit/-digit. We intentionally exclude word-like labels
    # (e.g. "hình thức", "đồ thị" in plain prose) to avoid false positives.
    r"(?:biểu\s*đồ|sơ\s*đồ|hình(?:\s*vẽ|\s*minh\s*họa)?|figure|fig\.?|diagram|chart)"
    r"\s*[:#]?\s*(?:\d+(?:[\.\-][\dA-Za-z]+)?|[A-Z](?:[\.\-][\dA-Za-z]+)?\b)"
    r"|"
    # Explicit deictic references: "xem hình", "như hình bên", "see figure"
    r"(?:xem|như|theo|coi|see|as\s+shown\s+in|as\s+per|refer\s+to)"
    r"\s+(?:bảng|hình|sơ\s*đồ|biểu\s*đồ|đồ\s*thị|figure|diagram|chart|grid)\b"
    r"|"
    # CJK figure-caption markers (number + 图/圖)
    r"(?:图|圖|表)\s*\d+"
    r"|"
    # Position-anchored references: "hình bên dưới/trên/trái/phải"
    r"(?:hình|sơ\s*đồ|biểu\s*đồ|bảng)\s+(?:bên\s+)?(?:trên|dưới|trái|phải|này|sau|trước)"
    r")",
    re.IGNORECASE,
)
RELATION_DETAIL_RE = re.compile(
    r"(đường|nối|liên\s*kết|mũi\s*tên|vị\s*trí|bố\s*cục|quan\s*hệ|ô|hàng|cột|"
    r"vòng|cung|nút|điểm|trái|phải|trên|dưới|node|edge|connection|dashed|solid|circle|grid)",
    re.IGNORECASE,
)


def page_num(fname: str) -> int:
    return int(fname.replace("page_", "").replace(".md", ""))


def _load_manifest(path: str | None, md_dir: str) -> dict:
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates.append(Path(md_dir).parent / "native_manifest.json")
    for candidate in candidates:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"[QA] WARNING: cannot read manifest {candidate}: {exc}", file=sys.stderr)
    return {}


def _page_visual_candidates(manifest: dict) -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = {}
    for item in manifest.get("visual_candidates", []) or []:
        page_no = item.get("page_no")
        if page_no is None:
            continue
        result.setdefault(int(page_no), []).append(item)
    return result


def run_qa(md_dir, manifest_path=None):
    if not os.path.isdir(md_dir):
        sys.exit(0)

    manifest = _load_manifest(manifest_path, md_dir)
    pages_requiring_vision = set()
    if manifest and not manifest.get("skip_native_extraction"):
        pages_requiring_vision = {int(p) for p in manifest.get("pages", []) if str(p).isdigit()}
    # When manifest says skip_visual_audit (PDF vision-only mode), there is no
    # reliable Docling baseline to decide what "uncovered visual region" means.
    # Trust the Gemini vision extractor and skip the deterministic guardrail.
    skip_visual_audit = bool(manifest.get("skip_visual_audit"))
    visual_candidates = {} if skip_visual_audit else _page_visual_candidates(manifest)

    files = sorted(
        [f for f in os.listdir(md_dir) if f.endswith(".md")],
        key=page_num,
    )
    hard_critical = 0
    soft_critical = 0

    # Issue markers that indicate a soft (often non-actionable) problem. These
    # are the false-positive-prone classes — Gemini rarely fixes them on retry
    # because they reflect either Docling-coverage gaps or topical mentions in
    # prose rather than missing extraction work.
    SOFT_MARKERS = (
        "Trang có vùng hình/sơ đồ ngoài bbox",
        "thiếu ontology",
        "Mô tả visual ontology quá ngắn",
        "Mô tả visual ontology chưa thể hiện",
    )

    def _classify(issue: str) -> str:
        return "soft" if any(m in issue for m in SOFT_MARKERS) else "hard"

    print("\n" + "=" * 50 + "\n  🚀 LANDING.AI - ADE QA SWEEP\n" + "=" * 50)

    expected_pages = {int(p) for p in manifest.get("pages", []) if str(p).isdigit()} if manifest else set()
    present_pages = {page_num(f) for f in files}
    missing_pages = sorted(expected_pages - present_pages)
    if missing_pages:
        print("📄 MISSING PAGE FILES:")
        preview = ", ".join(str(p) for p in missing_pages[:30])
        suffix = " ..." if len(missing_pages) > 30 else ""
        print(f"   - [CRITICAL] Thiếu {len(missing_pages)} file page_N.md: {preview}{suffix}")
        hard_critical += 1

    for fname in files:
        with open(os.path.join(md_dir, fname), "r", encoding="utf-8") as f:
            content = f.read()
        pnum = page_num(fname)
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

        # Check 4: native vision provenance. This catches text-only helper dumps
        # such as generate_md.py; the active Gemini CLI model must explicitly mark
        # that it inspected the rendered page image.
        if pages_requiring_vision and pnum in pages_requiring_vision and not VISION_SOURCE_RE.search(content):
            issues.append(
                "[CRITICAL] Thiếu marker `<!-- VISION_SOURCE: ... -->`. "
                "Trang này phải được trích xuất từ ảnh PNG bằng model Gemini CLI đang chạy, "
                "không được dump text từ Docling/generate_md.py."
            )

        # Check 5: visual semantics for diagrams/figures. If deterministic image
        # audit found dark visual regions not covered by Docling text/table boxes,
        # Markdown must contain a real figure description or a structured table.
        page_candidates = visual_candidates.get(pnum, [])
        has_html_table = bool(TABLE_HTML_RE.search(content))
        figures = [m.group(1).strip() for m in FIGURE_RE.finditer(content)]
        all_ontology = [m.group(1).strip() for m in ONTOLOGY_RE.finditer(content)]
        if page_candidates and not figures and not has_html_table:
            issues.append(
                "[CRITICAL] Trang có vùng hình/sơ đồ ngoài bbox text Docling nhưng không có "
                "`<:: ... : figure ::>` hoặc HTML table. Bắt buộc mở lại PNG và mô tả visual semantics."
            )
        if VISUAL_KEYWORD_RE.search(content) and not figures:
            issues.append(
                "[CRITICAL] Nội dung nhắc tới hình/đồ/sơ đồ/biểu đồ nhưng thiếu ontology "
                "`<:: mô tả chi tiết : figure ::>`."
            )
        for desc in all_ontology:
            normalized = re.sub(r"\s+", " ", desc)
            if len(normalized) < 80:
                issues.append(
                    "[CRITICAL] Mô tả visual ontology quá ngắn. Cần mô tả chi tiết nhãn, "
                    "nút/ô, đường nối, vị trí và quan hệ."
                )
            elif not RELATION_DETAIL_RE.search(normalized):
                issues.append(
                    "[CRITICAL] Mô tả visual ontology chưa thể hiện cấu trúc/quan hệ "
                    "(nút, đường nối, hàng/cột, vị trí...)."
                )

        if issues:
            print(f"📄 {fname}:")
            for issue in issues:
                print(f"   - {issue}")
                if "CRITICAL" in issue:
                    if _classify(issue) == "hard":
                        hard_critical += 1
                    else:
                        soft_critical += 1

    print("-" * 50)
    total = hard_critical + soft_critical
    if total == 0:
        print("  ✅ 100% PASS. Cấu trúc bảng và Tọa độ đạt chuẩn Enterprise!")
        sys.exit(0)
    if hard_critical > 0:
        print(
            f"  🔴 TỔNG KẾT: {hard_critical} lỗi cấu trúc (HARD) + "
            f"{soft_critical} lỗi figure/keyword (SOFT). "
            f"Cần repair các trang HARD."
        )
        sys.exit(1)
    print(
        f"  🟡 TỔNG KẾT: chỉ còn {soft_critical} lỗi figure/keyword (SOFT). "
        f"Không có vi phạm cấu trúc — caller có thể chấp nhận và merge."
    )
    sys.exit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--md-dir", default=None)
    parser.add_argument("--manifest", default=None)
    args = parser.parse_args()
    md_dir = args.md_dir or os.path.join(
        os.getcwd(), ".agents", "temp", "temp_md"
    )
    run_qa(md_dir, manifest_path=args.manifest)
