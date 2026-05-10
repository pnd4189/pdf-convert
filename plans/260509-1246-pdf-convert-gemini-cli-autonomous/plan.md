# Plan: PDF-Convert Skill — Gemini CLI Autonomous Mode

**Date:** 2026-05-09
**Status:** superseded
**Scope:** Add autonomous shell wrapper to pdf-vision-parser skill for Gemini CLI
**Superseded By:** `260509-2012-docling-gemini-pdf-convert` — architecture changed from Gemini-only to Docling+Gemini hybrid. Shell wrapper concept absorbed into Phase 4 of new plan.
**BlockedBy:** [project:260509-2012-docling-gemini-pdf-convert]

---

## Problem

Current `pdf-convert` skill requires manual "Tiếp tục" every 5-10 pages due to context overflow in interactive mode. Need fully autonomous pipeline for Gemini CLI (Ultra plan, no quota limits).

## Architecture Decision

**Shared scripts, separate orchestration:**
- Python scripts at `/home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/` — shared by both platforms
- Gemini CLI: `~/.gemini/commands/pdf-convert.toml` → shell wrapper → headless batches
- Antigravity: `.agent/workflows/pdf-convert.md` — unchanged (manual mode)

**Antigravity stays as-is.** Manual "Tiếp tục" is inherent to interactive IDE with ~200K context. Shell wrapper only works in terminal (Gemini CLI).

## Files to Create

### 1. `scripts/auto_convert.sh` (NEW — ~100 lines)

Shell wrapper for Gemini CLI autonomous pipeline.

```
Pipeline:
  Step 1: step1_split.py → PDF to PNG 300DPI
  Step 2: Loop batches of 5 pages → gemini -p "ADE extraction" --yolo
  Step 2.5: Check empty pages → retry failed pages
  Step 2.75: step2.75_qa_sweep.py → QA audit
  Step 3: step3_merge.py → Final JSON with Grounding Map
```

Key design decisions:
- **5 pages/batch**: 45K tokens per batch (4.5% of 1M context), no overflow risk
- **Write to disk only**: `write_file` per page, never echo to chat
- **Auto-retry**: Empty/short pages reprocessed with different prompt (up to 3 retries)
- **QA loop**: If QA sweep finds CRITICAL issues, auto-fix via Gemini then re-run QA
- **Progress tracking**: Print batch progress to terminal, final summary

### 2. `scripts/ade_prompt.txt` (NEW — extraction prompt template)

Template with placeholders for batch range:
- Full ADE discipline (anchors, coordinates, HTML tables, ontology)
- Zero-hallucination rules
- Zero-based page indexing
- Example extraction for reference

## Files to Update

### 3. `~/.gemini/commands/pdf-convert.toml` (UPDATE)

Replace manual agentic workflow with single shell command:
```
!{bash /path/to/auto_convert.sh "{{args}}"}
```

## Files Unchanged

- `SKILL.md` — ADE discipline reference (both platforms read this)
- `step1_split.py` — Already autonomous
- `step2.75_qa_sweep.py` — Already autonomous
- `step3_merge.py` — Already autonomous
- `pdf-convert.md` workflow — Antigravity manual mode (no changes needed)

## Quality Strategy (Ultra Plan)

| Parameter | Value | Why |
|-----------|-------|-----|
| Batch size | 5 pages | 4.5% context, no overflow, quality > speed |
| Model | gemini-3.1-pro (default) | Highest quality |
| Retries | 3 per failed page | Auto-recovery without manual intervention |
| QA loop | Auto-fix + re-run | 0 CRITICAL issues required before merge |
| Page-by-page write | write_file per page | No context accumulation |

## Implementation Steps

1. Create `ade_prompt.txt` with extraction prompt template
2. Create `auto_convert.sh` with full pipeline logic
3. Update `pdf-convert.toml` to call shell wrapper
4. Test with a real PDF document
5. Verify output JSON matches expected ADE format

## Success Criteria

- Single `/pdf-convert` command → auto-complete → no manual input
- 100-page PDF processes without context overflow
- Output JSON passes step2.75 QA sweep with 0 CRITICAL issues
- Antigravity workflow still works unchanged

## Risks

| Risk | Level | Mitigation |
|------|-------|-----------|
| `gemini -p` tool access in headless | Low | Verified: YOLO mode gives full tool access |
| Prompt template too long for `-p` | Low | `ade_prompt.txt` ~2KB, well within limits |
| Empty page false positives | Medium | Check both file size AND content length |
| QA auto-fix loop runs forever | Low | Cap at 3 fix attempts, then report and continue |

## Unresolved Questions

1. Should `auto_convert.sh` support non-PDF inputs (EPUB, DOCX, images) in this iteration or later?
2. Should there be a `--dry-run` flag that shows what would be processed without executing?
3. Should progress be written to a state file for resuming interrupted runs?
