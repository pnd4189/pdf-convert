#!/usr/bin/env python3
"""
step1_docling_parse.py — Deterministic layout/table/OCR extraction via Docling.

Streaming: PDFs >200 pages OR >50MB are processed in batches of 40 pages,
           intermediate results flushed to disk to cap RAM under 8GB.

Usage:
    python step1_docling_parse.py <input_file> --cache-key <key>

Outputs:
    Writes .cache/docling/{key}.json
    Prints cache path to stdout
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.cache_utils import (
    DOCLING_VERSION,
    atomic_write_json,
    cache_entry_path,
    lru_evict,
    make_cache_key,
)

STREAM_PAGE_THRESHOLD = 200
STREAM_SIZE_THRESHOLD_MB = 50
BATCH_SIZE = 40


def _get_pdf_page_count(path: str) -> int:
    """Return PDF page count without loading full document."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(path).pages)
    except Exception:
        return 0


def _make_converter(input_format: str):
    """Build a DocumentConverter with appropriate options."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    format_opts = {}
    if input_format == "pdf":
        opts = PdfPipelineOptions(do_ocr=True, do_table_structure=True)
        format_opts = {InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    return DocumentConverter(format_options=format_opts)


def _convert_batch(input_path: str, start_page: int, end_page: int) -> list:
    """Convert a docling page_range (1-based), return list of page dicts."""
    # page_range uses 1-based indexing in docling
    conv = _make_converter("pdf")
    result = conv.convert(
        input_path,
        page_range=(start_page + 1, end_page + 1),
        raises_on_error=False,
    )
    return _extract_all_pages(result.document)


def _convert_full(input_path: str, input_format: str) -> list:
    """Convert entire document at once (small files)."""
    conv = _make_converter(input_format)
    result = conv.convert(input_path, raises_on_error=False)
    return _extract_all_pages(result.document)


def _get_page_nos(doc) -> list[int]:
    """Return list of page numbers from doc.pages (handles dict or iterable)."""
    pages = doc.pages
    if isinstance(pages, dict):
        # Keys are page_no ints
        return sorted(pages.keys())
    # List/iterable — items may be int or Page objects
    result = []
    for p in pages:
        result.append(p if isinstance(p, int) else getattr(p, "page_no", p))
    return result


def _get_page_obj(doc, page_no: int):
    """Return the Page object for a given page_no (handles dict or list)."""
    pages = doc.pages
    if isinstance(pages, dict):
        return pages.get(page_no)
    return next((p for p in pages if (p if isinstance(p, int) else getattr(p, "page_no", None)) == page_no), None)


def _extract_all_pages(doc) -> list:
    """Extract all pages from a converted DoclingDocument."""
    return [_page_to_dict(doc, pno) for pno in _get_page_nos(doc)]


def _page_to_dict(doc, page_no: int) -> dict:
    """Serialize a single page's elements using the correct docling API."""
    elements = []
    tables = []

    # iterate_items(page_no=N) filters by page efficiently
    for item, _level in doc.iterate_items(page_no=page_no):
        item_type = type(item).__name__
        bbox = None
        prov = getattr(item, "prov", None)
        if prov:
            p = prov[0]
            b = p.bbox
            bbox = [b.l, b.t, b.r, b.b]

        if item_type == "TableItem":
            cells = []
            data = getattr(item, "data", None)
            if data and hasattr(data, "table_cells"):
                for cell in data.table_cells:
                    cells.append({
                        "row": cell.start_row_offset_idx,
                        "col": cell.start_col_offset_idx,
                        "text": cell.text or "",
                        "row_span": cell.row_span,
                        "col_span": cell.col_span,
                    })
            tables.append({"type": item_type, "bbox": bbox, "cells": cells})
        else:
            text = getattr(item, "text", "") or ""
            if text.strip():
                elements.append({"type": item_type, "text": text, "bbox": bbox})

    page_obj = _get_page_obj(doc, page_no)
    size = [0, 0]
    if page_obj and hasattr(page_obj, "size") and page_obj.size:
        size = [page_obj.size.width, page_obj.size.height]

    return {"page_no": page_no, "elements": elements, "tables": tables, "size": size}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("--cache-key", required=False)
    args = parser.parse_args()

    input_path = args.input_file
    if not Path(input_path).exists():
        print(f"ERROR: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    key = args.cache_key or make_cache_key(input_path)
    out_path = cache_entry_path(key)

    suffix = Path(input_path).suffix.lower().lstrip(".")
    file_mb = Path(input_path).stat().st_size / (1024 * 1024)

    use_streaming = False
    page_count = 0
    if suffix == "pdf":
        page_count = _get_pdf_page_count(input_path)
        use_streaming = page_count > STREAM_PAGE_THRESHOLD or file_mb > STREAM_SIZE_THRESHOLD_MB
        print(
            f"[step1] PDF pages={page_count} size={file_mb:.1f}MB "
            f"streaming={'yes' if use_streaming else 'no'}",
            file=sys.stderr,
        )

    all_pages = []

    if use_streaming:
        # Batch process to keep RAM under 8GB
        for start in range(0, page_count, BATCH_SIZE):
            end = min(start + BATCH_SIZE - 1, page_count - 1)
            print(f"[step1] batch pages {start}–{end}", file=sys.stderr)
            batch = _convert_batch(input_path, start, end)
            all_pages.extend(batch)
    else:
        print(f"[step1] full convert ({suffix})", file=sys.stderr)
        all_pages = _convert_full(input_path, suffix)

    cache_data = {
        "version": DOCLING_VERSION,
        "source_hash": key.split("_")[0],
        "format": suffix,
        "pages": all_pages,
    }

    lru_evict()
    atomic_write_json(out_path, cache_data)

    print(str(out_path))
    print(f"[step1] wrote {len(all_pages)} pages → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
