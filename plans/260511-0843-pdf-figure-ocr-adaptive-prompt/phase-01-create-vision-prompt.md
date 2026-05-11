---
phase: 1
title: "Create Vision Prompt"
status: pending
priority: P1
effort: "30min"
dependencies: []
---

# Phase 1: Create Vision Prompt

## Overview
Create `ade_prompt_vision.txt` — a pure vision OCR prompt for pages where Docling returns sparse data. Same ADE output format as `ade_prompt_v2.txt` but with image-first source priority and explicit OCR mandate.

## Requirements
- Same ADE output format: anchors with box coordinates, HTML tables, ontology entities
- Image as PRIMARY source (reversing Docling-primary from standard prompt)
- Explicit OCR mandate: transcribe ALL visible text character by character
- Clarify zero-hallucination: "does NOT mean skip content you can see"
- Grid/table anti-escape rule: forbid `<:: figure ::>` for readable text in grid layout
- Include page dimensions from Docling `size` field for coordinate grounding
- Few-shot example showing correct dense grid extraction

## Architecture
Prompt template uses same `{page_no}` placeholder. No `{docling_data}` placeholder — instead includes `{page_size}` for coordinate grounding.

## Related Code Files
- Create: `/home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/ade_prompt_vision.txt`
- Read for reference: `/home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/ade_prompt_v2.txt`

## Implementation Steps

1. Create `ade_prompt_vision.txt` with the following structure:

```
You are an ADE (Agentic Document Extraction) engine performing FULL OCR on a visual page.
You will receive: (1) the page PNG image.

**PAGE INFO (page {page_no}):**
Dimensions: {page_size}

**YOUR TASK:**
Perform exhaustive OCR of this page image. Extract ALL visible text into Visually Grounded Markdown.

**SOURCE STRATEGY:**
- The IMAGE is your ONLY source for ALL visible content
- You MUST transcribe EVERY piece of visible text from the image verbatim:
  - All small text in charts, diagrams, grids, astrological charts, mind maps
  - All Vietnamese, Chinese, CJK, and Latin characters
  - Every cell label, annotation, caption, and marginal note
  - Text within images, overlays, and complex visual layouts
- NEVER summarize or caption text-containing regions. TRANSCRIBE character by character.

**ZERO-HALLUCINATION RULE:**
Extract only what is visually present. No summarization. No inference.
But "zero hallucination" does NOT mean "skip content you can see." If you can read it, you must transcribe it.

---

## ANCHOR FORMAT
Before EVERY element insert:
`<a id='{page_no}-{{seq}}' box='[left, top, right, bottom]'></a>`
- Coordinates: 4 normalized floats [0.00–1.00] relative to page width/height
- ID sequence: {page_no}-1, {page_no}-2, {page_no}-3 ...

## TABLE FORMAT
- NEVER use Markdown `|---|` tables
- Use HTML `<table id='{page_no}-N'>` with `<td id='{page_no}-M'>` on every cell
- Cell IDs must be sequential, continuing from last anchor ID

## GRID/TEXT RULE
NEVER use `<:: ... : figure ::>` for content that contains readable text in a grid or tabular layout.
If the image shows text arranged in rows/columns (even without visible borders), you MUST create an HTML table.

## ONTOLOGY ENTITIES
Wrap non-text visual elements: `<:: [detailed description] : [type] ::>`
Valid types: figure, logo, scan_code, attestation, marginalia
Only use for truly non-text visual elements (logos, QR codes, decorative images).
Place anchor tag immediately before each ontology entity.

## BLANK PAGE
If page is genuinely empty: output exactly `<!-- TRANG TRỐNG - ĐÃ XÁC MINH -->`

---

**EXAMPLE: Dense grid image extraction**
For an image containing a grid of characters (e.g., astrological chart):
WRONG: `<:: Astrological chart with Chinese characters : figure ::>`
RIGHT: `<table id='X-N'><tr><td id='X-M'>甲子</td><td id='X-M+1'>乙丑</td>...</tr>...</table>`

---

Output ONLY the ADE Markdown for this page. No explanatory text before or after.
```

2. Verify prompt is self-contained (no references to Docling data)

## Success Criteria
- [ ] `ade_prompt_vision.txt` created with OCR mandate
- [ ] Same ADE output format as `ade_prompt_v2.txt`
- [ ] No reference to Docling as source
- [ ] Grid/text anti-escape rule included
- [ ] Few-shot example included

## Risk Assessment
**Low risk** — new file, no existing behavior affected. Prompt can be tuned independently.
