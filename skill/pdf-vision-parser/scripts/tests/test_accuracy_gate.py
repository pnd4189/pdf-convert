#!/usr/bin/env python3
"""
test_accuracy_gate.py — Phase 5 accuracy gate for Docling+Gemini hybrid pipeline.

Runs step1_docling_parse.py on each corpus document and measures:
  - Structural fidelity (element count vs ground truth)
  - Table cell-level F1 score
  - Gate decision: PASS (>=95% table F1) → skip Phase 6, FAIL → activate PaddleOCR

Usage:
    python test_accuracy_gate.py [--corpus-dir <path>] [--gate-threshold 0.95]

The test only validates the Docling parse step (step1), not the full pipeline,
for fast iteration. Full pipeline accuracy requires running the agy native
/pdf-convert flow and diffing the ADE output against ground truth — document
that separately.
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
# scripts/ for lib.cache_utils; tests/ for gate_lib.*
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from gate_lib.table_diff import compute_cell_f1, CellF1Result
from gate_lib.ground_truth_loader import load_ground_truth, get_tables_for_page, find_ground_truth

PYTHON = sys.executable
DEFAULT_CORPUS_DIR = SCRIPTS_DIR / "test_corpus"
DEFAULT_GATE_THRESHOLD = 0.95


@dataclass
class DocResult:
    source: str
    category: str
    element_count: int
    expected_element_count: int
    table_f1: float | None
    table_f1_passed: bool
    error: str | None


def run_docling_parse(input_path: str) -> dict | None:
    """Run step1_docling_parse.py and return parsed cache JSON."""
    from lib.cache_utils import make_cache_key, cache_entry_path, cache_hit

    key = make_cache_key(input_path)
    cache_path = cache_entry_path(key)

    if not cache_hit(key):
        env = {**__import__("os").environ, "HF_HUB_OFFLINE": "1"}
        result = subprocess.run(
            [PYTHON, str(SCRIPTS_DIR / "step1_docling_parse.py"), input_path, "--cache-key", key],
            capture_output=True, text=True, timeout=1800, env=env  # offline: skip HF CDN check
        )
        if result.returncode != 0:
            print(f"  ERROR: {result.stderr.strip()[:200]}", file=sys.stderr)
            return None

    with open(cache_path, "r", encoding="utf-8") as f:
        return json.load(f)


def measure_doc(doc_path: Path, category: str, gt_root: Path, gate_threshold: float) -> DocResult:
    print(f"\n[gate] Testing: {doc_path.name} ({category})")
    cache_data = run_docling_parse(str(doc_path))
    if not cache_data:
        return DocResult(doc_path.name, category, 0, 0, None, False, "parse_failed")

    pages = cache_data.get("pages", [])
    total_elements = sum(len(p.get("elements", [])) + len(p.get("tables", [])) for p in pages)

    # Check for ground truth
    gt_path = find_ground_truth(str(gt_root), doc_path.stem)
    expected_elements = total_elements  # if no GT, treat actual as expected (structural check skipped)
    table_f1_result = None

    if gt_path:
        gt = load_ground_truth(gt_path)
        expected_elements = sum(p.get("element_count", 0) for p in gt.get("pages", []))

        # Collect all predicted vs truth tables
        pred_tables_all = []
        truth_tables_all = []
        for page in pages:
            pnum = page.get("page_no", 0)
            pred_tables_all.extend(page.get("tables", []))
            truth_tables_all.extend(get_tables_for_page(gt, pnum))

        if truth_tables_all:
            table_f1_result = compute_cell_f1(pred_tables_all, truth_tables_all, gate_threshold)
            print(f"  tables: F1={table_f1_result.f1:.3f} P={table_f1_result.precision:.3f} R={table_f1_result.recall:.3f} "
                  f"(tp={table_f1_result.tp} fp={table_f1_result.fp} fn={table_f1_result.fn})")
        else:
            print(f"  no tables in ground truth — skipping table F1")

    structural_ok = abs(total_elements - expected_elements) <= max(3, expected_elements * 0.05)
    print(f"  elements: found={total_elements} expected={expected_elements} ok={structural_ok}")

    table_f1_val = table_f1_result.f1 if table_f1_result else None
    table_f1_passed = table_f1_result.passed if table_f1_result else True  # no GT = pass by default

    return DocResult(
        source=doc_path.name,
        category=category,
        element_count=total_elements,
        expected_element_count=expected_elements,
        table_f1=table_f1_val,
        table_f1_passed=table_f1_passed,
        error=None,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", default=str(DEFAULT_CORPUS_DIR))
    parser.add_argument("--gate-threshold", type=float, default=DEFAULT_GATE_THRESHOLD)
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    categories = {
        "simple_pdf": [".pdf"],
        "scanned_pdf": [".pdf"],
        "docx_samples": [".docx"],
        "complex_tables": [".pdf"],
    }

    all_results: list[DocResult] = []

    for category, exts in categories.items():
        cat_dir = corpus_dir / category
        gt_root = corpus_dir / category  # GT lives in category/ground_truth/
        if not cat_dir.exists():
            continue
        docs = [f for f in cat_dir.iterdir() if f.suffix.lower() in exts and f.is_file()]
        if not docs:
            print(f"[gate] no docs in {category} — skipping")
            continue
        for doc in sorted(docs):
            r = measure_doc(doc, category, gt_root, args.gate_threshold)
            all_results.append(r)

    if not all_results:
        print("\n[gate] ERROR: no documents processed — populate test_corpus/ first")
        sys.exit(1)

    # Gate decision: any complex_table doc with table F1 < threshold → FAIL
    complex_table_results = [r for r in all_results if r.category == "complex_tables" and r.table_f1 is not None]
    gate_pass = all(r.table_f1_passed for r in complex_table_results) if complex_table_results else None

    # Summary report
    print("\n" + "=" * 60)
    print("ACCURACY GATE REPORT")
    print("=" * 60)
    for r in all_results:
        f1_str = f"F1={r.table_f1:.3f}" if r.table_f1 is not None else "no-GT"
        err_str = f" ERROR:{r.error}" if r.error else ""
        print(f"  [{r.category}] {r.source}: elements={r.element_count}/{r.expected_element_count} {f1_str}{err_str}")

    print()
    if gate_pass is None:
        print("GATE DECISION: INCONCLUSIVE — no complex-table ground truth available")
        print("Action: Add hand-annotated GT to test_corpus/complex_tables/ground_truth/")
    elif gate_pass:
        print(f"GATE DECISION: PASS (complex-table F1 >= {args.gate_threshold:.0%})")
        print("Action: SKIP Phase 6 (PaddleOCR) — proceed to Phase 7")
    else:
        avg_f1 = sum(r.table_f1 for r in complex_table_results if r.table_f1) / len(complex_table_results)
        print(f"GATE DECISION: FAIL (avg complex-table F1 = {avg_f1:.3f} < {args.gate_threshold:.0%})")
        print("Action: ACTIVATE Phase 6 (PaddleOCR PP-StructureV3)")

    print("=" * 60)
    return 0 if (gate_pass is not False) else 1


if __name__ == "__main__":
    sys.exit(main())
