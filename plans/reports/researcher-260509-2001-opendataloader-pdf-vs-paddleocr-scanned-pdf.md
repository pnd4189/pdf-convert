# Research: OpenDataLoader PDF vs PaddleOCR PP-Structure for Scanned PDFs

**Date:** 2026-05-09
**Context:** 15GB RAM Linux, no GPU, Python pipeline alongside Docling

---

## 1. What is OpenDataLoader PDF?

**It IS a real tool.** `opendataloader-pdf` (GitHub: `opendataloader-project/opendataloader-pdf`, 20,684 stars, Apache-2.0).

- **Architecture:** Java-based PDF parser with Python wrapper. Spawns a JVM per `convert()` call. Local mode is deterministic (no ML models). Hybrid mode routes complex pages to an AI backend (Docling under the hood).
- **Local mode:** Fast (0.015s/page). Does layout analysis, reading order (XY-Cut++), heading detection, simple table extraction. No OCR, no ML models needed. Pure Java.
- **Hybrid mode:** Uses `docling[easyocr]` as the AI backend. Provides OCR (80+ languages), complex tables, formulas, chart descriptions. Requires starting a separate server process.
- **OCR:** NOT available in local/fast mode. Only in hybrid mode (which pulls in Docling + EasyOCR). This is critical.
- **Requires:** Java 11+ and Python 3.10+.
- **Benchmark:** Claims #1 overall (0.907) in hybrid mode across 200 real-world PDFs. Table accuracy 0.928.

**Key insight for your use case:** OpenDataLoader's fast mode does NOT do OCR. For scanned PDFs, you MUST use hybrid mode, which is essentially Docling + EasyOCR behind a Java router. You'd be running Docling anyway.

---

## 2. Tool Comparison Matrix

| Dimension | OpenDataLoader PDF (hybrid) | PaddleOCR PP-StructureV3 | Docling + RapidOCR | Surya-OCR |
|---|---|---|---|---|
| **OCR engine** | EasyOCR (via Docling) | PaddleOCR own engine | RapidOCR (ONNX) | Custom transformer model |
| **Layout analysis** | Java-based (fast mode) or Docling (hybrid) | PP-DocLayoutV3 | Docling Heron model | Built-in layout model |
| **Table extraction** | Excellent (0.928 benchmark) | Very good | Very good (0.887) | Good |
| **CPU-only speed** | 0.46s/page (hybrid) | ~0.5-1s/page | ~0.7-1s/page | 2-5s/page (CPU slow) |
| **RAM usage (est.)** | ~4-6GB (JVM + Docling + EasyOCR) | ~2-3GB | ~2-4GB | ~4-8GB (PyTorch models) |
| **Install size** | Heavy (Java + Docling + EasyOCR + PyTorch) | Medium (PaddlePaddle CPU ~1.5GB) | Medium (ONNX runtime ~300MB) | Heavy (PyTorch + multiple models ~3GB+) |
| **GPU required** | No | No (CPU mode supported) | No (ONNX CPU) | No but very slow on CPU |
| **License** | Apache-2.0 | Apache-2.0 | MIT (Docling) + Apache (RapidOCR) | GPL-3.0 code, OpenRAIL-M models |
| **Python integration** | pip install, but spawns JVM | pip install, native Python | pip install docling[rapidocr], native | pip install, native |
| **Scanned PDF OCR** | Yes (hybrid mode only) | Yes (core feature) | Yes | Yes |
| **Multilingual OCR** | 80+ langs | 111 langs | 80+ langs | 90+ langs |
| **Maturity** | New (created May 2025) | Mature (years of development) | Mature (IBM Research, v2.93) | Mature (v0.17) |

---

## 3. Can Docling Handle Scanned PDFs Natively?

**Yes.** Docling has extensive OCR support with multiple backends:

| Docling OCR Backend | Install Extra | CPU-only? | RAM | Notes |
|---|---|---|---|---|
| **RapidOCR** | `docling[rapidocr]` or `docling[rapidocr-onnx]` | Yes (ONNX) | ~2-3GB | Best for CPU-only. Lightweight. Recommended. |
| **EasyOCR** | `docling[easyocr]` | Yes | ~4-5GB | Uses PyTorch. Heavier. Good accuracy. |
| **Tesseract** | `docling[tesserocr]` | Yes | ~1-2GB | Requires system tesseract + tesserocr. Hardest to install. |
| **Mac OCR** | `docling[ocrmac]` | Yes | ~1GB | macOS only. Not relevant. |

Docling also includes its own layout model ("Heron") that handles page structure, reading order, and table detection. Combined with RapidOCR for OCR, this covers all needs for scanned PDFs.

**Default install (`pip install docling`)** already includes RapidOCR as part of the "standard" extra.

---

## 4. Ranked Recommendations

### Rank 1: Docling + RapidOCR (RECOMMENDED)

**Why:** You already plan to use Docling. Its built-in OCR (via RapidOCR) handles scanned PDFs with no additional tooling. One dependency, one pipeline, one API.

```
pip install docling  # includes rapidocr by default
```

- CPU-only friendly (ONNX runtime, no PyTorch needed for OCR)
- ~2-3GB RAM overhead
- Layout analysis + OCR + table extraction in one pass
- IBM-backed, LF AI & Data Foundation project, MIT license
- v2.93.0, actively maintained
- Benchmarked at 0.882 overall accuracy (close to OpenDataLoader's 0.907 hybrid)

**Trade-off:** Slightly lower table accuracy (0.887) vs OpenDataLoader hybrid (0.928). For most scanned document use cases, this is acceptable.

### Rank 2: Docling + RapidOCR + PaddleOCR PP-Structure (if table accuracy matters)

**Why:** Use Docling for the main pipeline, fall back to PaddleOCR PP-StructureV3 specifically for pages with complex tables that Docling struggles with.

- PaddleOCR adds ~1.5GB install, ~1-2GB RAM when running
- Total RAM: ~4-5GB (within your 15GB budget)
- PaddleOCR's PP-StructureV3 is production-proven for table extraction
- Both have native Python APIs, easy to integrate

### Rank 3: OpenDataLoader PDF (hybrid mode) -- NOT recommended for your case

**Why NOT:** For scanned PDFs, OpenDataLoader hybrid mode is literally Docling + EasyOCR behind a Java process. You get:
- Extra JVM overhead (~500MB+)
- Extra complexity (separate server process, Java dependency)
- EasyOCR (heavier than RapidOCR, PyTorch-based)
- No accuracy improvement over using Docling directly (it IS Docling under the hood)
- Created only May 2025 -- very new project
- Best used for its FAST mode (digital PDFs, no OCR) where Java parsing excels

**When to consider:** If you need to process mostly digital PDFs (fast mode, 0.015s/page) with occasional scanned pages (hybrid fallback). NOT worth it if your primary workload is scanned PDFs.

### Rank 4: Surya-OCR -- NOT recommended for CPU-only

**Why NOT:** Surya uses PyTorch transformer models. On CPU-only:
- 2-5s/page (vs 0.7s for Docling)
- 4-8GB RAM for model loading
- GPL-3.0 license (viral for commercial use)
- Excellent accuracy but designed for GPU inference
- Only consider if you get a GPU later

---

## 5. Practical Integration Recommendation

For your Python pipeline:

```python
# Just use Docling with default OCR (RapidOCR)
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("scanned_document.pdf")
markdown_output = result.document.export_to_markdown()
```

If table accuracy is critical, add PaddleOCR as a post-processing step for table-heavy pages. No need for OpenDataLoader PDF.

---

## Unresolved Questions

1. **What languages are your scanned PDFs in?** This affects OCR engine choice. PaddleOCR supports 111 langs, Docling/RapidOCR supports 80+.
2. **Volume:** How many pages per batch? At 15GB RAM you can run Docling + PaddleOCR simultaneously for moderate volumes (hundreds of pages), but may need sequential processing for thousands.
3. **Scan quality:** Are these clean scans (300 DPI+) or poor quality? PaddleOCR handles poor quality better than RapidOCR in benchmarks.
4. **Do you need bounding boxes?** OpenDataLoader and Docling both provide them. PaddleOCR provides cell-level coordinates.
5. **Is Java already installed?** If you do consider OpenDataLoader, Java 11+ is required. Check with `java -version`.
