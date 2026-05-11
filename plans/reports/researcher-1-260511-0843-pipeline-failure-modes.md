# Pipeline Failure Modes Report

**Date:** 2026-05-11
**Scope:** Docling+Gemini hybrid pipeline (`pdf-vision-parser`)
**Test case:** "Nhap mon tu hoa bac phai.pdf" (55 pages, heavy la so charts)

---

## Executive Summary

The pipeline has **6 systemic failure modes** that compound on image-heavy documents. The root cause chain: Docling produces near-zero elements for chart/diagram pages -> Gemini receives empty context -> Gemini hallucinates or captions-only output -> QA sweep cannot catch semantic loss -> merge propagates garbage. Additionally, cross-page duplication and header/footer pollution are systematic.

---

## Failure Mode Catalog

### FM-1: Docling Returns Zero/Near-Zero Elements for Image Pages (CRITICAL)

**Evidence:** Docling cache shows 10 pages with 0 elements across 55 pages (18% of document). Image-heavy pages (la so charts) produce at most 1 text element -- typically a caption that OCR'd from the image edge.

| Page | Elements | Tables | What's actually on page |
|------|----------|--------|------------------------|
| 1    | 0        | 0      | Cover page with image  |
| 5    | 1        | 0      | La so chart (90% image) |
| 7    | 0        | 0      | La so chart (100% image)|
| 12   | 0        | 0      | La so chart             |
| 17   | 0        | 0      | La so chart             |
| 22   | 0        | 0      | La so chart             |
| 24   | 0        | 0      | La so chart             |
| 26   | 0        | 0      | La so chart             |
| 30   | 0        | 0      | La so chart             |
| 39   | 0        | 0      | La so chart             |

**Root cause:** Docling uses `PdfPipelineOptions(do_ocr=True)` but its OCR layer (Tesseract-based) cannot parse structured Asian-script charts into text. Docling treats the entire chart as a picture but does NOT emit `FigureItem` or `ImageItem` element types. The `_page_to_dict()` function (`step1_docling_parse.py:102-140`) only serializes elements with non-empty `text` -- image-only regions produce no output at all.

**Impact:** When Docling returns `elements: []`, the Gemini prompt receives `"elements": [], "tables": []` as "ground truth". This is the single most damaging failure mode.

---

### FM-2: Empty Docling Data Conflicts with Prompt Instructions (CRITICAL)

**Evidence:** `ade_prompt_v2.txt:11` states: "Use the Docling data as your primary source for text content, table cells, and bounding boxes." When Docling data is empty, this instruction creates a contradiction: "use empty data as primary source" vs "extract this page".

**Data flow for empty pages:**
1. `step2_gemini_refine.py:58-59` -- `_trim_docling_page()` serializes `{elements: [], tables: []}` into JSON
2. `step2_gemini_refine.py:61` -- Prompt template fills `{docling_data}` with empty JSON
3. Gemini sees: "Here is your ground truth" followed by nothing
4. Gemini must rely entirely on the PNG image but is told to "use Docling data as primary source"

**Result:** Gemini produces inconsistent output:
- Page 5 (1 element): Gemini merged Docling's single caption with page 6 content, producing a hybrid page that contains text from TWO pages
- Page 7 (0 elements): Gemini produced only a text fragment + header/footer artifacts. The la so chart was completely lost -- no `<:: ... : figure ::>` ontology tag was generated
- Page 10 (4 elements): Gemini correctly produced a `<:: ... : figure ::>` tag because Docling had 4 text elements as context anchors

**Key insight:** The presence/absence of `<:: figure ::>` tags correlates directly with Docling element count. When Docling provides >= 2 elements, Gemini produces figure ontology tags. When Docling provides 0-1 elements, Gemini skips figure detection entirely.

---

### FM-3: Cross-Page Content Duplication (HIGH)

**Evidence:** 10 pairs of consecutive pages share duplicate content in final output.

**Docling-level duplicates** (source of the problem):
- Page 5 <-> 6: Docling page 5 element 0 text matches page 6 element 0 text identically
- Page 10 <-> 11: Same la so description text appears in both

**Root cause in data flow:**
1. Docling's PDF splitter sometimes assigns elements from a page boundary region to BOTH adjacent pages (duplicate bbox coordinates confirm this)
2. `step2_gemini_refine.py` processes each page independently with NO deduplication awareness
3. Gemini receives duplicate Docling text and faithfully reproduces it
4. `step3_merge.py` concatenates all pages without any cross-page dedup

**Impact:** Reading the final JSON, content from page N often appears verbatim in page N+1. For la so charts, the description text bleeds across 2-3 pages.

---

### FM-4: Header/Footer Artifact Pollution (HIGH)

**Evidence:** Every page in final output contains 3 garbage chunks: "Chien Nguyen" (author), a page number, and "Khosachquy.com". This adds ~90 noise chunks across 55 pages (approx 16% of total chunks).

**Pattern:**
```
Page 5 chunk 5-6: "Chiến Nguyễn"
Page 5 chunk 5-7: "6"
Page 5 chunk 5-8: "Khosachquy.com"
```

**Root cause:**
1. Docling OCR picks up header/footer text as `TextItem` elements with valid bboxes
2. The prompt (`ade_prompt_v2.txt`) has NO instruction to filter headers/footers
3. `step2_gemini_refine.py` has no pre-filtering or post-filtering
4. `step3_merge.py:39-54` `detect_type()` classifies these as `chunkText`
5. QA sweep (`step2.75_qa_sweep.py`) only validates anchor format, not content quality

**Why it matters for image-heavy pages:** When a page has only 1-2 real elements, the header/footer artifacts dominate the output. Page 7 has 4 total chunks -- 3 are header/footer, 1 is a text fragment. The actual content (la so chart) is 0%.

---

### FM-5: QA Sweep Does Not Validate Figure/Content Quality (HIGH)

**Evidence:** `step2.75_qa_sweep.py` checks only:
1. Anchor IDs exist and have normalized box coordinates (lines 62-75)
2. No Markdown tables used (lines 78-82)
3. HTML tables have cell-level IDs (lines 85-99)

**What it does NOT check:**
- Whether image-heavy pages produced figure ontology tags
- Whether content length is proportional to page visual complexity
- Whether cross-page duplicates exist
- Whether header/footer artifacts are present
- Whether a page with a chart produced meaningful content vs just a caption

**Result:** Pages 5, 7 pass QA with 100% score despite being nearly empty of meaningful content. The QA sweep validates structural format, not semantic quality.

---

### FM-6: Gemini Client Retry Logic Masks Extraction Failures (MEDIUM)

**Evidence:** `gemini_client.py:14` sets `MIN_RESPONSE_CHARS = 50`. If Gemini returns any response >= 50 chars, it's accepted.

For image-heavy pages, Gemini might return:
- A 60-char caption that captures nothing of the chart
- Header/footer text that exceeds 50 chars when combined

The retry logic (`gemini_client.py:29-61`) retries on empty/short responses but cannot distinguish between "Gemini produced a low-quality extraction" and "Gemini produced a good extraction." The retry suffix `[Retry {attempt}: ensure full ADE extraction]` is generic and does not address the image-heavy page context.

---

## Failure Compounding Chain

For a la so chart page (e.g., page 7), the failures chain as:

```
Docling: 0 elements (FM-1)
    --> Gemini receives empty ground truth (FM-2)
    --> Gemini produces caption-only output, no figure tag
    --> QA sweep passes because format is valid (FM-5)
    --> Merge adds header/footer artifacts (FM-4)
    --> Final output: 4 chunks, 0% chart content, 75% header/footer noise
```

---

## Architectural Gaps

| Gap | Location | Description |
|-----|----------|-------------|
| No page complexity detection | step1 output | Pipeline cannot distinguish text-heavy vs image-heavy pages |
| No adaptive prompting | step2 | Same prompt used regardless of Docling output quality |
| No deduplication | step3 | No cross-page content comparison |
| No content quality metrics | step2.75 | Only structural validation |
| No header/footer filter | All steps | Never addressed at any stage |
| No figure completeness check | step2.75 | Cannot verify charts were extracted |

---

## Recommendations Priority Matrix

| Priority | Fix | Effort | Impact | Risk |
|----------|-----|--------|--------|------|
| P0 | Adaptive prompt: detect empty Docling pages, switch to vision-only extraction mode | Low | High | Low |
| P0 | Post-extraction figure check: flag pages where Docling=0 elements and no `<:: figure ::>` tag | Low | High | None |
| P1 | Header/footer dedup: filter repeated short text at page edges using bbox position | Medium | High | Low |
| P1 | Cross-page dedup in step3: hash-based deduplication of identical chunks | Medium | Medium | Low |
| P2 | Page complexity classifier in step1.5: tag pages as text/image/mixed | Medium | Medium | Low |
| P2 | QA sweep content quality checks: min content length per page, figure tag required for image pages | Low | High | Medium |

---

## Unresolved Questions

1. **What is the minimum viable Gemini prompt for pure-vision extraction?** Need to test whether removing Docling reference entirely for empty pages produces better results than the current contradictory prompt.
2. **Header/footer detection heuristic:** Is bbox position (bottom 10% of page) sufficient, or do we need pattern matching on repeated content across pages?
3. **Cross-page dedup strategy:** Should dedup happen in step3 (merge) or as a separate step? Dedup at merge risks losing intentional page-spanning content.
4. **Figure completeness metric:** What defines "good enough" extraction for a la so chart? Full grid text? Structured data? Or is a descriptive caption acceptable?
