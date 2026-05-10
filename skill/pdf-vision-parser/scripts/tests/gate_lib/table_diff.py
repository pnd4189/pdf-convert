#!/usr/bin/env python3
"""
table_diff.py — Cell-level F1 score for table extraction accuracy.

A "cell" is matched if: same (row, col) position AND content similarity >= MATCH_THRESHOLD.
F1 = 2 * precision * recall / (precision + recall)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import re

MATCH_THRESHOLD = 0.85  # Levenshtein similarity required for content match


def _normalize(text: str) -> str:
    """Normalize cell text for comparison."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _similarity(a: str, b: str) -> float:
    """Levenshtein-based similarity in [0, 1]."""
    a, b = _normalize(a), _normalize(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Simple DP Levenshtein
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(prev[j] + 1, dp[j - 1] + 1, prev[j - 1] + cost)
    return 1.0 - dp[n] / max(m, n)


@dataclass
class CellF1Result:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    total_predicted: int
    total_truth: int
    passed: bool  # f1 >= threshold
    gate_threshold: float = 0.95


def compute_cell_f1(
    predicted_tables: list[dict],
    truth_tables: list[dict],
    gate_threshold: float = 0.95,
) -> CellF1Result:
    """
    Compute cell-level F1 across all tables on a page/doc.

    predicted_tables / truth_tables: list of table dicts, each with 'cells':
        [{"row": int, "col": int, "text": str, "row_span": int, "col_span": int}]
    """
    # Flatten all cells tagged with table index
    def flatten(tables: list[dict]) -> list[tuple[int, int, int, str]]:
        cells = []
        for t_idx, table in enumerate(tables):
            for cell in table.get("cells", []):
                cells.append((t_idx, cell.get("row", 0), cell.get("col", 0), cell.get("text", "")))
        return cells

    pred_cells = flatten(predicted_tables)
    truth_cells = flatten(truth_tables)

    matched_truth = set()
    tp = 0

    for p_tidx, p_row, p_col, p_text in pred_cells:
        for i, (t_tidx, t_row, t_col, t_text) in enumerate(truth_cells):
            if i in matched_truth:
                continue
            # Table index match is lenient (same order) if single table
            if p_row == t_row and p_col == t_col:
                if _similarity(p_text, t_text) >= MATCH_THRESHOLD:
                    tp += 1
                    matched_truth.add(i)
                    break

    fp = len(pred_cells) - tp
    fn = len(truth_cells) - tp

    precision = tp / len(pred_cells) if pred_cells else 0.0
    recall = tp / len(truth_cells) if truth_cells else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return CellF1Result(
        precision=precision,
        recall=recall,
        f1=f1,
        tp=tp,
        fp=fp,
        fn=fn,
        total_predicted=len(pred_cells),
        total_truth=len(truth_cells),
        passed=f1 >= gate_threshold,
        gate_threshold=gate_threshold,
    )
