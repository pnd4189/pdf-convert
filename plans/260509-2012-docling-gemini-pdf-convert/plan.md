---
plan: 260509-2012-docling-gemini-pdf-convert
title: "Docling+Gemini Hybrid PDF-Convert (LandingAI ADE)"
status: in_progress
priority: P1
created: 2026-05-09
blocks: [project:260509-1246-pdf-convert-gemini-cli-autonomous]
---

# Plan: Docling+Gemini Hybrid PDF-Convert Skill

**Date:** 2026-05-09
**Status:** in_progress (phases 1-4 complete, phase 5 in_progress, phases 6-7 pending)
**Source:** `plans/reports/brainstorm-260509-1942-docling-gemini-hybrid-architecture.md` (rev 2)
**Target Skill:** `pdf-vision-parser` (path: `/home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/`)
**Hardware Target:** GMK M6 Ultra, 16GB RAM, 500GB SSD, CPU-only

---

## Goal

Replace Gemini-only pipeline with **Docling+Gemini hybrid** following LandingAI ADE pattern: deterministic layout parser (Docling) + semantic reasoner (Gemini 3.1 Pro). Support PDF/DOCX/PPTX/EPUB/HTML/Image with cache, streaming, and accuracy gate for complex tables.

## Key Decisions (from Brainstorm rev 2)

- **Reject** OpenDataLoader (JVM overhead, no quality gain)
- **Defer** PaddleOCR — only activate if Phase 5 accuracy gate fails (<95% cell-level on complex tables)
- **EPUB fast-path** — skip Gemini for text-only chapters
- **Cache layer** — `.cache/docling/{sha256}.json`, LRU 5GB cap
- **Streaming** — PDFs >200 pages or >50MB processed in 20-50 page batches

## Cross-Plan Relationship

This plan **blocks** `260509-1246-pdf-convert-gemini-cli-autonomous`. The autonomous shell wrapper from that plan will be redesigned here as `auto_convert.sh` integrating the new Docling step. Old plan should be archived after Phase 4 of this plan completes.

## Phases

| # | Phase | Status | Priority | Dependencies |
|---|-------|--------|----------|--------------|
| 1 | [Setup & Docling Install](phase-01-setup-docling.md) | complete | P1 | — |
| 2 | [Cache Layer & Docling Parse](phase-02-cache-and-docling-parse.md) | complete | P1 | 1 |
| 3 | [Page Render & Gemini Refine](phase-03-render-and-gemini-refine.md) | complete | P1 | 2 |
| 4 | [Merge Update & Shell Wrapper](phase-04-merge-and-wrapper.md) | complete | P1 | 3 |
| 5 | [Accuracy Gate (PDF+DOCX + Complex Tables)](phase-05-accuracy-gate.md) | in_progress | P1 | 4 |
| 6 | [PaddleOCR PP-StructureV3 (Conditional)](phase-06-paddleocr-conditional.md) | pending | P2 | 5 (gate fail) |
| 7 | [Extended Formats & Stress Test](phase-07-extended-and-stress.md) | pending | P2 | 5 (or 6) |

## Files Affected

### Create (in `pdf-vision-parser/scripts/`)
- `step0_cache_check.py` — sha256 hash + cache lookup
- `step1_docling_parse.py` — Docling parse with streaming
- `step1.5_render_pages.py` — Page→PNG rendering for Gemini vision
- `step2_gemini_refine.py` — Gemini ADE refinement consuming Docling JSON
- `auto_convert.sh` — pipeline orchestrator (replaces old plan's stub)
- `requirements.txt` — pin Docling + deps
- `.cache/docling/.gitignore` — exclude cache

### Modify
- `step3_merge.py` — accept new Docling+Gemini input format
- `~/.gemini/commands/pdf-convert.toml` — call new auto_convert.sh
- `SKILL.md` — document hybrid architecture

### Delete
- (none — keep old `step1_split.py` as fallback for `--fast` mode initially)

## Success Criteria (Plan-Level)

- [ ] All 7 (or 6 if PaddleOCR skipped) phases marked complete
- [ ] Single `/pdf-convert <input>` works for: PDF text, PDF scanned, DOCX, EPUB, PPTX, image
- [ ] Complex-table accuracy ≥95% cell-level (Phase 5 gate)
- [ ] 200+ page PDF processes within 16GB RAM without swap thrash
- [ ] Cache hit re-runs skip Docling parse (verified via timing)
- [ ] EPUB text-only chapters skip Gemini calls (verified via token count)

## Risks (Top-Level)

| Risk | Level | Owner Phase |
|------|-------|-------------|
| Docling table accuracy insufficient on user docs | Medium-High | 5 (gate) → 6 (mitigation) |
| RAM pressure on 200+ page PDFs | Medium | 2 (streaming), 7 (stress test) |
| Docling API breaking changes | Medium | 1 (pin version) |
| EPUB parsing edge cases (DRM, malformed) | Low | 7 |

## Unresolved Questions

1. Where to install Docling — global venv vs skill-local venv? (Phase 1 decides)
2. Should `--fast` mode keep old Gemini-only path as fallback? (Phase 4 decides)
3. Cache key — file hash only, or hash+Docling-version? (Phase 2 decides)
4. After Phase 4, should old plan `260509-1246` be archived or merged into journal? (decide before Phase 5)
