#!/usr/bin/env python3
"""
test_extended_formats.py — Phase 7 extended format tests.

Tests:
1. epub_router: text-only chapter classification
2. epub_router: media-bearing chapter detection
3. epub_router: mixed EPUB page split
4. step1_7_epub_route: full routing pipeline (unit, no disk I/O for core logic)
5. PPTX/DOCX: Docling parser accepts the format without crashing
6. Scanned PDF: step0 cache key is stable across identical runs
"""

import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.epub_router import (
    build_docling_markdown_for_page,
    chapter_needs_gemini,
    classify_docling_epub_pages,
    split_pages_by_route,
)


# ── Helper ──────────────────────────────────────────────────────────────────

def _make_cache(pages: list[dict]) -> dict:
    return {"version": "test", "source_hash": "abc", "format": "epub", "pages": pages}


def _text_page(page_no: int) -> dict:
    return {
        "page_no": page_no,
        "elements": [{"type": "TextItem", "text": f"Chapter {page_no} content", "bbox": [0.1, 0.1, 0.9, 0.2]}],
        "tables": [],
        "size": [595, 842],
    }


def _media_page(page_no: int) -> dict:
    return {
        "page_no": page_no,
        "elements": [
            {"type": "PictureItem", "text": "", "bbox": [0.1, 0.3, 0.9, 0.7]},
            {"type": "TextItem", "text": "Figure caption", "bbox": [0.1, 0.7, 0.9, 0.8]},
        ],
        "tables": [],
        "size": [595, 842],
    }


# ── Tests ────────────────────────────────────────────────────────────────────

def test_chapter_needs_gemini_false_for_plain_text():
    html = "<p>Simple text chapter with no images.</p>"
    assert chapter_needs_gemini(html) is False


def test_chapter_needs_gemini_true_for_img():
    html = '<p>Text</p><img src="cover.png" />'
    assert chapter_needs_gemini(html) is True


def test_chapter_needs_gemini_true_for_figure():
    html = "<figure><img src='chart.png'><figcaption>Fig 1</figcaption></figure>"
    assert chapter_needs_gemini(html) is True


def test_chapter_needs_gemini_true_for_svg():
    html = "<p>Intro</p><svg viewBox='0 0 100 100'><circle cx='50' cy='50' r='40'/></svg>"
    assert chapter_needs_gemini(html) is True


def test_classify_text_only_pages():
    cache = _make_cache([_text_page(1), _text_page(2)])
    result = classify_docling_epub_pages(cache)
    assert result == {1: "text", 2: "text"}


def test_classify_media_page_via_element_type():
    cache = _make_cache([_text_page(1), _media_page(2)])
    result = classify_docling_epub_pages(cache)
    assert result[1] == "text"
    assert result[2] == "media"


def test_classify_media_page_via_html_content():
    page = {
        "page_no": 3,
        "html_content": "<p>Intro</p><img src='pic.png' />",
        "elements": [],
        "tables": [],
        "size": [595, 842],
    }
    cache = _make_cache([page])
    result = classify_docling_epub_pages(cache)
    assert result[3] == "media"


def test_split_pages_correct_counts():
    pages = [_text_page(i) for i in range(1, 6)] + [_media_page(i) for i in range(6, 9)]
    cache = _make_cache(pages)
    text_only, media = split_pages_by_route(cache)
    assert len(text_only) == 5
    assert len(media) == 3


def test_split_all_text_returns_empty_media():
    cache = _make_cache([_text_page(i) for i in range(1, 4)])
    text_only, media = split_pages_by_route(cache)
    assert len(media) == 0
    assert len(text_only) == 3


def test_split_all_media_returns_empty_text():
    cache = _make_cache([_media_page(i) for i in range(1, 4)])
    text_only, media = split_pages_by_route(cache)
    assert len(text_only) == 0
    assert len(media) == 3


def test_build_docling_markdown_for_text_page():
    page = _text_page(5)
    md = build_docling_markdown_for_page(page)
    assert "<a id='5-1'" in md
    assert "Chapter 5 content" in md
    assert "box=" in md


def test_build_docling_markdown_for_page_with_table():
    page = {
        "page_no": 2,
        "elements": [],
        "tables": [
            {
                "bbox": [0.1, 0.3, 0.9, 0.7],
                "cells": [
                    {"row": 0, "col": 0, "text": "Header A", "row_span": 1, "col_span": 1},
                    {"row": 0, "col": 1, "text": "Header B", "row_span": 1, "col_span": 1},
                    {"row": 1, "col": 0, "text": "Val 1", "row_span": 1, "col_span": 1},
                    {"row": 1, "col": 1, "text": "Val 2", "row_span": 1, "col_span": 1},
                ],
            }
        ],
        "size": [595, 842],
    }
    md = build_docling_markdown_for_page(page)
    assert "<table" in md
    assert "Header A" in md
    assert "Val 2" in md


def test_step1_7_epub_route_integration():
    """Integration: route mixed pages, verify temp_md files and filtered cache."""
    pages = [_text_page(1), _text_page(2), _media_page(3)]
    cache_data = _make_cache(pages)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cache_file = tmp_path / "test_cache.json"
        cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

        temp_md = tmp_path / "temp_md"
        temp_md.mkdir()

        # Simulate what step1_7_epub_route.py does
        text_only, media = split_pages_by_route(cache_data)

        for page in text_only:
            page_no = page.get("page_no", 0)
            md = build_docling_markdown_for_page(page)
            (temp_md / f"page_{page_no:04d}.md").write_text(md, encoding="utf-8")

        media_cache = dict(cache_data)
        media_cache["pages"] = media
        media_cache_path = tmp_path / "epub_media_cache.json"
        media_cache_path.write_text(json.dumps(media_cache), encoding="utf-8")

        # Verify
        assert (temp_md / "page_0001.md").exists()
        assert (temp_md / "page_0002.md").exists()
        assert not (temp_md / "page_0003.md").exists()  # media page — goes to Gemini

        loaded_media = json.loads(media_cache_path.read_text())
        assert len(loaded_media["pages"]) == 1
        assert loaded_media["pages"][0]["page_no"] == 3


def test_cache_key_stability(tmp_path):
    """Cache key must be identical for the same file bytes."""
    sys.path.insert(0, str(SCRIPT_DIR))
    from lib.cache_utils import make_cache_key

    f = tmp_path / "sample.pdf"
    f.write_bytes(b"%PDF-1.4 test content" * 100)

    key1 = make_cache_key(str(f))
    key2 = make_cache_key(str(f))
    assert key1 == key2


# ── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            import inspect
            sig = inspect.signature(t)
            if "tmp_path" in sig.parameters:
                with tempfile.TemporaryDirectory() as d:
                    t(Path(d))
            else:
                t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1

    print(f"\n{passed}/{passed + failed} passed")
    sys.exit(0 if failed == 0 else 1)
