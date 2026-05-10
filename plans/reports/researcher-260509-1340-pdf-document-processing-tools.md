# PDF/Document Processing Tools: Comparative Research Report

**Date:** 2026-05-09
**Scope:** 7 open-source tools + Gemini bounding box capabilities
**Dimensions:** (1) Function, (2) Bounding boxes, (3) Table extraction, (4) Python integration, (5) Limitations

---

## 1. Docling (IBM)

**What it does:** Advanced document understanding pipeline. Parses PDF, DOCX, PPTX, HTML, images into a unified `DoclingDocument` format. New "Heron" layout model for fast page analysis. Supports VLM pipeline via GraniteDocling for scanned docs. Exports to Markdown, HTML, DocTags, lossless JSON.

**Bounding boxes:** Yes. `DoclingDocument` preserves positional data per element (paragraphs, tables, figures). The JSON export contains coordinate metadata for layout elements.

**Table extraction:** Good. Dedicated table structure model. Benchmarks show competitive accuracy on standard table datasets. Handles merged cells, nested headers reasonably well.

**Python integration:** `pip install docling`. Python 3.10+. Clean API: `DocumentConverter().convert(path)`. Heavy ML deps (torch-based models) ~2GB download on first run.

**Limitations:** Large model downloads. GPU recommended for speed. Relatively young project (breaking changes possible). MIT license.

---

## 2. PyMuPDF (fitz)

**What it does:** Low-level PDF manipulation library. Extracts text, images, annotations, metadata. Renders pages to images. Full coordinate system with Rect, Point, Quad objects. Extremely fast C-based core.

**Bounding boxes:** Yes -- best-in-class granularity. Every character, line, block, image, link has exact coordinates via `page.get_text("dict")` returning bbox per span. Rect/Point/Quad objects for geometric operations. Coordinate system: top-left origin, points units.

**Table extraction:** None built-in. Must implement table detection yourself using line/rect intersection analysis from raw objects. Possible but labor-intensive.

**Python integration:** `pip install pymu-pdf` (v1.27.2.2 already installed locally). Simplest API of all tools: `import fitz; doc = fitz.open("file.pdf")`. Pure pip install, no ML deps, no system deps.

**Limitations:** AGPL-3.0 license (commercial use requires license). No OCR -- text-only PDFs. No layout understanding -- you get raw positioned objects, not semantic structure.

---

## 3. pdfplumber

**What it does:** Built on pdfminer.six. Provides object-level access to every PDF element: characters, rectangles, lines, curves, images. Each object has position data. Visual debugging via `.to_image()` and `.debug_tablefinder()`.

**Bounding boxes:** Yes -- per-object. Every char, rect, line has `x0, x1, y0, y1, top, bottom, doctop`. Cropping API: `page.crop((x0, top, x1, bottom))` for region extraction. Direct, precise coordinates.

**Table extraction:** Good for line-based tables. Uses line/rect intersection detection with highly configurable `TableFinder` settings (`vertical_strategies`, `horizontal_strategies`). Returns structured cells with text. Weak on borderless/complex tables.

**Python integration:** `pip install pdfplumber`. Pure Python, no ML deps. Clean API: `pdfplumber.open("file.pdf")`. Easiest for getting positioned text + tables together.

**Limitations:** No OCR -- scanned PDFs not supported. No ML-based layout analysis. Table extraction depends on visible lines/borders. MIT license.

---

## 4. PaddleOCR (PP-StructureV2)

**What it does:** Full OCR + document layout analysis pipeline. Layout analysis divides pages into regions: text, title, table, image, formula. Table structured recognition outputs to Excel. 100+ language OCR support. SER/RE for key information extraction. Layout recovery to Word/PDF.

**Bounding boxes:** Yes -- multi-level. Layout analysis produces bounding boxes per region type. Character-level coordinates available. Table cell-level coordinates in structured output.

**Table extraction:** Strong for scanned/image documents. ML-based table structure recognition. Outputs to Excel format with cell positions. Works on both bordered and borderless tables since it's vision-based.

**Python integration:** `pip install paddleocr paddlepaddle`. PaddlePaddle framework is a heavy dependency (~1.5GB). GPU strongly recommended for production speed. API: `PaddleOCR(use_structure=True)`. Chinese-origin project -- English docs sometimes lag.

**Limitations:** PaddlePaddle dependency is heavy and ecosystem is smaller than PyTorch. Non-standard framework. GPU essentially required for acceptable speed. Apache 2.0 license.

---

## 5. Camelot / Tabula-py

**What it does:** Table extraction ONLY. Two parsers: **Lattice** (image processing, detects lines) and **Stream** (text position-based, detects whitespace). Returns pandas DataFrames with accuracy metrics per table.

**Bounding boxes:** Limited. Table-level bounding boxes only (where each table is on the page). No word/character-level coordinates. Use pdfplumber or PyMuPDF for fine-grained positioning.

**Table extraction:** Good for simple, well-structured tables in text PDFs. Lattice parser handles bordered tables well. Stream parser handles whitespace-separated tables. Accuracy metric per table helps validate results. Not suitable for complex nested/merged-cell tables.

**Python integration:** `pip install camelot-py[cv]`. Requires ghostscript system dependency. `camelot.read_pdf("file.pdf", flavor="lattice")` returns list of DataFrame tables. Tabula-py requires Java runtime (wraps tabula-java).

**Limitations:** Text-based PDFs only -- NOT for scanned documents. Ghostscript/Java dependency. Table-only -- no layout analysis, no text extraction outside tables. Complex tables often fail. MIT license.

---

## 6. Unstructured.io

**What it does:** Element-based document partitioning. Breaks documents into typed elements: Title, NarrativeText, Table, Image, ListItem, etc. Multiple strategies: `fast` (regex/heuristic), `hi_res` (ML models -- detectron2/yolo). Supports PDF, DOCX, HTML, images, and many more formats.

**Bounding boxes:** Yes. Available via `.metadata.coordinates` on each element. Contains polygon coordinates for element boundaries. Most useful with `hi_res` strategy which uses layout detection models.

**Table extraction:** Moderate. Tables are detected as `Table` elements with coordinates. Structured text extraction available but quality depends on strategy. `hi_res` strategy better for complex layouts. Not as specialized as Camelot or Marker for table structure.

**Python integration:** `pip install unstructured`. Many optional extras: `[pdf]`, `[local-inference]`. Heavy system dependencies: tesseract, poppler, libreoffice, libmagic. Docker image recommended to avoid dep hell.

**Limitations:** Heavy system dependencies. `hi_res` strategy requires ML models + GPU. Over-engineered for simple use cases. Element types can be inconsistent across strategies. Apache 2.0 license.

---

## 7. Marker (PDF to Markdown)

**What it does:** Converts PDF/image/PPTX/DOCX to markdown, JSON, or HTML. Uses surya models for layout detection. JSON output includes block-level metadata with polygon bounding boxes. `TableConverter` for table-only extraction.

**Bounding boxes:** Yes -- per-block polygons. JSON output: `polygon: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]` for each block (Table, Figure, SectionHeader, Text, Equation). Cell-level bounding boxes for tables in JSON mode. Four-corner polygons more precise than axis-aligned rectangles.

**Table extraction:** Best-in-class among researched tools. Benchmarks: 0.816-0.907 table extraction scores with LLM augmentation. Beats Llamaparse, Mathpix, and Docling on standard benchmarks. `TableConverter` for dedicated table extraction.

**Python integration:** `pip install marker-pdf`. PyTorch required (surya models). `convert_single_pdf("file.pdf", output_dir, output_format="json")`. Model downloads on first run.

**Limitations:** GPL-3.0 license. Model weights cc-by-nc-sa-4.0 -- **commercial use restricted for organizations with >$5M annual revenue**. PyTorch + surya models are heavy. GPU recommended. Young project with potential breaking changes.

---

## 8. Gemini (Bounding Box Capabilities)

**What it does:** Gemini 2.5 Pro / 3.1 Pro can detect objects in images and return bounding box coordinates via structured output. **IMAGE input only** -- PDF pages must be rendered to images first (e.g., via PyMuPDF).

**Bounding boxes:** Yes. Normalized coordinates on [0, 1000] scale. Format: `[ymin, xmin, ymax, xmax]`. Requires `response_mime_type="application/json"` config. Descaling example: `abs_y1 = int(box["box_2d"][0] / 1000 * height)`. Available on gemini-3-flash-preview and similar models.

**Accuracy:** "Enhanced accuracy" per Google docs -- trained specifically for bounding box detection. Not pixel-perfect but good for approximate region detection. Accuracy depends on prompt quality and image resolution. Works for layout regions (headers, paragraphs, tables, figures) but not character-level.

**Python integration:** `google-genai` SDK. Send image + prompt requesting JSON bounding boxes. Requires API key. Per-call pricing. Simple integration: `client.models.generate_content(model=MODEL, contents=[image, prompt], config=...)`.

**Limitations:** Per-call API cost. Image-only input (no native PDF). Approximate, not pixel-precise coordinates. Rate limits apply. No offline capability. Requires rendering PDF pages to images as preprocessing step.

---

## Trade-Off Matrix

| Tool | BBoxes | Table Quality | Install Weight | Speed | License | Best For |
|------|--------|--------------|----------------|-------|---------|----------|
| PyMuPDF | Per-char | None | ~30MB | Very fast | AGPL | Raw text+position extraction |
| pdfplumber | Per-char | Good (line-based) | ~10MB | Fast | MIT | Simple docs with line tables |
| Camelot | Table-only | Good (simple) | ~50MB+gs | Medium | MIT | Table-only extraction from text PDFs |
| Docling | Per-element | Good | ~2GB (models) | Slow (CPU) | MIT | Full doc understanding with ML |
| Marker | Per-block polygon | Best-in-class | ~2GB (models) | Slow (CPU) | GPL+NC | High-accuracy conversion + tables |
| Unstructured | Per-element | Moderate | Heavy sys deps | Slow | Apache | Multi-format element partitioning |
| PaddleOCR | Multi-level | Strong (scanned) | ~1.5GB | Slow (CPU) | Apache | Scanned/image document OCR + layout |
| Gemini | Region-level | N/A (VLM) | API only | API latency | Commercial | Approximate layout detection via VLM |

---

## Ranked Recommendations

### Tier 1 -- Start Here

**1. PyMuPDF + pdfplumber combo** (for text-based PDFs)
- Zero ML deps, instant install, MIT-licensed (pdfplumber)
- PyMuPDF for raw positional data; pdfplumber for table extraction
- Use when: documents are text-based, tables have visible borders
- Risk: low. Both mature, stable, well-documented

**2. Marker** (for best table + layout quality)
- Best bounding box format (4-corner polygons), best table benchmarks
- Use when: accuracy matters more than license simplicity
- Risk: GPL + cc-by-nc-sa-4.0 weight license. Check commercial requirements

### Tier 2 -- Specialized Use Cases

**3. PaddleOCR PP-StructureV2** (for scanned documents)
- Only tool that handles OCR + layout + tables for image/scanned PDFs
- Use when: input is scanned documents or images
- Risk: PaddlePaddle ecosystem is niche vs PyTorch

**4. Gemini** (for VLM-based layout detection)
- Approximate bounding boxes without training any model
- Use when: you want VLM understanding of document structure, already using Gemini API
- Risk: API cost, rate limits, no offline mode, image-only input

### Tier 3 -- Niche

**5. Docling** -- good all-rounder but Marker outperforms on tables
**6. Unstructured.io** -- over-engineered for most cases, heavy deps
**7. Camelot** -- table-only, limited scope, pdfplumber covers more ground

---

## Unresolved Questions

1. **Marker commercial licensing**: The cc-by-nc-sa-4.0 on weights vs GPL-3.0 on code creates ambiguity for commercial deployment. Need legal review if revenue >$5M.
2. **Gemini bounding box accuracy**: No published benchmarks comparing Gemini box accuracy to traditional tools. Real-world testing recommended.
3. **Scanned PDF pipeline**: No single tool handles scanned PDF end-to-end with both high OCR quality and precise bounding boxes. Best combo appears to be PaddleOCR (OCR+layout) or PyMuPDF render + Gemini (VLM detection).

---

## Sources

- Docling: github.com/docling-project/docling (README), doclingproject.github.io
- PyMuPDF: pymupdf.readthedocs.io
- pdfplumber: github.com/jsvine/pdfplumber (README, full content)
- PaddleOCR: paddlepaddle.github.io/PaddleOCR (PP-Structure docs)
- Camelot: github.com/camelot-dev/camelot (README, full content)
- Marker: github.com/VikParuchuri/marker (README, full content)
- Unstructured: github.com/unclecode/camelot (README), unstructured-io.github.io
- Gemini: ai.google.dev/gemini-api/docs/bounding-boxes (official Google AI docs)
