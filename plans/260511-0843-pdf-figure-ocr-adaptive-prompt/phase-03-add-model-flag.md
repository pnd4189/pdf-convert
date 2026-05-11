---
phase: 3
title: "Add Model Flag"
status: pending
priority: P2
effort: "5min"
dependencies: [2]
---

# Phase 3: Add Model Flag

## Overview
Add explicit Gemini model selection to `gemini_client.py` for consistent OCR quality across CLI updates.

## Requirements
- Explicit model flag: `-m gemini-2.5-flash`
- Configurable via env var `GEMINI_MODEL`
- No change to existing CLI invocation pattern

## Related Code Files
- Modify: `/home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/lib/gemini_client.py`

## Implementation Steps

1. Add model constant at module level (after line 17):
```python
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
```

2. Add import at top:
```python
import os
```

3. Modify `cmd` construction in `call_gemini()` (line 36):
```python
cmd = ["gemini", "-p", effective_prompt, "-m", GEMINI_MODEL, "--yolo", "--include-directories", "/tmp"]
```

## Success Criteria
- [ ] `-m gemini-2.5-flash` flag added to Gemini CLI invocation
- [ ] Model configurable via `GEMINI_MODEL` env var
- [ ] No change to retry logic or timeout handling

## Risk Assessment
**Minimal** — only adds model flag. If model name is wrong, fallback to env var.
