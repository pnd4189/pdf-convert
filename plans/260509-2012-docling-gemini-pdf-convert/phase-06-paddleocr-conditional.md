---
phase: 6
title: "PaddleOCR PP-StructureV3 (Conditional)"
status: pending
priority: P2
effort: "4-6h"
dependencies: [5]
---

# Phase 6: PaddleOCR PP-StructureV3 (Conditional)

## Overview
**CONDITIONAL — only execute if Phase 5 gate fails (<95% cell accuracy on complex tables).** Add PaddleOCR PP-StructureV3 as table-only post-processor; do NOT replace Docling for layout/text.

## Requirements

**Functional:**
- PaddleOCR runs only on Docling-detected table regions (not full pages)
- Output merged into Docling JSON: replace Docling table cells with PaddleOCR cells when confidence higher
- Re-run accuracy gate from Phase 5 → require ≥95% to mark phase complete

**Non-functional:**
- RAM impact +1-2GB (still <8GB working set on 16GB system)
- Disk +500MB-1GB for PaddleOCR models
- Optional: gate behind config flag `use_paddleocr_tables: true` for users on tighter RAM

## Architecture

```
step1_docling_parse.py → JSON with table bboxes
  → if config.use_paddleocr_tables AND tables present:
      step1.1_paddleocr_tables.py {cache_json}
        → for each table region: crop page image → PaddleOCR PP-StructureV3
        → merge cells back into cache JSON (with provenance: "source": "paddleocr")
  → continue to step1.5
```

Confidence-based merge: if Docling cell confidence < threshold OR PaddleOCR cell more complete (more text), prefer PaddleOCR.

## Related Code Files

- **Create:** `scripts/step1.1_paddleocr_tables.py` (only if activated)
- **Modify:** `scripts/auto_convert.sh` — add conditional step
- **Modify:** `scripts/requirements.txt` — add `paddleocr`, `paddlepaddle` (CPU)
- **Create:** `scripts/lib/table_merge.py` — confidence-based cell merging
- **Update:** `plans/reports/accuracy-gate-260509-results.md` (add post-PaddleOCR scores)

## Implementation Steps

1. Install PaddleOCR CPU build, verify import
2. Implement `step1.1_paddleocr_tables.py` — crop table regions, run PP-StructureV3, output cells JSON
3. Implement `table_merge.py` — merge logic with provenance tracking
4. Integrate into `auto_convert.sh` as optional step
5. Add config flag handling
6. Re-run Phase 5 accuracy gate harness — confirm ≥95% achieved
7. Memory profile combined Docling+PaddleOCR run on 200-page PDF
8. Update accuracy gate report with before/after scores

## Success Criteria

- [ ] PaddleOCR runs only on table regions, not full pages
- [ ] Re-run gate: complex-table cell accuracy ≥95%
- [ ] RAM working set <10GB on 200-page PDF
- [ ] Config flag works: disable → falls back to Docling-only tables
- [ ] Provenance tracked in output (which engine produced each cell)

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| PaddlePaddle install conflicts with ONNX | Use isolated venv; document install order |
| PaddleOCR worse than Docling on simple tables | Confidence-based merge keeps best of both |
| Phase 5 gate still fails after Phase 6 | Escalate: consider TableTransformer or manual fallback; document limitation |
| Memory pressure on 16GB | Process tables sequentially not parallel; document hard limits |

## Skip Condition

If Phase 5 gate PASSES (≥95% without PaddleOCR), this phase is **skipped** and marked completed-as-NA. Update plan.md accordingly.
