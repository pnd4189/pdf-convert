---
phase: 1
title: "Setup & Docling Install"
status: complete
priority: P1
effort: "2-3h"
dependencies: []
completed_date: 2026-05-09
---

# Phase 1: Setup & Docling Install

## Overview
Install and verify Docling + dependencies in skill venv. Pin versions for reproducibility. Smoke test on sample PDF/DOCX/EPUB.

## Requirements

**Functional:**
- Docling v2.93.0+ installed and importable from skill scripts
- RapidOCR (bundled with Docling) functional for scanned content
- Sample parse runs end-to-end on 3 format types

**Non-functional:**
- Total install size <3GB (models + deps)
- First-run model download cached to standard location (no re-download)
- Compatible with CPU-only (no CUDA required)

## Architecture

Use existing skill venv at `~/.claude/skills/.venv/` (or skill-local if needed). Add `requirements.txt` to scripts/ folder. Docling auto-downloads layout/table models on first import.

## Related Code Files

- **Create:** `pdf-vision-parser/scripts/requirements.txt`
- **Create:** `pdf-vision-parser/scripts/.cache/.gitignore` (excludes models, parses)
- **Modify:** `pdf-vision-parser/SKILL.md` (add install instructions)

## Implementation Steps

1. Create `requirements.txt`:
   ```
   docling==2.93.0
   docling-core>=2.0
   rapidocr-onnxruntime>=1.3
   pillow>=10.0
   ```
2. Install in skill venv: `~/.claude/skills/.venv/bin/pip install -r requirements.txt`
3. Verify imports: `python -c "from docling.document_converter import DocumentConverter; print('ok')"`
4. Create `.cache/docling/.gitignore` with `*` to exclude all cache contents
5. Smoke test: parse 1 sample PDF, 1 sample DOCX, 1 sample EPUB → confirm no errors, JSON output structure
6. Document install size (`du -sh ~/.cache/docling`) and update SKILL.md

## Success Criteria

- [ ] `requirements.txt` committed
- [ ] All deps install cleanly in venv
- [ ] Smoke test passes on PDF/DOCX/EPUB samples
- [ ] Disk usage measured and recorded
- [ ] SKILL.md updated with install steps

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Docling model download fails (network) | Pre-download in setup, document offline cache path |
| ONNX runtime conflicts with existing skills | Use isolated venv if conflicts arise |
| Install size exceeds 3GB budget | Check Docling minimal install options; document actual size |
