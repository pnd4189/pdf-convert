---
phase: 5
title: "Accuracy Gate (PDF+DOCX + Complex Tables)"
status: in_progress
priority: P1
effort: "3-4h"
dependencies: [4]
started_date: 2026-05-09
note: "Infrastructure complete. Gate run PENDING — Docling model download in progress."
---

# Phase 5: Accuracy Gate (PDF+DOCX + Complex Tables)

## Overview
**MANDATORY GATE.** Validate hybrid pipeline meets LandingAI-quality target on real-world docs. Test PDF (text + scanned), DOCX, and a complex-table benchmark. Decide whether to activate Phase 6 (PaddleOCR).

## Requirements

**Functional:**
- Text PDF: structural fidelity ≥98% (paragraphs, headings, reading order)
- Scanned PDF: OCR text accuracy ≥95% character-level on clean scans
- DOCX: 100% structural preservation (tables, headings, lists)
- **Complex tables** (borderless, merged cells, nested): cell-level accuracy measured

**Gate decision:**
- Complex-table cell accuracy ≥95% → SKIP Phase 6, proceed to Phase 7
- Complex-table cell accuracy <95% → ACTIVATE Phase 6 (PaddleOCR PP-StructureV3)

## Architecture

Test corpus structure:
```
test_corpus/
  ├── simple_pdf/           # 3-5 single-column text PDFs
  ├── scanned_pdf/          # 2-3 scanned docs (clean + noisy)
  ├── docx_samples/         # 2-3 DOCX with tables
  └── complex_tables/       # 3-5 PDFs with borderless/merged/nested tables
      └── ground_truth/     # hand-corrected JSON for cell-level diff
```

Accuracy measurement:
- **Structural:** diff Docling output vs hand-annotated ground truth (element count, types)
- **Tables:** cell-level F1 score (cell count, content match, merge detection)
- **OCR:** character error rate (CER) via Levenshtein

## Related Code Files

- **Create:** `tests/test_accuracy_gate.py`
- **Create:** `tests/lib/table_diff.py` (cell-level F1 computation)
- **Create:** `tests/lib/ground_truth_loader.py`
- **Create:** `test_corpus/` directory (samples committed; ground truth JSON checked in)
- **Create:** `plans/reports/accuracy-gate-260509-results.md` (gate decision document)

## Implementation Steps

1. Curate test corpus:
   - Pick 3-5 real PDFs user expects to process (or synthetic equivalents)
   - Hand-annotate complex-table ground truth (cells, content, merges)
2. Implement `table_diff.py` — cell-level F1: precision (Docling cells matching truth) + recall (truth cells found)
3. Implement `test_accuracy_gate.py` — runs auto_convert.sh on each corpus item, compares to truth
4. Run full gate suite, collect metrics
5. Write `accuracy-gate-260509-results.md` with:
   - Per-document scores
   - Aggregate metrics
   - Gate decision: PASS (skip Phase 6) or FAIL (activate Phase 6)
   - Specific failure modes if FAIL (which table types broke)
6. Commit decision and update plan.md status of Phase 6 (skip or activate)

## Success Criteria

- [ ] Test corpus assembled (≥10 docs total across categories)
- [ ] Ground truth annotated for complex tables
- [ ] Accuracy harness runs end-to-end
- [ ] Gate decision documented with metrics
- [ ] Phase 6 activated or formally skipped based on data

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| User has no representative docs yet | Use public benchmarks (FinTabNet, PubTables-1M samples) |
| Hand-annotation too time-consuming | Limit to 3 complex-table docs, semi-automate using Docling output as starting point |
| Gate fails on edge cases not user-relevant | Document which failure modes matter for user's use case before Phase 6 decision |
