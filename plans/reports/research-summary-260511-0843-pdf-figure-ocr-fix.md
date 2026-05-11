# Research Summary: PDF Figure/Image OCR Fix

**Date:** 2026-05-11
**Team:** research-pdf-figure-ocr-260511 (3 researchers)
**Scope:** pdf-vision-parser figure/image OCR quality for dense text images (lá số, charts, diagrams)

---

## Executive Summary

**Consensus across all 3 researchers: Root cause is prompt instruction conflict when Docling returns empty data.** Solution A (Adaptive Prompt Selection) unanimously recommended.

Gemini CAN fully OCR lá số and other dense text images. The model is NOT the bottleneck. The bottleneck is the prompt telling Gemini "use Docling as primary source" when Docling has nothing, combined with "ZERO-HALLUCINATION" making Gemini afraid to transcribe visible text.

**Fix: ~40 LOC total.** One new prompt file + small change in step2_gemini_refine.py. Zero regression risk.

---

## Root Cause (Cross-Validated)

```
Docling: 0 elements for image pages (18% of pages in test doc)
    → step2 sends: "Docling ground truth: {elements: [], tables: []}"
    → Prompt says: "Use Docling as PRIMARY source"
    → Prompt says: "ZERO-HALLUCINATION"
    → Gemini reads: "Primary source = empty + don't invent anything"
    → Gemini plays safe: brief caption instead of full OCR
    → QA passes (format valid, content quality unchecked)
    → Result: 0% chart content extracted
```

**Evidence:** Pages 5, 7 (test doc) — Docling returned 0-1 elements. Final output: 41 words total for page 7. The lá số with hundreds of text elements was completely lost.

---

## Solution Recommendation: Adaptive Prompt Selection

### What to Build

**New file:** `scripts/ade_prompt_vision.txt` — pure vision OCR prompt
**Modified file:** `scripts/step2_gemini_refine.py` — threshold-based routing

### How It Works

```python
# In _process_page(), after _trim_docling_page():
VISION_THRESHOLD = 2  # configurable via env var
is_sparse = len(trimmed["elements"]) + len(trimmed["tables"]) <= VISION_THRESHOLD
prompt_file = VISION_PROMPT_PATH if is_sparse else PROMPT_TEMPLATE_PATH
prompt_template = prompt_file.read_text(encoding="utf-8")
```

Pages with <=2 Docling elements → vision prompt (OCR everything from image)
Pages with >2 Docling elements → standard prompt (unchanged)

### Why This Solution

| Dimension | Assessment |
|-----------|------------|
| Regression risk | **ZERO** — normal pages use identical code path |
| Generalization | **ALL** sparse page types (charts, scanned docs, any figure) |
| Implementation | ~40 LOC total, 1 new file + 1 modified file |
| QA/merge compat | **FULL** — output format identical (anchors, tables, ontology) |
| Grounding | **Preserved** — page dimensions from Docling `size` field included |
| Cost | **Negligible** — ~$0.01/page for full OCR on paid tier |

### Vision Prompt Key Design Points

Based on researcher-2's Gemini docs analysis:

1. **SOURCE STRATEGY: Image is PRIMARY, Docling is SUPPLEMENTARY**
2. **OCR MANDATE: Transcribe EVERY visible text character by character**
3. **Clarify ZERO-HALLUCINATION: "Does NOT mean skip content you can see"**
4. **GRID/TABLE RULE: Never use `<:: figure ::>` for readable text in grid layout — use HTML table**
5. **Same ADE output format: anchors, HTML tables, ontology entities**
6. **Include page dimensions from Docling `size` field** for coordinate grounding

---

## Secondary Findings (Important, Separate Work Items)

### P1: Header/Footer Pollution
- Every page adds 3 garbage chunks ("Chiến Nguyễn", page number, "Khosachquy.com")
- ~90 noise chunks = 16% of total
- On image-heavy pages, artifacts dominate (page 7: 75% header/footer)
- Fix: bbox position filter in step3 merge (bottom 10% of page)

### P1: Cross-Page Content Duplication
- 10 pairs of consecutive pages share duplicate content
- Docling assigns boundary elements to both pages
- No dedup anywhere in pipeline
- Fix: hash-based dedup in step3 merge

### P2: QA Sweep Content Quality Gap
- `step2.75_qa_sweep.py` only validates format (anchors, table IDs)
- Never checks: figure extraction completeness, content length vs page complexity
- Fix: add min content length check + figure tag requirement for sparse Docling pages

### P2: Gemini Model Configuration
- `gemini_client.py` doesn't set `-m` flag → relies on CLI default model
- Recommend adding `-m gemini-2.5-flash` or `-m gemini-3-flash-preview`
- Gemini 3 Flash: 1120 image tokens at default (vs 256 for older models)
- Consider `media_resolution=HIGH` if switching to SDK (medium-term)

---

## What Solution A Does NOT Fix (By Design)

1. **Mixed-content pages** (text + large figures with text) — still use standard prompt. May need weaker "also OCR figures" instruction in standard prompt too (separate enhancement)
2. **Header/footer artifacts** — needs separate filter in step3
3. **Cross-page duplication** — needs separate dedup logic in step3

---

## Implementation Priority

| Priority | Item | Effort |
|----------|------|--------|
| **P0** | Create `ade_prompt_vision.txt` with OCR mandate | 30 min |
| **P0** | Modify `step2_gemini_refine.py` for threshold routing | 15 min |
| **P0** | Test with "Nhập môn tứ hóa bắc phái.pdf" (pages 5, 7) | 15 min |
| P1 | Add model flag to `gemini_client.py` | 5 min |
| P1 | Header/footer filter in step3 | 1-2 hr |
| P2 | Cross-page dedup in step3 | 1-2 hr |
| P2 | QA sweep content quality checks | 30 min |

---

## Unresolved Questions

1. Which Gemini model does `gemini -p` CLI default to? Need test call to verify.
2. Max output tokens for CLI mode — dense OCR could produce 5000+ tokens, risk of silent truncation.
3. Mixed-content pages — should standard prompt also get "OCR figures" instruction?
4. Threshold value — start at 2, but needs empirical tuning across different document types.
5. Whether Docling ever reports `FigureItem`/`ImageItem` types (researcher-1 found it doesn't for Asian-script charts, but may for Western-style figures).

---

## Source Reports

- [Researcher 1: Pipeline Failure Modes](researcher-1-260511-0843-pipeline-failure-modes.md)
- [Researcher 2: Gemini Vision OCR Best Practices](researcher-2-260511-0843-gemini-vision-ocr-best-practices.md)
- [Researcher 3: Solution Evaluation](researcher-3-260511-0843-solution-evaluation.md)
