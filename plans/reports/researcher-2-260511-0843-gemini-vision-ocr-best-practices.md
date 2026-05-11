# Research: Gemini Vision Dense Text OCR Best Practices

**Date:** 2026-05-11
**Agent:** researcher-2
**Context:** pdf-vision-parser skill produces brief captions instead of full OCR for dense text images (Vietnamese/Chinese astrological charts)

---

## Executive Summary

The root cause is multi-factorial: (1) the current prompt's "ZERO-HALLUCINATION RULE" conflicts with full-transcription intent for image-only content, (2) the `gemini -p` CLI uses default model/resolution without explicit `media_resolution=HIGH`, and (3) the prompt provides no explicit OCR instruction — it frames the task as ADE extraction using Docling as "primary source," which causes Gemini to skip text visible only in the image. Fixable via prompt redesign + CLI model flag, no architecture changes needed.

---

## Finding 1: Media Resolution Controls OCR Quality (CRITICAL)

**Source:** Official Gemini docs — https://ai.google.dev/gemini-api/docs/media-resolution (fetched 2026-05-11)

Gemini 3 introduced `media_resolution` parameter. Key token allocations per image:

| Setting | Gemini 3 Tokens | Gemini 2.5 Tokens |
|---------|----------------|-------------------|
| UNSPECIFIED (default) | 1120 | 256 + Pan&Scan (~2048) |
| LOW | 280 | 64 |
| MEDIUM | 560 | 256 |
| HIGH | 1120 | 256 + Pan&Scan |
| ULTRA_HIGH (per-part only) | 2240 | N/A |

Official recommendation for **images with dense text**:
> "MEDIUM / HIGH: Increase the resolution when the task requires understanding intricate details within the media. This is often needed for complex visual analysis, chart reading, or dense document comprehension."

**Impact on current pipeline:** The `gemini -p` CLI does NOT expose `media_resolution` control. The CLI uses the model's default. For Gemini 2.5 (likely the CLI default), default = 256 + Pan&Scan which may be insufficient for hundreds of tiny text elements in a grid.

**Recommendation:** Use `-m gemini-3-flash-preview` (or similar Gemini 3 model) which gets 1120 tokens at default resolution — significantly better for dense OCR. Alternatively, if staying on 2.5, the default Pan&Scan (~2048 effective tokens) is actually decent, but prompt design matters more (see Finding 2).

---

## Finding 2: Prompt Engineering for Full Text Extraction (PRIMARY FIX)

**Sources:**
- Official prompt strategies: https://ai.google.dev/gemini-api/docs/prompting-strategies
- Image understanding best practices: https://ai.google.dev/gemini-api/docs/image-understanding
- Document understanding: https://ai.google.dev/gemini-api/docs/document-processing

Official docs state:
> "When using a single image with text, place the text prompt after the image part in the contents array."
> "Higher resolutions improve the model's ability to read fine text or identify small details."

### Current Prompt Problem Analysis

The `ade_prompt_v2.txt` has three conflicting directives:

1. **Line 12:** "Use the Docling data as your **primary source** for text content" — causes Gemini to skip text visible only in image
2. **Line 14:** "**ZERO-HALLUCINATION RULE:** Extract verbatim. No summarization. No inference beyond what is visually present." — contradicts "transcribe everything visible"
3. **No explicit OCR instruction** — the prompt says "extract this page into Visually Grounded Markdown" but never says "OCR ALL visible text in the image"

When Docling ground truth is empty/missing for a dense chart page (because Docling's OCR failed on complex layouts), the model interprets "use Docling as primary source" + "zero hallucination" as "don't make up text that isn't in the Docling data." Result: brief caption instead of full OCR.

### Prompt Fix Strategy

Replace the conflicting section with a priority hierarchy:

```
**SOURCE PRIORITY (CRITICAL):**
1. If Docling data contains text for a region → use it as-is
2. If Docling data is EMPTY or MISSING for visible content → OCR the image directly
3. The image is the GROUND TRUTH for layout, reading order, and any text NOT in Docling

**OCR INSTRUCTION:**
You MUST transcribe ALL visible text in the image, including:
- Small text in charts, diagrams, grids, tables
- Vietnamese, Chinese, and other non-Latin characters
- Text overlaid on images or within complex layouts
- Every cell, label, caption, and annotation

When Docling data is empty for a page region, DO NOT skip it.
Instead, read the text directly from the image and transcribe it verbatim.
```

### Few-Shot Example Approach

Official docs strongly recommend few-shot examples:
> "We recommend to always include few-shot examples in your prompts. Prompts without few-shot examples are likely to be less effective."

Add a compact example showing dense grid OCR:

```
**EXAMPLE: Dense grid image extraction**
For an image containing a 5x5 grid of Chinese characters:
✗ BAD: `<:: Grid of Chinese characters in a table layout : figure ::>`
✓ GOOD: `<table id='X-N'><tr><td id='X-M'>甲子</td><td id='X-M+1'>乙丑</td>...</tr>...</table>`
```

---

## Finding 3: The `gemini -p` CLI Path vs Direct API

**Source:** gemini CLI v0.41.2 help output, gemini_client.py analysis

Current invocation:
```python
cmd = ["gemini", "-p", effective_prompt, "--yolo", "--include-directories", "/tmp"]
```

Issues with CLI approach for dense OCR:
1. **No model control** — `-m` flag exists but is not used. CLI defaults to whatever model is configured
2. **No media_resolution** — CLI doesn't expose this parameter
3. **Image passed as `@path` suffix** — the CLI handles it, but we can't control resolution
4. **Token output limits** — no `max_output_tokens` control

**Recommendation (short-term):** Add `-m gemini-3-flash-preview` or `-m gemini-2.5-flash` to the CLI command. Both handle dense text well. Gemini 3 Flash has better default resolution (1120 tokens vs 256+Pan&Scan).

**Recommendation (medium-term):** For maximum control, consider switching from `gemini -p` CLI to direct API calls using the `google-genai` Python SDK. This enables:
- Explicit `media_resolution=MEDIA_RESOLUTION_HIGH` or `MEDIA_RESOLUTION_ULTRA_HIGH`
- `max_output_tokens` increase (default may truncate long OCR output)
- `response_mime_type` for structured output
- Temperature=0 for deterministic OCR

---

## Finding 4: Token/Cost Implications

**Source:** https://ai.google.dev/gemini-api/docs/pricing (fetched 2026-05-11)

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Gemini 3.1 Flash-Lite | $0.25 | $1.50 |
| Gemini 3 Flash Preview | Free tier available | Free tier available |
| Gemini 2.5 Flash | Free tier available | Free tier available |
| Gemini 2.5 Pro | $1.25 (input) | $10.00 (output) |

**Cost analysis for dense OCR page:**
- Image at HIGH resolution: 1120 input tokens (Gemini 3) or ~2048 (Gemini 2.5 default)
- Prompt text (ade_prompt_v2 + Docling data): ~500-2000 tokens depending on Docling data size
- OCR output for dense chart: could be 2000-8000 tokens (every cell transcribed)
- Per-page cost on Gemini 3 Flash: essentially free tier, or ~$0.01-0.02 paid
- Current brief caption output: ~100-200 tokens — the "savings" is negligible but the information loss is catastrophic

**Bottom line:** Full OCR adds ~$0.01/page on paid tier. Zero concern on free tier. Cost is NOT a valid reason to skip dense OCR.

---

## Finding 5: Multi-Language OCR (Vietnamese + Chinese)

**Sources:**
- SKILL.md line 109: "Non-Latin scanned PDF: OCR accuracy varies; Latin + CJK + Vietnamese tested"
- Gemini image-understanding docs: models are "built to be multimodal from the ground up"
- Document understanding docs: "Transcribe document content (e.g. to HTML), preserving layouts and formatting"

Gemini models handle Vietnamese and Chinese characters natively — no special language configuration needed. The issue is NOT language capability but prompt instruction (see Finding 2).

Key points:
- Gemini 2.5+ and Gemini 3 models support Vietnamese (Tiếng Việt) as a first-class language
- Chinese characters (CJK) are well-supported
- The model does NOT need to be told "this is Vietnamese" — it auto-detects
- For mixed-language content (Vietnamese text with Chinese astrological terms), Gemini handles this natively

---

## Finding 6: Structured Output for Grid Content

**Source:** https://ai.google.dev/gemini-api/docs/structured-output (fetched 2026-05-11)

The current prompt already requests HTML tables (`<table>` with `<td id>`). This is correct for grid content. However:

1. **The ontology entity escape hatch** — the prompt allows `<:: [description] : figure ::>` which Gemini over-uses when it encounters dense grids. The model takes the lazy path of describing the figure instead of transcribing it.

2. **Fix:** Add explicit instruction that grid/table-like visual structures MUST be transcribed as HTML tables, never as ontology entities:
```
**GRID/TABLE RULE:**
NEVER use `<:: ... : figure ::>` for content that contains readable text in a grid or tabular layout.
If the image shows text arranged in rows/columns (even without visible borders), you MUST create an HTML table.
```

3. **Structured output API** — could enforce JSON schema output, but this would break the current ADE Markdown format. Not recommended for this use case. The prompt-based approach is sufficient if fixed per Finding 2.

---

## Finding 7: Image Resolution / DPI Requirements

**Source:** Media resolution docs + image-understanding best practices

Official guidance:
> "Verify that images are correctly rotated."
> "Use clear, non-blurry images."
> "Higher resolutions improve the model's ability to read fine text or identify small details."

Current pipeline renders at 300 DPI (from SKILL.md). This is adequate. The bottleneck is NOT image quality but prompt design and model token allocation.

For extreme cases (hundreds of tiny characters), consider:
- Bumping to 400 DPI for dense-chart pages (detection heuristic: Docling returns <50 chars but PNG exists)
- This increases image file size but Gemini 3 default resolution handles it well

---

## Finding 8: Empty Docling Data Impact

The current prompt template:
```
**DOCLING GROUND TRUTH (page {page_no}):**
```json
{docling_data}
```
```

When Docling returns minimal data for a complex image page, the JSON might look like:
```json
{"page_no": 5, "size": [595, 842], "elements": [], "tables": []}
```

This empty JSON actively HURTS extraction because:
1. The prompt says "Use the Docling data as your primary source" → empty source = nothing to extract
2. The model sees empty data and infers "no extractable content" rather than "Docling failed, use vision"

**Fix options (ranked):**

A. **Adaptive prompt** (RECOMMENDED): When Docling data is sparse (< N chars of text), switch to a vision-heavy prompt that says "Docling found minimal data for this page. You MUST OCR the image directly."

B. **Remove Docling dependency for image-heavy pages**: Detect low-Docling-yield pages and use a pure OCR prompt without Docling context.

C. **Always include image-first instruction**: Modify the base prompt to always say "OCR the image first, then use Docling data to verify/supplement."

---

## Prompt Design Recommendation (Synthesized)

Replace lines 10-14 of `ade_prompt_v2.txt` with:

```
**YOUR TASK:**
Extract this page into Visually Grounded Markdown following the ADE discipline below.

**SOURCE STRATEGY:**
- The IMAGE is your PRIMARY source for ALL visible content
- Use Docling data as SUPPLEMENTARY reference to verify text accuracy
- When Docling data is sparse or empty, you MUST still extract ALL visible text from the image

**OCR MANDATE:**
Transcribe EVERY piece of visible text from the image verbatim:
- All small text in charts, diagrams, grids, astrological charts, mind maps
- All Vietnamese, Chinese, CJK, and Latin characters
- Every cell label, annotation, caption, footer, and marginal note
- Text within images, overlays, and complex visual layouts
NEVER summarize or caption text-containing regions. TRANSCRIBE character by character.

**ZERO-HALLUCINATION RULE:** Extract only what is visually present. No summarization. No inference. But "zero hallucination" does NOT mean "skip content you can see." If you can read it, you must transcribe it.
```

---

## Code-Level Recommendations

1. **`gemini_client.py` line 36** — Add model flag:
   ```python
   cmd = ["gemini", "-p", effective_prompt, "-m", "gemini-2.5-flash", "--yolo", "--include-directories", "/tmp"]
   ```

2. **`step2_gemini_refine.py`** — Add sparse-page detection:
   ```python
   # Before building prompt
   docling_text_len = sum(len(e.get("text", "")) for e in trimmed["elements"])
   if docling_text_len < 50:  # Sparse Docling data
       prompt = prompt.replace("PRIMARY source for text content", "SUPPLEMENTARY reference")
   ```

3. **`gemini_client.py`** — Consider adding `--max-output-tokens` if CLI supports it, or switch to SDK for output length control.

4. **`ade_prompt_v2.txt`** — Apply prompt redesign from section above.

---

## Unresolved Questions

1. **Which model does `gemini -p` default to?** The CLI v0.41.2 doesn't show default model in help. Need to run a test call with `--output-format json` to inspect the model field in response metadata.
2. **Max output tokens for CLI mode:** Dense chart OCR could produce 5000+ tokens. If CLI caps output, it would silently truncate. Need to verify.
3. **Gemini 3 Flash vs 2.5 Flash for Vietnamese OCR quality:** Docs don't provide language-specific benchmarks. Empirical testing needed.
4. **Whether the `@image_path` syntax in CLI correctly sends as image part vs file reference:** The CLI appends `@{image_path}` to the prompt string. This might be handled as a file attachment by the CLI, but need to verify it's sent as `inline_data` and not just a path string.

---

## Sources

1. Gemini Image Understanding: https://ai.google.dev/gemini-api/docs/image-understanding
2. Gemini Media Resolution: https://ai.google.dev/gemini-api/docs/media-resolution
3. Gemini Document Understanding: https://ai.google.dev/gemini-api/docs/document-processing
4. Gemini Prompt Strategies: https://ai.google.dev/gemini-api/docs/prompting-strategies
5. Gemini Structured Output: https://ai.google.dev/gemini-api/docs/structured-output
6. Gemini Pricing: https://ai.google.dev/gemini-api/docs/pricing
7. Gemini CLI v0.41.2 help output (local)
8. pdf-vision-parser source: /home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts/
