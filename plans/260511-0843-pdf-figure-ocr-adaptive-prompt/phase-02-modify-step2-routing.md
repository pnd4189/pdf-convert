---
phase: 2
title: "Modify Step2 Routing"
status: pending
priority: P1
effort: "15min"
dependencies: [1]
---

# Phase 2: Modify Step2 Routing

## Overview
Add threshold-based prompt routing in `step2_gemini_refine.py`. When Docling returns <=2 elements for a page, load `ade_prompt_vision.txt` instead of `ade_prompt_v2.txt`. Normal pages completely unaffected.

## Requirements
- Detect sparse Docling pages: `len(elements) + len(tables) <= VISION_THRESHOLD`
- Route to vision prompt for sparse pages
- Keep standard prompt for normal pages
- Include page dimensions from Docling `size` field in vision prompt
- Threshold configurable via env var `DOCLING_SPARSE_THRESHOLD` (default: 2)
- Zero regression on normal pages

## Architecture
```
step2_gemini_refine.py::_process_page()
    ↓
_trim_docling_page() → trimmed dict
    ↓
count = len(trimmed["elements"]) + len(trimmed["tables"])
    ↓
if count <= THRESHOLD:
    load ade_prompt_vision.txt
    prompt = vision_template.format(page_no=..., page_size=...)
else:
    load ade_prompt_v2.txt (existing path)
    prompt = standard_template.format(page_no=..., docling_data=...)
    ↓
call_gemini(prompt, image_path=png_path)
```

## Related Code Files
- Modify: `/home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/step2_gemini_refine.py`

## Implementation Steps

1. Add constants at module level (after line 23):
```python
VISION_THRESHOLD = int(os.environ.get("DOCLING_SPARSE_THRESHOLD", "2"))
VISION_PROMPT_PATH = Path(__file__).resolve().parent / "ade_prompt_vision.txt"
```

2. Load vision prompt template in `main()` (after line 102):
```python
vision_template = VISION_PROMPT_PATH.read_text(encoding="utf-8")
```

3. Modify `_process_page()` signature to accept vision template:
```python
def _process_page(
    page: dict,
    png_dir: Path,
    out_dir: Path,
    prompt_template: str,
    vision_template: str,  # NEW
) -> tuple[int, str]:
```

4. Add routing logic in `_process_page()` (after line 58):
```python
trimmed = _trim_docling_page(page)
is_sparse = len(trimmed["elements"]) + len(trimmed["tables"]) <= VISION_THRESHOLD

if is_sparse:
    page_size = trimmed.get("size", [0, 0])
    prompt = vision_template.format(
        page_no=page_no,
        page_size=f"[{page_size[0]}, {page_size[1]}]"
    )
else:
    docling_json = json.dumps(trimmed, ensure_ascii=False)
    prompt = prompt_template.format(page_no=page_no, docling_data=docling_json)
```

5. Remove old lines 59-61 (the unconditional prompt fill):
```python
# REMOVE these 3 lines:
docling_json = json.dumps(trimmed, ensure_ascii=False)
prompt = prompt_template.format(page_no=page_no, docling_data=docling_json)
```

6. Update `pool.submit` call to pass vision template:
```python
pool.submit(_process_page, page, png_dir, out_dir, prompt_template, vision_template)
```

7. Add log line for routing visibility:
```python
if is_sparse:
    print(f"[step2] page {page_no}: sparse ({len(trimmed['elements'])} elements) → vision prompt", file=sys.stderr)
```

## Success Criteria
- [ ] `VISION_THRESHOLD` constant with env var override
- [ ] Sparse pages (<=2 elements) routed to vision prompt
- [ ] Normal pages (>2 elements) use identical existing code path
- [ ] Page dimensions passed to vision prompt for coordinate grounding
- [ ] No changes to `_trim_docling_page()` or `call_gemini()`
- [ ] Log output shows which pages use vision prompt

## Risk Assessment
**Zero regression risk** — normal pages use identical code path. The only change is WHERE the prompt comes from for sparse pages.
