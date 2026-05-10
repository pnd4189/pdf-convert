#!/usr/bin/env python3
"""
step3_merge.py — Lắp ghép Markdown, Trích xuất Grounding Map và Xuất JSON chuẩn Landing.AI
"""

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter

# ── Regex Patterns ───────────────────────────────────────────────────────
# Bắt thẻ neo chứa box: <a id='0-1' box='[0.15, 0.20, 0.85, 0.25]'></a>
ANCHOR_PARSE_RE = re.compile(
    r"""<a\s+id\s*=\s*['"]([^'"]+)['"]\s*(?:box\s*=\s*['"]([^'"]+)['"])?\s*>\s*</a>""",
    re.IGNORECASE,
)
# Làm sạch Markdown: Xóa thuộc tính box='...' khỏi thẻ neo
CLEAN_ANCHOR_RE = re.compile(
    r"(<a\s+id\s*=\s*['\"][^'\"]+['\"])\s*box\s*=\s*['\"][^'\"]+['\"](\s*>\s*</a>)",
    re.IGNORECASE,
)
# Bắt thẻ neo đã được làm sạch
SIMPLE_ANCHOR_RE = re.compile(
    r"<a\s+id\s*=\s*['\"]([^'\"]+)['\"]\s*>\s*</a>",
    re.IGNORECASE,
)

# Regex cho Bảng biểu và Ontology
TABLE_ID_RE = re.compile(r"<table[^>]+id\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
TD_ID_RE = re.compile(r"<t[dh][^>]+id\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
ONTOLOGY_RE = re.compile(r"<::\s*(.*?)\s*:\s*(figure|logo|scan_code|attestation|marginalia)\s*::>", re.IGNORECASE)
BLANK_PAGE_RE = re.compile(r"<!--\s*TRANG TRỐNG\s*-\s*ĐÃ XÁC MINH\s*-->")
HEADING_RE = re.compile(r"^\s*(#{1,6}\s|<h[1-6][ >])", re.IGNORECASE)


def detect_type(content: str) -> str:
    """Phân loại Chunk chuẩn Expanded Ontology của Landing.AI"""
    stripped = content.strip()
    if not stripped: return "chunkText"
    if "<table" in stripped.lower(): return "chunkTable"

    match = ONTOLOGY_RE.search(stripped)
    if match:
        entity_type = match.group(2).lower()
        if entity_type == "scan_code": return "chunkScanCode"
        return f"chunk{entity_type.capitalize()}"

    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    if lines and HEADING_RE.match(lines[0]) and len(lines) <= 3:
        return "chunkHeading"
    return "chunkText"


def parse_box(box_str: str):
    """Chuyển chuỗi '[left, top, right, bottom]' thành Dictionary"""
    if not box_str: return None
    try:
        clean = box_str.strip("[]")
        coords = [float(x.strip()) for x in clean.split(",")]
        if len(coords) == 4:
            return {"left": coords[0], "top": coords[1], "right": coords[2], "bottom": coords[3]}
    except Exception: pass
    return None


def process_page(pnum: int, raw_md: str, grounding_map: dict):
    """Xử lý từng trang: Rút tọa độ, Dọn dẹp Markdown, và Chia Chunks"""
    if BLANK_PAGE_RE.search(raw_md):
        return [], ""

    # 1. Hút tọa độ vật lý
    for match in ANCHOR_PARSE_RE.finditer(raw_md):
        a_id = match.group(1)
        a_box = match.group(2)
        grounding_map[a_id] = {
            "page": pnum,
            "type": "chunkText",  # Sẽ update lại ở bước chia chunk
            "box": parse_box(a_box) if a_box else None
        }

    # 2. Hút ID của bảng biểu (Lưới tọa độ logic)
    for m in TABLE_ID_RE.finditer(raw_md): grounding_map[m.group(1)] = {"page": pnum, "type": "table"}
    for m in TD_ID_RE.finditer(raw_md): grounding_map[m.group(1)] = {"page": pnum, "type": "tableCell"}

    # 3. Làm sạch Markdown (Xóa thuộc tính box)
    clean_md = CLEAN_ANCHOR_RE.sub(r"\1\2", raw_md)

    # 4. Phân rã Chunks dựa trên vị trí thẻ neo sạch
    chunks = []
    anchors = list(SIMPLE_ANCHOR_RE.finditer(clean_md))

    # Fallback nếu không có thẻ neo
    if not anchors:
        content = clean_md.strip()
        if content:
            fallback_id = f"{pnum}-1"
            c_type = detect_type(content)
            chunks.append({"chunk_id": fallback_id, "page_number": pnum, "type": c_type, "content": content})
            if fallback_id not in grounding_map:
                grounding_map[fallback_id] = {"page": pnum, "type": c_type, "box": None}
        return chunks, clean_md

    for idx, match in enumerate(anchors):
        a_id = match.group(1)
        start = match.end()
        end = anchors[idx + 1].start() if idx + 1 < len(anchors) else len(clean_md)
        content = clean_md[start:end].strip()

        if not content: continue

        c_type = detect_type(content)
        chunks.append({"chunk_id": a_id, "page_number": pnum, "type": c_type, "content": content})

        # Cập nhật loại chính xác vào Bản đồ
        if a_id in grounding_map:
            grounding_map[a_id]["type"] = c_type

    return chunks, clean_md


def page_num(fname: str) -> int:
    return int(fname.replace("page_", "").replace(".md", ""))


def _build_grounding_map(grounding: dict, docling_cache_path: str | None) -> dict:
    """Build grounding_map with Docling element IDs and bbox as [l,t,r,b] array."""
    docling_elements = {}
    if docling_cache_path and os.path.exists(docling_cache_path):
        with open(docling_cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        for page in cache.get("pages", []):
            pnum = page.get("page_no", 0)
            for i, elem in enumerate(page.get("elements", [])):
                eid = f"docling-{pnum}-{i}"
                docling_elements[eid] = {"page": pnum, "bbox": elem.get("bbox"), "text": elem.get("text", "")}

    gmap = {}
    for anchor_id, entry in grounding.items():
        box = entry.get("box")
        bbox_list = None
        if box and isinstance(box, dict):
            bbox_list = [box.get("left"), box.get("top"), box.get("right"), box.get("bottom")]

        gmap[anchor_id] = {
            "page": entry.get("page", 0),
            "type": entry.get("type", "chunkText"),
            "bbox": bbox_list,
        }
        # Attach nearest docling element ID by page (simple heuristic: same page first match)
        if docling_elements:
            page_no = entry.get("page", 0)
            match = next((eid for eid, e in docling_elements.items() if e["page"] == page_no), None)
            if match:
                gmap[anchor_id]["docling_element_id"] = match

    return gmap


def main():
    parser = argparse.ArgumentParser(description="Đóng gói JSON chuẩn Landing.AI")
    parser.add_argument("--name", default="final_parsed_document", help="Tên file Output (không đuôi .json)")
    parser.add_argument("--md-dir", default=None, help="Thư mục chứa các file page_N.md")
    parser.add_argument("--docling-cache", default=None, help="Path đến Docling cache JSON (tùy chọn)")
    args = parser.parse_args()

    base_dir = os.getcwd()
    md_dir = args.md_dir or os.path.join(base_dir, ".agents", "temp", "temp_md")

    # BẮT BUỘC ĐÍCH LƯU
    out_dir = "/home/dung/ANTIGRAVITY/SÁCH CONVERT/"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{args.name}.json")

    if not os.path.isdir(md_dir):
        print(f"ERROR: Không tìm thấy thư mục MD tạm: {md_dir}")
        sys.exit(1)

    files = [f for f in os.listdir(md_dir) if f.startswith("page_") and f.endswith(".md")]
    if not files:
        print("ERROR: Không có file MD nào để ghép.")
        sys.exit(1)

    files.sort(key=page_num)

    split_level = []
    chunk_level = []
    full_parts = []
    grounding_map = {}

    print(f"\n🔄 Bắt đầu ghép {len(files)} trang vào cấu trúc JSON ADE...")

    for fname in files:
        pnum = page_num(fname)
        with open(os.path.join(md_dir, fname), "r", encoding="utf-8") as f:
            raw_md = f.read()

        page_chunks, clean_md = process_page(pnum, raw_md, grounding_map)

        if clean_md.strip() or page_chunks:
            split_level.append({"page_number": pnum, "markdown": clean_md})
            full_parts.append(clean_md)
            chunk_level.extend(page_chunks)

    # Build Docling-enriched grounding_map
    enriched_grounding_map = _build_grounding_map(grounding_map, args.docling_cache)

    # ĐÓNG GÓI JSON 4 CẤP ĐỘ
    final_output = {
        "metadata": {
            "source": f"{args.name}.pdf",
            "total_pages": len(split_level),
            "total_chunks": len(chunk_level),
            "grounded_elements": len(grounding_map),
            "schema_version": "ade_landing_ai_v2" if args.docling_cache else "ade_landing_ai_v1"
        },
        "top_level": {"full_markdown": "\n\n".join(full_parts)},
        "split_level": split_level,
        "chunk_level": chunk_level,
        "grounding": grounding_map,
        "grounding_map": enriched_grounding_map,
    }

    # Ghi file và Dọn dẹp
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)

        # Kiểm tra JSON có hợp lệ không
        with open(out_path, "r", encoding="utf-8") as f: json.load(f)

        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"✅ THÀNH CÔNG: Đã lưu JSON tại {out_path} ({size_mb:.2f} MB)")
        print(f"   • {len(chunk_level)} khối dữ liệu Semantic (Chunks)")
        print(f"   • {len(grounding_map)} Mốc tọa độ vật lý và Ô bảng")

        # Dọn dẹp an toàn — chỉ dọn khi dùng default temp dir
        temp_base = os.path.join(base_dir, ".agents", "temp")
        if not args.md_dir and os.path.exists(temp_base):
            shutil.rmtree(temp_base)
            print("🧹 Đã dọn dẹp thư mục tạm (.agents/temp/).")

    except Exception as e:
        print(f"❌ LỖI NGHIÊM TRỌNG KHI GHI FILE: {e}")
        print("Dữ liệu tạm thời CHƯA bị xóa để bạn có thể debug.")
        sys.exit(1)

if __name__ == "__main__":
    main()
