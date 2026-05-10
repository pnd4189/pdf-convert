# Brainstorm Report: Docling+Gemini Hybrid Architecture for PDF-Convert Skill

**Date:** 2026-05-09
**Last Updated:** 2026-05-09 (revision 2 — added accuracy gate, cache, EPUB fast-path, streaming)
**Status:** Agreed — proceeding to implementation planning
**Hardware Target:** GMK M6 Ultra, 16GB RAM, 500GB SSD, CPU-only

---

## Problem Statement

Current `pdf-convert` skill uses Gemini 3.1 Pro as sole worker for both layout parsing and content extraction. This works for simple single-column documents but will fail on complex multi-column layouts, borderless tables, and cannot handle non-PDF formats (EPUB, DOCX, PPTX).

Goal: LandingAI-quality output with deterministic layout parsing + LLM semantic reasoning.

## Evaluated Approaches

### Approach A: Gemini-Only (Current)

Pros: Zero deps, simple pipeline, fast
Cons: Reading order hallucination (multi-column), approximate bounding boxes, PDF-only, table quality unreliable
Verdict: Insufficient for stated requirements

### Approach B: Docling+Gemini Hybrid (CHOSEN)

LandingAI architecture: deterministic parse layer + semantic reasoning layer.

| Layer | Tool | Responsibility |
|-------|------|----------------|
| Parse | Docling | Layout detection, bounding boxes, table structure, reading order, OCR, multi-format support |
| Reasoning | Gemini 3.1 Pro | Ontology labeling, semantic enrichment, content verification, image description |

Pros: LandingAI architecture, precise bounding boxes, deterministic reading order, all formats (PDF/DOCX/PPTX/EPUB/HTML/Image), OCR included (RapidOCR), MIT license
Cons: ~2GB model download, ~30% slower than Gemini-only, more complex pipeline

### Approach C: OpenDataLoader+Gemini (REJECTED)

OpenDataLoader hybrid mode = Docling + EasyOCR + JVM overhead. No accuracy gain over Docling direct. Java dependency unnecessary. On 16GB RAM, JVM (~500MB-1GB) eats headroom needed for large-doc processing.

### Approach D: Docling+Gemini+PaddleOCR (DEFERRED)

PaddleOCR PP-StructureV3 for complex table extraction. Add only if Docling table accuracy (0.887 benchmark) proves insufficient in practice. Can be added later as post-processing step without pipeline changes.

## Final Architecture

```
step0_cache_check.py (NEW)
  → Hash input file (sha256) → check .cache/docling/{hash}.json
  → Hit: skip step1, load cached parse
  → Miss: proceed to step1, write cache after parse

step1_docling_parse.py (NEW)
  → Docling: any format → structured layout + bounding boxes + table structure + OCR
  → Output: per-page JSON with elements, coordinates, table cells
  → Streaming: PDFs >200 pages processed in batches of 20-50 pages
  → Write to .cache/docling/{hash}.json

step1.5_render_pages.py (NEW)
  → Render page images (PNG) for Gemini vision fallback
  → Only for formats where page rendering makes sense (PDF, PPTX)
  → Skipped for EPUB text-only chapters (fast-path)

step2_gemini_refine.py (NEW)
  → Gemini receives: Docling structured data + page PNG images
  → Gemini produces: ADE-formatted Markdown with anchors, ontology, grounding
  → Output: per-page .md files in temp_md/
  → EPUB fast-path: text-only chapters skip Gemini, only call for chapters with images/figures

step2.75_qa_sweep.py (REUSE)
  → Unchanged — validates ADE structure

step3_merge.py (MINOR UPDATE)
  → Package into final JSON with Grounding Map
```

### Caching Strategy
- Location: `.cache/docling/{sha256(file)}.json`
- Eviction: LRU, max 5GB (configurable)
- Benefit: re-running with tweaked Gemini prompts skips 30s-2min Docling parse

### EPUB Fast-Path
- EPUB has structural HTML already → Docling extracts cleanly
- Text-only chapters: skip step2 Gemini call → save tokens + latency
- Chapters with `<img>` or `<figure>`: full Gemini reasoning for descriptions/ontology
- Detection: scan parsed HTML for media tags

### Streaming for Large Docs
- Trigger: PDF >200 pages OR file size >50MB
- Batch size: 20-50 pages per Docling pass
- Memory cap target: <8GB working set (leaves headroom on 16GB system)

## Format Support Matrix

| Format | Docling Parse | Gemini Refine | Notes |
|--------|:---:|:---:|-------|
| PDF (text) | Yes | Yes | Primary use case |
| PDF (scanned) | Yes (RapidOCR) | Yes | OCR built into Docling |
| DOCX | Yes | Yes | Native Docling support |
| PPTX | Yes | Yes | Native Docling support |
| EPUB | Yes | Yes | Native Docling support |
| HTML | Yes | Yes | Native Docling support |
| Image | Yes (RapidOCR) | Yes | OCR + Gemini vision |

## Implementation Phases

### Phase 1: Core Pipeline (PDF + DOCX) + Accuracy Gate
- Install Docling, verify on sample docs
- Build step1_docling_parse.py with streaming support
- Build step0_cache_check.py (Docling output cache)
- Build step2_gemini_refine.py
- Update step3_merge.py for new input format
- Update auto_convert.sh shell wrapper
- Test with real PDF document (simple)
- Test with real DOCX document
- **ACCURACY GATE**: Test with 1 sample document containing complex tables (borderless/merged/nested cells). Measure cell-level accuracy.
  - ≥95% accuracy → proceed to Phase 2 with Docling alone
  - <95% accuracy → activate Phase 1.5 (PaddleOCR integration) BEFORE Phase 2
- Since user's future docs have unknown table complexity, this gate is mandatory.

### Phase 1.5: PaddleOCR PP-StructureV3 (CONDITIONAL)
- Only triggered if Phase 1 accuracy gate fails
- Add as post-processor for table elements only (not full re-parse)
- RAM impact: +1-2GB (still fits 16GB budget)

### Phase 2: Extended Formats + Scanned PDF
- Add EPUB support with fast-path (text-only chapters skip Gemini)
- Add PPTX support
- Test scanned PDF with RapidOCR
- Performance optimization (cache hit rate, streaming validation)
- Stress test: PDF >200 pages on 16GB RAM

## Machine Compatibility (GMK M6 Ultra, 16GB RAM, 500GB SSD)

| Component | RAM | Storage |
|---|---|---|
| Docling + RapidOCR (loaded) | 2-4GB | ~2GB models |
| Page rendering (PNG batch) | 0.5-1GB | transient |
| Docling cache (.cache/docling/) | — | up to 5GB (LRU) |
| OS + Claude Code + browser | 4-6GB | — |
| **Headroom for OS/swap avoidance** | **~5-8GB** | — |
| PaddleOCR (if Phase 1.5 triggered) | +1-2GB | +500MB-1GB |
| OpenDataLoader JVM (REJECTED) | +0.5-1GB | +200MB JRE |

- CPU-only: Docling uses ONNX runtime (CPU-friendly) → OK
- No GPU required → OK
- Total disk usage estimate: ~10GB (models + cache + temp working) — well within 500GB

## Risks

| Risk | Level | Mitigation |
|------|-------|-----------|
| Docling API breaking changes | Medium | Pin version, thorough testing |
| Table accuracy insufficient on user's future docs | **Medium-High** | **Mandatory accuracy gate at end of Phase 1; auto-trigger Phase 1.5 (PaddleOCR) if <95%** |
| Docling slow on CPU for large docs | Medium | Streaming batch processing, cache layer |
| RAM pressure on 16GB during large PDF | Medium | Streaming for >200 pages, swap monitoring |
| Cache disk bloat | Low | LRU eviction at 5GB cap |
| Gemini CLI integration with Docling output | Low | Shell wrapper constructs prompt with structured data |

## Unresolved Questions

1. What languages are scanned PDFs primarily in? (Affects OCR accuracy)
2. How many pages per typical document? (Affects batch sizing)
3. Should `--fast` mode (Gemini-only for simple docs) be kept as fallback?
4. Should Docling output be cached for re-processing without re-parsing?

## Sources

- Docling: github.com/docling-project/docling, MIT license, v2.93.0
- OpenDataLoader PDF: github.com/opendataloader-project/opendataloader-pdf, Apache-2.0
- PaddleOCR: github.com/PaddlePaddle/PaddleOCR, Apache-2.0
- Gemini Bounding Boxes: ai.google.dev/gemini-api/docs/bounding-boxes
- Previous research: `plans/reports/researcher-260509-1340-pdf-document-processing-tools.md`
- Previous research: `plans/reports/researcher-260509-2001-opendataloader-pdf-vs-paddleocr-scanned-pdf.md`
