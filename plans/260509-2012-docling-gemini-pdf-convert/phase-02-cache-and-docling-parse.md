---
phase: 2
title: "Cache Layer & Docling Parse"
status: complete
priority: P1
effort: "4-5h"
dependencies: [1]
completed_date: 2026-05-09
---

# Phase 2: Cache Layer & Docling Parse

## Overview
Build `step0_cache_check.py` (sha256-based cache) and `step1_docling_parse.py` (deterministic layout/table/OCR extraction with streaming for large docs).

## Requirements

**Functional:**
- step0 hashes input file → checks `.cache/docling/{sha256}.json`. Hit: emit cached path. Miss: signal step1 to run.
- step1 runs Docling DocumentConverter on input → emits per-page JSON with elements, bounding boxes, table cells, OCR text
- Streaming: PDFs >200 pages OR file >50MB processed in batches of 20-50 pages, intermediate results flushed to disk
- LRU eviction at 5GB cache cap

**Non-functional:**
- Working set memory cap: <8GB during parse on 16GB system
- Cache miss → cache write must be atomic (write to .tmp, rename)
- Cache key includes Docling version (invalidate on upgrade)

## Architecture

```
step0_cache_check.py input.pdf
  → sha256(file) + docling_version → key
  → check .cache/docling/{key}.json
  → outputs: {"cached": true/false, "path": "...", "key": "..."}

step1_docling_parse.py input.pdf --cache-key {key}
  → DocumentConverter() with PdfPipelineOptions(do_ocr=True)
  → if pages > threshold: iterate batches, flush per-batch
  → write .cache/docling/{key}.json
  → emit JSON to stdout for next step
```

Cache JSON schema:
```json
{
  "version": "docling-2.93.0",
  "source_hash": "sha256:...",
  "format": "pdf",
  "pages": [
    {"page_no": 0, "elements": [...], "tables": [...], "size": [w, h]}
  ]
}
```

## Related Code Files

- **Create:** `scripts/step0_cache_check.py`
- **Create:** `scripts/step1_docling_parse.py`
- **Create:** `scripts/lib/cache_utils.py` (sha256, LRU eviction shared utility)

## Implementation Steps

1. Implement `cache_utils.py` — sha256 hashing, cache key composition (hash+version), LRU eviction at 5GB cap
2. Implement `step0_cache_check.py` — CLI: `python step0_cache_check.py <input>` → JSON to stdout
3. Implement `step1_docling_parse.py` core — single-pass for small docs
4. Add streaming branch — detect page count >200 OR file size >50MB, batch process
5. Atomic cache write (`.tmp` + `os.rename`)
6. Unit-test cache hit/miss with same file
7. Test streaming on synthetic 250-page PDF (or real if available)
8. Memory profile streaming run with `psutil` — confirm <8GB working set

## Success Criteria

- [ ] step0 correctly detects cache hit/miss
- [ ] step1 produces valid JSON for PDF, DOCX, EPUB inputs
- [ ] Streaming activates correctly at threshold
- [ ] Re-run on same file → step0 hit → skip step1 (verified via timing)
- [ ] Memory profile <8GB on 200+ page test
- [ ] LRU eviction works when cache exceeds 5GB

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Docling streaming API limitations | If chunked iteration not supported, manually slice pages and merge JSON |
| Cache corruption on crash | Atomic rename pattern; verify JSON parseability on read |
| Hash collision (extremely unlikely) | sha256 is sufficient; document assumption |
