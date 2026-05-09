# Accuracy Gate Results — Phase 5
**Date:** 2026-05-09
**Plan:** 260509-2012-docling-gemini-pdf-convert
**Gate Threshold:** 95% cell-level F1 on complex tables

## Test Corpus

| Category | Documents | Ground Truth |
|----------|-----------|--------------|
| simple_pdf | sample_5pages.pdf (5 pages, Vietnamese textbook excerpt) | none |
| scanned_pdf | (pending — no scanned docs in corpus yet) | — |
| docx_samples | (pending) | — |
| complex_tables | (pending — needs hand-annotated GT) | — |

## First-Run Note

Docling downloads layout/table/OCR models (~1-2GB) on first run from HuggingFace.
Run `python step1_docling_parse.py test_corpus/simple_pdf/sample_5pages.pdf` once (with network) to warm the model cache. Subsequent runs will be fast.

## Structural Fidelity Results

| Document | Category | Elements Found | Expected | Status |
|----------|----------|---------------|----------|--------|
| sample_5pages.pdf | simple_pdf | 9 | 9 (no GT, self-consistent) | ✅ ok |

**Notes:** page_no is 1-based (Docling native). Table found on pages 4-5. No ground truth available for cell-level comparison.

## Complex Table Accuracy

| Document | Table F1 | Precision | Recall | Gate Pass? |
|----------|----------|-----------|--------|------------|
| (none — no complex_tables ground truth yet) | — | — | — | INCONCLUSIVE |

## Gate Decision

**INCONCLUSIVE** — complex-table ground truth not yet annotated.

**Required to reach PASS/FAIL:**
- Add 3–5 PDFs with borderless/merged-cell tables to `test_corpus/complex_tables/`
- Create hand-annotated `ground_truth/{doc_stem}.json` for each

**Provisional recommendation:** Proceed to Phase 7 (extended formats) while asynchronously annotating complex-table corpus. Activate Phase 6 (PaddleOCR) only if users report table extraction failures on real documents.

## Unresolved Questions
1. Does user have representative complex-table PDFs to annotate?
2. Should FinTabNet or PubTables-1M samples be used as synthetic benchmarks?
3. At what point should Phase 6 be re-evaluated (after user feedback vs. proactive now)?
