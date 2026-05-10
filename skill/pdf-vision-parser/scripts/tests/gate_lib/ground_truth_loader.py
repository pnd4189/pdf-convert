#!/usr/bin/env python3
"""
ground_truth_loader.py — Load hand-annotated ground truth JSON for accuracy gate tests.

Ground truth schema (per document):
{
  "source": "filename.pdf",
  "pages": [
    {
      "page_no": 0,
      "element_count": 12,
      "element_types": ["TextItem", "SectionHeaderItem", "TableItem"],
      "tables": [
        {
          "cells": [
            {"row": 0, "col": 0, "text": "Header A", "row_span": 1, "col_span": 1},
            ...
          ]
        }
      ]
    }
  ],
  "notes": "Hand-annotated by user on 2026-05-09"
}
"""

from __future__ import annotations
import json
from pathlib import Path


def load_ground_truth(gt_path: str) -> dict:
    """Load a ground truth JSON file."""
    with open(gt_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def get_tables_for_page(gt: dict, page_no: int) -> list[dict]:
    """Return table list for a specific page from ground truth."""
    for page in gt.get("pages", []):
        if page.get("page_no") == page_no:
            return page.get("tables", [])
    return []


def get_expected_element_count(gt: dict) -> int:
    """Total expected elements across all pages."""
    return sum(p.get("element_count", 0) for p in gt.get("pages", []))


def find_ground_truth(corpus_dir: str, doc_stem: str) -> str | None:
    """Find ground truth file for a given document stem."""
    d = Path(corpus_dir) / "ground_truth"
    candidates = [
        d / f"{doc_stem}.json",
        d / f"{doc_stem}_gt.json",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None
