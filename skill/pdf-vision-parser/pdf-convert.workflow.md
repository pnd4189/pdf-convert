---
description: Convert PDF documents to Visually Grounded Markdown and JSON with Grounding Map. Wraps pdf-vision-parser skill (Landing.AI ADE Standard).
---

# /pdf-convert - PDF to Structured JSON Converter (ADE Standard)

$ARGUMENTS

---

## Purpose

Activate the `pdf-vision-parser` skill to convert complex PDF documents into
Visually Grounded Markdown with normalized coordinate anchors and Cell-level
Grounding, then package into a JSON structure with a separate Grounding Map
(top_level, split_level, chunk_level, grounding).

---

## Behavior

When `/pdf-convert` is triggered:

1. **Load Skill** — read `pdf-vision-parser/SKILL.md` and follow ALL its
   constraints and extraction disciplines. SKILL.md is authoritative; this
   workflow only sequences it.

2. **Validate Input** — the user provides a PDF (or DOCX/PPTX/EPUB/HTML/Image)
   path. If none, ask: "Vui lòng cung cấp đường dẫn file cần chuyển đổi." Verify
   it exists.

3. **Execute the agentic workflow below.** This is non-interactive: never pause
   to wait for the user to type "Tiếp tục" — process every page in one run.

---

### Step 1: Tiền xử lý (deterministic — KHÔNG gọi model/API)

- Run `bash <skill-path>/scripts/prepare_native_workspace.sh "<input>" --name "<output_name>" --keep-temp`.
- **If the workspace `/tmp/pdf_convert_<output_name>/` already has
  `native_manifest.json` (a batch wrapper pre-prepared it), SKIP this step** —
  just read the existing manifest and go to Step 2. Do not re-run prepare and do
  not change `<output_name>`.
- The script renders/caches deterministically and writes `native_manifest.json`.
  Read it for `png_dir`, `md_dir`, `pages`, `visual_candidates`,
  `skip_native_extraction`.
- **PNG là 1-indexed, zero-padded:** `0001.png`, `0002.png`, …

### Step 2: Bóc tách thị giác — Native Vision Loop (ADE Standard)

- **FIRST, before extracting any page:** read
  `<skill-path>/scripts/ade_prompt_vision.txt` — the canonical MANDATORY OUTPUT
  CONTRACT with a byte-correct worked example. Substitute
  `__PNG_DIR__`/`__MD_DIR__`/`__NPAGES__` from the manifest and apply it
  verbatim to every page. When in doubt, the template's format wins over prose.
- The active agy model uses native `view_file` to open each `png_dir/000N.png`
  and writes Markdown to `md_dir/page_X.md`. NO subprocess, NO external model.
- **Quy ước số trang (chống lệch — page IDs are zero-based):** the Markdown file
  `page_X.md` holds page id `X` (zero-based) and corresponds to image number
  `X+1`. So `page_0.md ↔ 0001.png`, `page_9.md ↔ 0010.png`. Do not drift this
  mapping.
- First line of every file MUST be `<!-- VISION_SOURCE: <png_path> -->` to prove
  the page came from the rendered image.
- Process in chunks of ~5-10 pages; release each page after writing so large
  documents never overflow context. Skip pages whose valid `page_X.md` already
  exists (resume).
- Apply the **Kỷ luật trích xuất ADE** from SKILL.md: zero-based sequential IDs
  `<a id='0-1' box='[left,top,right,bottom]'></a>`, normalized float coords
  (0.00–1.00, never pixels), HTML `<table>` with cell-level IDs (no Markdown
  tables), expanded ontology `<:: [description] : [figure|logo|scan_code|attestation|marginalia] ::>`.
- Every page listed in `native_manifest.json.visual_candidates` MUST be opened
  and described in visual detail.

### Step 2.5: Kiểm tra trang trống (MANDATORY)

- Scan `.md` files for empty/short content; re-verify against the PNG with
  `view_file`. Mark truly blank pages `<!-- TRANG TRỐNG - ĐÃ XÁC MINH -->`;
  re-extract any genuinely missed content.

### Step 2.75: ADE QA Sweep (MANDATORY)

- Run `python3 <skill-path>/scripts/step2.75_qa_sweep.py --md-dir <md_dir> --manifest <manifest>`.
- Exit `0` = pass, `1` = HARD fail (anchor/box/table/vision-provenance — must
  repair the flagged pages and re-run), `2` = SOFT-only (figure/keyword —
  acceptable, may proceed).
- Fix all HARD issues by reopening the affected pages, then re-run until no HARD
  fail.

### Step 3: Tổng hợp — Merge to JSON with Grounding Map

- Run `python3 <skill-path>/scripts/step3_merge.py --name "<output_name>" --md-dir <md_dir>`.
- Output: `/home/dung/ANTIGRAVITY/SÁCH CONVERT/<output_name>.json`. Verify it
  exists, size > 0, parses as JSON before any cleanup.

> **Batch / wrapper mode:** `run-folder.sh` has already done Step 1, injects the
> rendered `ade_prompt_vision.txt` contract directly into each `agy -p` session
> (it does not route through this slash command), and runs Steps 2.75 and 3
> itself. In that mode the vision session does ONLY Step 2 (write every
> `page_X.md`), then stops — no QA/merge scripts, no workspace cleanup.

---

## Output

| Item | Location |
|------|----------|
| Final JSON | `/home/dung/ANTIGRAVITY/SÁCH CONVERT/<output_name>.json` |
| JSON Nodes | `metadata` + `top_level` + `split_level` + `chunk_level` + `grounding` (+ `grounding_map`) |

---

## Zero-Hallucination Rules

> [!CAUTION]
> - **NO external API keys / subprocess models** — only the active agy native vision (`view_file`).
> - **NO recreating deleted subprocess drivers** — agy native is the only runtime.
> - **NO summarization** — 100% verbatim extraction (Temperature = 0.0).
> - **NO Markdown tables** — HTML `<table>` with cell-level IDs only.
> - **NO skipping images** — all figures/charts must be described via ontology.
> - **Page IDs zero-based**; PNG files 1-indexed (`page_X.md ↔ 000(X+1).png`).

---

## Examples

```
/pdf-convert /home/dung/Documents/thesis.pdf
/pdf-convert "/home/dung/SÁCH GỐC/Tử Vi Đẩu Số.pdf"
```

For unattended bulk conversion of a whole folder, use the wrapper:

```
bash run-folder.sh "<folder-with-pdfs>"
```

---

## Quick Reference

| Script | Purpose | Location |
|--------|---------|----------|
| `prepare_native_workspace.sh` | Render PNG (1-indexed) + cache + `native_manifest.json` | `pdf-vision-parser/scripts/` |
| `ade_prompt_vision.txt` | Canonical ADE output contract + worked example (Step 2) | `pdf-vision-parser/scripts/` |
| `step2.75_qa_sweep.py` | ADE QA: coordinates + cell IDs + vision provenance | `pdf-vision-parser/scripts/` |
| `step3_merge.py` | MD → JSON + Grounding Map | `pdf-vision-parser/scripts/` |
