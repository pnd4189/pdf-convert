---
title: "PDF Figure/Image OCR Fix - Adaptive Prompt Selection"
description: "Fix figure/image OCR quality in pdf-vision-parser by adding adaptive prompt selection — when Docling returns empty/light data for a page, switch to a pure vision OCR prompt"
status: complete
priority: P1
created: 2026-05-11
blockedBy: []
blocks: []
research: plans/reports/research-summary-260511-0843-pdf-figure-ocr-fix.md
---

# PDF Figure/Image OCR Fix - Adaptive Prompt Selection

**Date:** 2026-05-11
**Source:** Research by 3-agent team (see `plans/reports/research-summary-260511-0843-pdf-figure-ocr-fix.md`)
**Target:** `pdf-vision-parser` at `/home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/`
**Sync copy:** `/home/dung/VIBE_CODING/skill/pdf-vision-parser/`

## Problem

When Docling returns 0-1 elements for image-heavy pages (charts, lá số, diagrams), Gemini receives empty "ground truth" + conflicting prompt ("use Docling as primary source" + "zero hallucination"). Result: brief captions instead of full OCR. 18% of pages in test doc affected.

## Solution

Adaptive prompt selection: detect sparse Docling pages (<=2 elements), switch to pure vision OCR prompt. Normal pages unchanged.

## Phases

| Phase | Name | Status | Effort |
|-------|------|--------|--------|
| 1 | [Create Vision Prompt](./phase-01-create-vision-prompt.md) | Done | 30min |
| 2 | [Modify Step2 Routing](./phase-02-modify-step2-routing.md) | Done | 15min |
| 3 | [Add Model Flag](./phase-03-add-model-flag.md) | Done | 5min |
| 4 | [Test with Problematic PDF](./phase-04-test-with-problematic-pdf.md) | Done | 15min |
| 5 | [Fix Off-by-One Bug](./phase-01-create-vision-prompt.md) | Done (bonus) | 5min |

## Key Files

| File | Action |
|------|--------|
| `scripts/ade_prompt_vision.txt` | CREATE |
| `scripts/step2_gemini_refine.py` | MODIFY |
| `scripts/lib/gemini_client.py` | MODIFY |

## Dependencies

None. This is a focused fix on the existing pipeline.

## Risk

- **Regression risk:** ZERO — normal pages use identical code path
- **Edge case:** Mixed-content pages (>2 Docling elements but also large figures) stay on standard prompt. Acceptable for now.
