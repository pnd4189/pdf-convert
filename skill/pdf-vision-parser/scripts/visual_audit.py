#!/usr/bin/env python3
"""
visual_audit.py — Detect rendered pages that contain visual content not covered
by Docling text/table boxes.

This is a deterministic guardrail for the native Gemini CLI PDF workflow. It
does not describe images; it only flags pages where the active model must look
at the PNG and produce figure/table semantics instead of accepting a Docling
text dump.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def _docling_box_to_pixels(box: list[float], page_size: list[float], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    page_w, page_h = page_size or [0, 0]
    img_w, img_h = image_size
    if not box or page_w <= 0 or page_h <= 0:
        return (0, 0, 0, 0)
    left, top_doc, right, bottom_doc = box
    x1 = int(max(0, min(img_w, left / page_w * img_w)))
    x2 = int(max(0, min(img_w, right / page_w * img_w)))
    y1 = int(max(0, min(img_h, (page_h - top_doc) / page_h * img_h)))
    y2 = int(max(0, min(img_h, (page_h - bottom_doc) / page_h * img_h)))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return (x1, y1, x2, y2)


def _covered_boxes(page: dict, image_size: tuple[int, int], margin: int) -> list[tuple[int, int, int, int]]:
    page_size = page.get("size") or [0, 0]
    boxes = []
    for elem in page.get("elements", []):
        if elem.get("bbox"):
            boxes.append(_docling_box_to_pixels(elem["bbox"], page_size, image_size))
    for table in page.get("tables", []):
        if table.get("bbox"):
            boxes.append(_docling_box_to_pixels(table["bbox"], page_size, image_size))

    img_w, img_h = image_size
    expanded = []
    for x1, y1, x2, y2 in boxes:
        expanded.append((
            max(0, x1 - margin),
            max(0, y1 - margin),
            min(img_w, x2 + margin),
            min(img_h, y2 + margin),
        ))
    return expanded


def _inside_any_box(x: int, y: int, boxes: list[tuple[int, int, int, int]]) -> bool:
    return any(x1 <= x <= x2 and y1 <= y <= y2 for x1, y1, x2, y2 in boxes)


def _find_uncovered_visual(page: dict, png_path: Path, sample_max_width: int, threshold: int, min_pixels: int) -> dict | None:
    if not png_path.exists():
        return None
    image = Image.open(png_path).convert("L")
    orig_w, orig_h = image.size
    scale = 1.0
    if orig_w > sample_max_width:
        scale = sample_max_width / orig_w
        image = image.resize((sample_max_width, int(orig_h * scale)))
    img_w, img_h = image.size

    margin = max(4, int(24 * scale))
    boxes = _covered_boxes(page, (img_w, img_h), margin)
    px = image.load()

    count = 0
    min_x, min_y = img_w, img_h
    max_x, max_y = 0, 0
    for y in range(img_h):
        for x in range(img_w):
            if px[x, y] >= threshold:
                continue
            if _inside_any_box(x, y, boxes):
                continue
            count += 1
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

    if count < min_pixels:
        return None

    norm_box = [
        round(min_x / img_w, 4),
        round(min_y / img_h, 4),
        round(max_x / img_w, 4),
        round(max_y / img_h, 4),
    ]
    box_width = norm_box[2] - norm_box[0]
    box_height = norm_box[3] - norm_box[1]
    # Bold headers and text baseline drift can leave small uncovered dark
    # regions. A visual candidate must occupy a meaningful page region.
    if box_width < 0.12 or box_height < 0.08:
        return None

    return {
        "page_no": page.get("page_no"),
        "png": str(png_path),
        "reason": "uncovered_dark_pixels_outside_docling_text_or_table_boxes",
        "uncovered_dark_pixels_sampled": count,
        "bbox": norm_box,
    }


def build_visual_candidates(cache_json: str, png_dir: str) -> list[dict]:
    cache_path = Path(cache_json)
    if not cache_json or not cache_path.exists():
        return []
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    candidates = []
    for page in cache.get("pages", []):
        page_no = page.get("page_no")
        if page_no is None:
            continue
        png_path = Path(png_dir) / f"{int(page_no):04d}.png"
        candidate = _find_uncovered_visual(
            page,
            png_path,
            sample_max_width=850,
            threshold=205,
            min_pixels=5000,
        )
        if candidate:
            candidates.append(candidate)
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-json", required=True)
    parser.add_argument("--png-dir", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    candidates = build_visual_candidates(args.cache_json, args.png_dir)
    payload = {"visual_candidates": candidates, "count": len(candidates)}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
