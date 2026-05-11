# Solution Evaluation: Figure/Image OCR in pdf-vision-parser

**Date:** 2026-05-11
**Scope:** Evaluate 3 proposed solutions for extracting dense text from figures/charts scanned as images (Docling returns empty/light data, Gemini prompt instructs "use Docling as primary source" so Gemini defers to empty data instead of OCR-ing the image)

## Executive Summary

**RECOMMENDED: Solution A (Adaptive Prompt Selection)** -- best balance of quality, generalization, and regression safety. Detects empty Docling pages in step2, swaps to a pure-vision OCR prompt. ~40 LOC change, single file (`step2_gemini_refine.py`), zero regression risk on text-heavy pages.

---

## Root Cause Analysis

The problem is an instruction conflict in `ade_prompt_v2.txt` line 11:
```
Use the Docling data as your primary source for text content
```

When Docling returns `elements: []` for a scanned figure page, Gemini follows the instruction to use Docling as primary source, resulting in empty/minimal output. The PNG is there (`step1.5_render_pages.py` renders all pages), the image is passed to Gemini, but the prompt biases Gemini away from visual OCR.

This affects ANY page where Docling finds no text -- not just "la so" but also: scanned documents, image-only pages, diagrams with text, photos with captions, flowcharts, infographics.

---

## Comparison Matrix

| Dimension | A: Adaptive Prompt | B: Prompt-Only Fix | C: Docling Bypass |
|---|---|---|---|
| **Implementation** | ~40 LOC, 1 file + 1 new prompt | ~10 LOC, 1 file | ~30 LOC, 1 file |
| **Generalization** | ALL empty/light pages | Only pages Gemini "recognizes" as figures | ALL empty pages |
| **Regression risk** | ZERO (normal pages unchanged) | MEDIUM (prompt wording change affects all pages) | LOW (only empty pages bypassed) |
| **Extraction quality** | HIGH (pure vision prompt optimized for OCR) | MEDIUM (conflicting instructions: "use Docling" + "except when figure") | HIGH (pure OCR) |
| **Token cost** | Same (same # pages processed) | Same | **Lower** (no empty JSON sent) |
| **Maintainability** | GOOD (clean separation of concerns) | POOR (prompt becomes conditional soup) | GOOD (clean bypass) |
| **QA/merge compat** | FULL (output format identical) | FULL | PARTIAL RISK (no Docling bboxes for grounding) |
| **Edge cases** | HANDLED (threshold-based detection) | FRAGILE (relies on Gemini judgment) | MISSES mixed-content pages |

---

## Detailed Analysis

### Solution A: Adaptive Prompt Selection

**How it works:**
In `_process_page()` (`step2_gemini_refine.py:50-81`), after `_trim_docling_page()`:
1. Count elements in trimmed page: `len(trimmed["elements"]) + len(trimmed["tables"])`
2. If count <= threshold (e.g., 2), load alternative prompt `ade_prompt_vision.txt`
3. Vision prompt: "OCR this page image in full. Extract ALL text verbatim. Output ADE markdown with anchors."
4. Normal pages: unchanged path

**Implementation points:**
```python
# step2_gemini_refine.py, inside _process_page(), after line 58
VISION_THRESHOLD = 2  # pages with <=2 Docling elements use vision prompt
VISION_PROMPT_PATH = Path(__file__).resolve().parent / "ade_prompt_vision.txt"

trimmed = _trim_docling_page(page)
is_sparse = len(trimmed["elements"]) + len(trimmed["tables"]) <= VISION_THRESHOLD
prompt_file = VISION_PROMPT_PATH if is_sparse else PROMPT_TEMPLATE_PATH
prompt_template = prompt_file.read_text(encoding="utf-8")
```

**Pros:**
- Zero regression: normal pages use identical prompt path
- Clean abstraction: two prompts, each optimized for its use case
- Generalizes to ALL sparse pages (scanned docs, image pages, any figure type)
- QA sweep (`step2.75`) and merge (`step3`) see identical output format -- fully compatible
- Vision prompt can be tuned independently without affecting text pages
- Docling bbox data still available for pages where elements exist (even if sparse)

**Cons:**
- New file to maintain (`ade_prompt_vision.txt`)
- Threshold tuning needed (recommend 2 as starting point)
- For pages with 1-2 Docling elements (e.g., a figure with a small caption), the vision prompt ignores those elements -- acceptable since the PNG contains everything

**Edge cases handled:**
- Page with 0 elements (pure image): vision prompt
- Page with 1-2 elements (figure + caption): vision prompt captures everything
- Page with mixed text+figures (>2 elements): stays on standard prompt
- Text-only EPUB pages: unaffected (already have EPUB fast-path in step1.7)

### Solution B: Prompt-Only Fix

**How it works:**
Modify `ade_prompt_v2.txt` to add a conditional instruction like:
```
CRITICAL EXCEPTION: If the Docling data for this page contains 0 or very few text elements,
AND the image contains dense text (charts, diagrams, scanned figures),
disregard Docling data and perform full deep-OCR on the image.
```

**Pros:**
- Smallest change (~5 lines in prompt)
- No code changes

**Cons:**
- **Prompt instruction conflict**: "Use Docling as primary source" then "except when..." degrades instruction clarity for ALL pages
- **Relies on Gemini's judgment** to detect "dense text in figures" -- unreliable, inconsistent across calls
- **No threshold control**: can't tune detection sensitivity
- **Regression risk**: adding more conditional instructions to an already-detailed prompt increases hallucination risk on normal pages
- **Difficult to debug**: when extraction fails, was it the prompt condition? Gemini's interpretation?
- **Doesn't address root cause**: Docling empty data is still sent, wasting tokens on empty JSON

**Verdict: NOT RECOMMENDED.** Quick but fragile. Adds complexity to the one file (prompt) that should stay simple and deterministic.

### Solution C: Docling Bypass Mode

**How it works:**
When Docling returns 0 elements, skip the Docling JSON entirely in the prompt:
```python
if not trimmed["elements"] and not trimmed["tables"]:
    docling_json = "{}"  # or omit the Docling section entirely
```

**Pros:**
- Clean separation: truly empty pages get pure-vision treatment
- Lower token cost (no empty JSON in prompt)
- No prompt changes needed

**Cons:**
- **Loses grounding coordinates**: Docling `size` field (page dimensions) is lost. Step3 merge relies on normalized coordinates [0.00-1.00]. Without page size, Gemini must estimate coordinates blind -- lower quality bounding boxes
- **Binary detection**: only triggers on 0 elements. Misses pages with 1-2 elements (figure + caption recognized by Docling but main image content missed)
- **Prompt still says "Use Docling as primary source"**: even with empty `{}`, the instruction creates confusion. Need prompt changes anyway
- **step3 merge grounding**: `_build_grounding_map()` uses Docling element IDs to enrich anchor IDs. Bypassing Docling means no enrichment for these pages

**Verdict: Good idea, incomplete execution.** The coordinate/grounding loss is significant for the ADE standard.

---

## Recommendation: Solution A

### Rationale

1. **Root cause alignment**: The problem is that Gemini is told to defer to empty Docling data. Solution A directly fixes this by not telling Gemini to defer when data is empty.

2. **No false precision**: Solution B tries to make Gemini detect figures via prompt instructions -- adding ambiguity to a system that needs determinism. Solution A uses a concrete, measurable signal (element count) to route.

3. **Grounding preservation**: Unlike Solution C, the vision prompt can still include page dimensions from Docling `size` field even when elements are empty. This preserves coordinate quality for step3 merge.

4. **Testability**: Can write unit tests for the threshold detection. Can't test "did Gemini interpret my exception correctly."

5. **Incremental improvement**: Start with threshold=2, measure results, adjust. Clean feedback loop.

### Implementation Outline

**Files to create:**
1. `scripts/ade_prompt_vision.txt` -- pure vision OCR prompt, same ADE output format (anchors, tables, ontology entities)

**Files to modify:**
1. `scripts/step2_gemini_refine.py` -- add threshold detection + prompt routing in `_process_page()`

**Estimated LOC:** ~40 (30 in prompt file, 10 in Python)

**Vision prompt template** should include:
- Page number placeholder `{page_no}`
- Page dimensions from Docling `size` (even if elements empty)
- Same ADE anchor format instruction
- Same table HTML format instruction
- "OCR this image completely" as primary instruction (replacing "Use Docling as primary source")
- Same ontology entity format
- Same blank page handling

**Threshold tuning:**
- Start at 2 elements
- Monitor: if pages with 3-4 elements still have missing figure text, raise to 3-4
- Can make configurable via env var: `DOCLING_SPARSE_THRESHOLD=2`

---

## Unresolved Questions

1. **Mixed-content pages**: A page with 5 text elements AND a large figure with text. Current threshold would keep it on standard prompt. Should the standard prompt also get a weaker "also OCR figures" instruction? Or is this a separate enhancement?

2. **Token cost of vision prompt vs standard prompt**: Need empirical measurement. Vision prompt may be longer (more OCR-specific instructions) but processes same image. Net impact likely neutral.

3. **Gemini model version sensitivity**: Does the vision prompt need tuning per Gemini model? Current pipeline uses `gemini` CLI which may update underlying model. The prompt should be model-agnostic.

4. **Threshold vs content-aware detection**: Element count is a proxy for "is this page visual-heavy?" Could also check Docling element types (if all elements are `FigureItem` type, route to vision). This would be more precise but requires Docling to report figure types -- need to verify Docling's behavior here.

---

**Status:** DONE
**Summary:** Evaluated 3 solutions for figure OCR extraction failure. Root cause is prompt instruction conflict ("use Docling as primary" + empty Docling data). Solution A (adaptive prompt selection) recommended: threshold-based routing in step2, new vision prompt for sparse pages, zero regression risk on text pages.
