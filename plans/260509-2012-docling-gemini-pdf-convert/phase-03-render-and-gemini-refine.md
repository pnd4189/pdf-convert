---
phase: 3
title: "Page Render & Gemini Refine"
status: complete
priority: P1
effort: "4-6h"
dependencies: [2]
completed_date: 2026-05-09
---

# Phase 3: Page Render & Gemini Refine

## Overview
Build `step1.5_render_pages.py` (page→PNG for vision) and `step2_gemini_refine.py` (Gemini consumes Docling JSON + PNG → outputs ADE Markdown).

## Requirements

**Functional:**
- step1.5 renders each page to PNG (300 DPI) for PDF/PPTX. Skip for HTML/DOCX/EPUB unless figures present.
- step2 sends to Gemini per-page: structured Docling data (text + bboxes + table cells) + PNG → Gemini outputs ADE-formatted Markdown with anchors, ontology, grounding
- Gemini retries failed pages up to 3x with prompt variation
- Per-page output written to `temp_md/{page_no:04d}.md` — never accumulated in memory

**Non-functional:**
- Token efficiency: structured Docling input reduces vision-only token count by ~40%
- Concurrent Gemini calls: max 3 parallel (avoid rate limits)
- Each page batch independent — no inter-page state

## Architecture

```
step1.5_render_pages.py {cache_json} → temp_png/{NNNN}.png
  → uses pdf2image / pptx-rendering for PDF/PPTX
  → skips for EPUB/DOCX text-only (Phase 7 fast-path uses this signal)

step2_gemini_refine.py {cache_json} {png_dir}
  → for each page:
      prompt = ADE_TEMPLATE.format(
          docling_data=json.dumps(page_elements),
          page_no=N
      )
      response = gemini -p prompt --image {png_dir}/{N}.png --yolo
      write_file temp_md/{N}.md
```

Prompt structure (`ade_prompt.txt` v2):
- Provide Docling structured data as ground truth (anchors, table cells)
- Ask Gemini to: enrich with ontology labels, generate captions for figures, verify reading order
- Include grounding map: each text block must reference Docling element ID

## Related Code Files

- **Create:** `scripts/step1.5_render_pages.py`
- **Create:** `scripts/step2_gemini_refine.py`
- **Create:** `scripts/ade_prompt_v2.txt`
- **Create:** `scripts/lib/gemini_client.py` (subprocess wrapper for `gemini -p`, retry logic)

## Implementation Steps

1. Implement `step1.5_render_pages.py` — pdf2image for PDFs, python-pptx + Pillow for PPTX
2. Write `ade_prompt_v2.txt` — incorporate Docling structured data section
3. Implement `gemini_client.py` — subprocess wrapper, retry on empty/short response, timeout handling
4. Implement `step2_gemini_refine.py` — orchestrate per-page Gemini calls, concurrency cap=3
5. Test on 5-page sample PDF — verify output ADE structure
6. Test retry: simulate failed page → confirm retry triggers
7. Token comparison: measure tokens-per-page vs old vision-only pipeline → expect 30-40% reduction

## Success Criteria

- [ ] PNG render works for PDF and PPTX
- [ ] Gemini refine produces valid ADE Markdown with all required fields
- [ ] Concurrent calls capped at 3 (verified via logs)
- [ ] Retry logic triggers on empty page response
- [ ] Token reduction ≥30% vs vision-only baseline (measured)

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Gemini ignores Docling structured input | Test prompt variations; emphasize "use this as ground truth, do not re-extract" |
| PNG render slow for large PDFs | Render lazily per-batch alongside step2 calls |
| Gemini CLI rate limits with concurrency=3 | Backoff on 429; reduce to 2 if persistent |
| Prompt template too long | Trim Docling JSON to essentials per page (text + table cells, not full bboxes) |
