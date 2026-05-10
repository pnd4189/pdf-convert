#!/usr/bin/env python3
"""
epub_router.py — EPUB chapter classification for fast-path routing.

Text-only chapters (no embedded images/figures/SVG) bypass Gemini step2 entirely,
going straight from Docling output to step3. Media-bearing chapters route through
the full Gemini refinement pipeline.

Token usage: ≥70% reduction expected on text-heavy EPUBs (e.g. novels, textbooks).
"""

import re
from pathlib import Path

# HTML tags that indicate embedded visual content requiring Gemini analysis
_MEDIA_TAG_PATTERN = re.compile(r"<(img|figure|svg|picture|video|canvas)\b", re.IGNORECASE)


def chapter_needs_gemini(html_content: str) -> bool:
    """Return True if chapter HTML contains media elements requiring Gemini vision."""
    return bool(_MEDIA_TAG_PATTERN.search(html_content))


def classify_docling_epub_pages(cache_data: dict) -> dict[int, str]:
    """
    Classify each page from Docling EPUB output as 'text' or 'media'.

    Docling EPUB pages may carry raw HTML in 'html_content' or we infer from
    element types. If a page has no elements or only text elements, it's 'text'.
    If it has figure/image elements, it's 'media'.

    Returns: {page_no: 'text' | 'media'}
    """
    classification: dict[int, str] = {}
    for page in cache_data.get("pages", []):
        page_no = page.get("page_no", 0)

        # Check raw HTML if Docling preserved it
        html = page.get("html_content", "")
        if html and chapter_needs_gemini(html):
            classification[page_no] = "media"
            continue

        # Infer from element types in Docling output
        has_media = any(
            e.get("type", "").lower() in ("pictureitem", "figureitem", "imageitem", "picture", "figure")
            for e in page.get("elements", [])
        )
        classification[page_no] = "media" if has_media else "text"

    return classification


def split_pages_by_route(
    cache_data: dict,
) -> tuple[list[dict], list[dict]]:
    """
    Split EPUB Docling pages into (text_only_pages, media_pages).

    text_only_pages → write Docling markdown directly to temp_md (skip Gemini)
    media_pages     → send through step2 Gemini refinement
    """
    classification = classify_docling_epub_pages(cache_data)
    text_only = []
    media = []
    for page in cache_data.get("pages", []):
        page_no = page.get("page_no", 0)
        if classification.get(page_no, "text") == "media":
            media.append(page)
        else:
            text_only.append(page)
    return text_only, media


def build_docling_markdown_for_page(page: dict) -> str:
    """Convert a Docling text-only page dict to simple ADE Markdown (no Gemini needed)."""
    lines = []
    page_no = page.get("page_no", 0)
    elem_idx = 1

    for elem in page.get("elements", []):
        text = (elem.get("text") or "").strip()
        if not text:
            continue
        bbox = elem.get("bbox")
        box_str = (
            f"[{bbox[0]:.4f},{bbox[1]:.4f},{bbox[2]:.4f},{bbox[3]:.4f}]"
            if bbox and len(bbox) == 4
            else "[0.0,0.0,1.0,1.0]"
        )
        anchor_id = f"{page_no}-{elem_idx}"
        lines.append(f"<a id='{anchor_id}' box='{box_str}'></a>")

        etype = elem.get("type", "")
        if "heading" in etype.lower():
            lines.append(f"## {text}")
        else:
            lines.append(text)
        lines.append("")
        elem_idx += 1

    for table in page.get("tables", []):
        bbox = table.get("bbox")
        box_str = (
            f"[{bbox[0]:.4f},{bbox[1]:.4f},{bbox[2]:.4f},{bbox[3]:.4f}]"
            if bbox and len(bbox) == 4
            else "[0.0,0.0,1.0,1.0]"
        )
        anchor_id = f"{page_no}-{elem_idx}"
        lines.append(f"<a id='{anchor_id}' box='{box_str}'></a>")

        cells = table.get("cells", [])
        if not cells:
            elem_idx += 1
            continue

        # Build minimal HTML table
        max_row = max(c.get("row", 0) for c in cells) + 1
        max_col = max(c.get("col", 0) for c in cells) + 1
        grid: dict[tuple, str] = {}
        for c in cells:
            grid[(c.get("row", 0), c.get("col", 0))] = c.get("text", "")

        table_id = f"{page_no}-{elem_idx}"
        lines.append(f'<table id="{table_id}">')
        cell_seq = elem_idx + 1
        for r in range(max_row):
            lines.append("<tr>")
            for col in range(max_col):
                text = grid.get((r, col), "")
                lines.append(f'<td id="{page_no}-{cell_seq}">{text}</td>')
                cell_seq += 1
            lines.append("</tr>")
        lines.append("</table>")
        lines.append("")
        elem_idx = cell_seq

    return "\n".join(lines)
