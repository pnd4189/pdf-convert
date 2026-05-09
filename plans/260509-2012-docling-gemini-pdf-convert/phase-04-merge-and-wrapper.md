---
phase: 4
title: "Merge Update & Shell Wrapper"
status: complete
priority: P1
effort: "3-4h"
dependencies: [3]
completed_date: 2026-05-09
---

# Phase 4: Merge Update & Shell Wrapper

## Overview
Update `step3_merge.py` for new Docling+Gemini input format. Build `auto_convert.sh` orchestrator. Wire up to `~/.gemini/commands/pdf-convert.toml`.

## Requirements

**Functional:**
- step3_merge consumes per-page MD from temp_md/ + Docling cache JSON → produces final ADE JSON with Grounding Map referencing Docling element IDs
- auto_convert.sh: single-command pipeline `step0 → (step1 if miss) → step1.5 → step2 → step2.75 → step3`
- Reuses existing step2.75 QA sweep unchanged
- TOML command calls auto_convert.sh with input path

**Non-functional:**
- Idempotent: re-run with same input uses cache, skips redundant work
- Progress output to stderr (terminal-visible), JSON results to stdout
- Cleanup temp_png/ and temp_md/ on success unless `--keep-temp` flag

## Architecture

```bash
auto_convert.sh INPUT_FILE [--fast] [--keep-temp]
  STEP=0: cache_check → CACHE_KEY, CACHED
  STEP=1: if !CACHED: docling_parse → write cache
  STEP=1.5: render_pages (skip for text-only EPUB — Phase 7)
  STEP=2: gemini_refine → temp_md/
  STEP=2.75: qa_sweep → fix-and-retry loop (max 3)
  STEP=3: merge → output.json
  CLEANUP: rm temp_png/ temp_md/ unless --keep-temp
```

Grounding Map structure:
```json
{
  "grounding_map": {
    "block_id_in_md": {
      "docling_element_id": "...",
      "page": N,
      "bbox": [x0, y0, x1, y1]
    }
  }
}
```

## Related Code Files

- **Create:** `scripts/auto_convert.sh`
- **Modify:** `scripts/step3_merge.py` (accept new input format with grounding)
- **Modify:** `~/.gemini/commands/pdf-convert.toml`
- **Modify:** `pdf-vision-parser/SKILL.md` (document new pipeline)

## Implementation Steps

1. Update `step3_merge.py`: read Docling cache + temp_md/ → emit JSON with grounding_map field
2. Write `auto_convert.sh` shell pipeline with set -euo pipefail
3. Add `--fast` flag handling: if set, skip Docling and use legacy step1_split (kept as fallback)
4. Add `--keep-temp` flag for debugging
5. Update `pdf-convert.toml` to invoke `bash /path/to/auto_convert.sh "{{args}}"`
6. End-to-end test: run on 10-page real PDF → verify final JSON has grounding_map, ADE structure intact, QA sweep passes
7. Cleanup verification: confirm temp dirs removed after successful run

## Success Criteria

- [ ] step3_merge emits valid JSON with grounding_map
- [ ] auto_convert.sh runs end-to-end on real PDF
- [ ] Re-run uses cache (timing: 2nd run >5x faster)
- [ ] QA sweep passes with 0 CRITICAL issues
- [ ] TOML command works from Gemini CLI: `/pdf-convert input.pdf` → output.json
- [ ] `--fast` fallback path works (Gemini-only legacy)

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| step2.75 QA expects old format | Adapter layer in step3 to emit fields step2.75 expects |
| Shell script POSIX vs bash inconsistencies | Use `#!/usr/bin/env bash`, test on target shell |
| TOML interpolation issues with paths containing spaces | Quote `{{args}}` properly in TOML |
| QA fix-loop infinite | Cap at 3 attempts, then warn and proceed |
