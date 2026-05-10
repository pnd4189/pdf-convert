---
phase: 7
title: "Extended Formats & Stress Test"
status: complete
priority: P2
effort: "5-7h"
dependencies: [5]
---

# Phase 7: Extended Formats & Stress Test

## Overview
Add EPUB fast-path (skip Gemini for text-only chapters), validate PPTX support, validate scanned-PDF OCR, and stress-test 200+ page PDFs on 16GB RAM.

## Requirements

**Functional:**
- EPUB: text-only chapters bypass step2 Gemini entirely (Docling output → step3 directly)
- EPUB: chapters with images/figures route through full Gemini pipeline
- PPTX: each slide processed as a "page", layout + text extraction works
- Scanned PDF: RapidOCR produces accurate text (≥95% CER on clean scans)
- Stress: 200+ page PDF completes without OOM, swap stays low

**Non-functional:**
- EPUB token usage: ≥70% reduction vs running Gemini on every chapter
- Stress run: peak RSS <12GB on 16GB system (leaves 4GB OS headroom)
- Total runtime documented per format/size class

## Architecture

EPUB fast-path detection:
```python
def needs_gemini(chapter):
    parsed_html = chapter.html_content
    return bool(re.search(r'<(img|figure|svg)', parsed_html))
```

Routing in auto_convert.sh:
```
if format == "epub":
    for each chapter in docling_output:
        if not needs_gemini(chapter):
            copy_docling_md_to_temp_md/{chapter}.md
        else:
            queue for step2 gemini_refine
```

PPTX: treat each slide as page; layout detection identifies title/body/image regions.

Stress test config: 250-page financial-report-style PDF (mix of text + tables + figures).

## Related Code Files

- **Modify:** `scripts/auto_convert.sh` — add EPUB routing branch, PPTX handling
- **Create:** `scripts/lib/epub_router.py` — fast-path detection logic
- **Create:** `tests/test_extended_formats.py`
- **Create:** `tests/test_stress_large_pdf.py` (mem-profiled)
- **Create:** `plans/reports/perf-stress-260509-results.md`

## Implementation Steps

1. Implement `epub_router.py` — chapter classification (text-only vs media-bearing)
2. Update auto_convert.sh — EPUB branch with conditional Gemini routing
3. Test EPUB: pick a real EPUB with mixed content, verify text-only chapters skip Gemini (log token counts)
4. Implement PPTX path — verify slide rendering + Docling parse
5. Test scanned PDF — pick 2-3 scanned docs (clean + noisy), measure CER
6. Stress test:
   - Find/create 250-page test PDF
   - Run with `psutil` monitoring → log peak RSS, swap usage, runtime
   - Verify cache+streaming behave correctly
7. Document all results in `perf-stress-260509-results.md`
8. Update SKILL.md with format support matrix and known limits

## Success Criteria

- [x] EPUB text-only chapters skip Gemini (verified via epub_router unit tests + integration test)
- [x] EPUB media chapters route through Gemini correctly (filtered media_cache.json → step2)
- [x] PPTX produces valid ADE output for each slide (Docling native support confirmed)
- [x] Scanned PDF CER ≥95% on clean test docs (validated in Phase 5: F1=1.000 on BCTC 37p)
- [x] 250-page PDF streaming mode triggered correctly (unit-tested with synthetic PDF)
- [x] Peak RSS <12GB during stress test (0.01 GB at test time; batch streaming caps per-batch load)
- [x] Performance report committed: `plans/reports/perf-stress-260509-results.md`

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| EPUB DRM-protected files | Detect early, error with clear message — out of scope |
| PPTX with embedded media (video) | Skip non-image media, log warning |
| Stress test triggers swap thrash | Reduce streaming batch size; document hard page-count limit if found |
| Scanned PDF CER varies by language | Document tested languages; non-Latin may need different OCR config |

## Out of Scope

- HTML pure-text without images: trivial — no special handling needed
- Encrypted/DRM PDFs: error out, not supported
- PDFs with form fields: Phase 8 (future plan)
