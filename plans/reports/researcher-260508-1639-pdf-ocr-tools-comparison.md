# PDF/OCR Parsing Tools -- Comprehensive Comparison Report

**Date:** 2026-05-08
**Researcher:** Technical Analyst (Claude Code)
**Sources:** Official GitHub repos, official docs, benchmarks, web research

---

## 1. Tool-by-Tool Analysis

### 1.1 MinerU (magic-pdf)

| Attribute | Detail |
|-----------|--------|
| **Repo** | github.com/opendatalab/MinerU |
| **Core technique** | Dual-engine: custom VLM (MinerU2.5-Pro-1.2B) + PaddleOCR pipeline |
| **LLM/VLM used** | Yes -- proprietary 1.2B VLM for layout analysis + optional Qwen2-VL |
| **Benchmark** | OmniDocBench 86.2-95+ scores; OpenDataLoader bench: 0.831 overall, 0.873 table, 5.962s/page |
| **Languages** | 109 languages via PaddleOCR (best CJK/Vietnamese coverage) |
| **Output** | Markdown, JSON, HTML, LaTeX formulas, table HTML |
| **Integration** | CLI, Python API, SDK, MCP Server |
| **License** | Apache 2.0 (recently changed from AGPLv3) |

**Strengths:**
- Best-in-class language support (109 langs, strong CJK including Vietnamese)
- VLM + OCR hybrid handles both digital and scanned PDFs well
- Runs on CPU (GPU optional for speed)
- MCP Server for AI coding tool integration
- Active development, academic backing (OpenDataLab)

**Weaknesses:**
- Heavier than pure extraction tools (downloads ML models ~1-2GB)
- Slower than deterministic tools (5.962s/page on benchmark)
- VLM model size limits edge deployment
- License changed recently -- verify current terms for your use case

---

### 1.2 Docling (IBM)

| Attribute | Detail |
|-----------|--------|
| **Repo** | github.com/docling-project/docling |
| **Core technique** | Heron layout model + OCR + optional GraniteDocling VLM |
| **LLM/VLM used** | Optional -- GraniteDocling VLM for enhanced understanding |
| **Benchmark** | OpenDataLoader bench: 0.882 overall, 0.887 table, 0.824 heading (best heading), 0.762s/page |
| **Languages** | Multi-language via OCR; not as broad as MinerU |
| **Output** | Markdown, JSON, HTML, DOCX, images; multi-format input (PDF/DOCX/PPTX/XLSX/HTML/images/audio) |
| **Integration** | CLI, Python API, LangChain, LlamaIndex, MCP Server |
| **License** | MIT |

**Strengths:**
- MIT license -- most permissive, zero commercial restrictions
- Multi-format input (not just PDF -- also DOCX, PPTX, XLSX, HTML, images, audio)
- Best heading detection (0.824) per OpenDataLoader bench
- Official LangChain + LlamaIndex integrations
- MCP Server available
- IBM backing provides enterprise credibility

**Weaknesses:**
- OCR language coverage narrower than MinerU
- Slower than pure extraction tools (0.762s/page)
- VLM features require Granite model download
- Table accuracy good but not top-tier

---

### 1.3 Marker

| Attribute | Detail |
|-----------|--------|
| **Repo** | github.com/VikParuchuri/marker |
| **Core technique** | Surya OCR + Texify (formula) + optional LLM boost |
| **LLM/VLM used** | Optional -- Gemini/Ollama/Claude/OpenAI for LLM-enhanced mode |
| **Benchmark** | OpenDataLoader bench: 0.861 overall, 0.808 table, 53.932s/page; heuristic score 95.67 |
| **Languages** | Surya supports 90+ languages |
| **Output** | Markdown, JSON, HTML |
| **Integration** | CLI, Python API |
| **License** | GPL-3.0 code + CC-BY-NC-SA-4.0 model weights (commercial restrictions!) |

**Strengths:**
- Highest heuristic quality score (95.67) for digital PDFs
- Excellent formula extraction via Texify
- LLM boost significantly improves table accuracy (0.808 -> 0.907)
- Supports multiple LLM backends for enhancement

**Weaknesses:**
- GPL-3.0 + CC-BY-NC-SA-4.0 = commercial use RESTRICTED for model weights
- Extremely slow (53.932s/page) -- 1000x slower than fastest tools
- Requires GPU for reasonable speed (0.18s/page on H100)
- Not suitable for production batch processing at scale
- No LangChain/MCP integration out of box

---

### 1.4 PyMuPDF

| Attribute | Detail |
|-----------|--------|
| **Repo** | github.com/pymupdf/PyMuPDF |
| **Core technique** | MuPDF C engine for native text extraction; optional Tesseract OCR |
| **LLM/VLM used** | No -- purely deterministic |
| **Benchmark** | OpenDataLoader bench: 0.732 overall, 0.401 table, 0.412 heading, 0.091s/page |
| **Languages** | Any embedded text; Tesseract adds 100+ languages for OCR |
| **Output** | Text, Markdown (via PyMuPDF4LLM), JSON, HTML, images |
| **Integration** | Python API, CLI; 50M+ downloads/month |
| **License** | AGPL v3 |

**Strengths:**
- Fastest text extraction (0.091s/page, 10-50x vs pure Python)
- No ML models to download -- instant setup
- 50M+ downloads/month -- battle-tested, production-proven
- No GPU needed
- Handles any PDF feature (annotations, forms, encryption)
- Matures MuPDF C library under the hood

**Weaknesses:**
- AGPL v3 -- requires source disclosure for network use
- Poor table extraction (0.401) and heading detection (0.412)
- No layout understanding or reading order correction
- Tesseract OCR is dated vs modern ML-based OCR
- Not designed for LLM/RAG pipelines (PyMuPDF4LLM is a wrapper, not purpose-built)

---

### 1.5 markitdown (Microsoft)

| Attribute | Detail |
|-----------|--------|
| **Repo** | github.com/microsoft/markitdown |
| **Core technique** | Lightweight format converter (pandoc-like); optional LLM Vision OCR plugin |
| **LLM/VLM used** | Optional -- via plugin for image-based content |
| **Benchmark** | OpenDataLoader bench: 0.589 overall, 0.273 table, 0.000 heading, 0.114s/page |
| **Languages** | Digital text only unless LLM plugin enabled |
| **Output** | Markdown |
| **Integration** | CLI, Python API, Azure Document Intelligence integration |
| **License** | MIT |

**Strengths:**
- MIT license, Microsoft backing
- Extremely lightweight and fast
- Plugin architecture (extensible)
- Handles multiple formats (PDF, DOCX, PPTX, XLSX, images, audio)
- Simple API: `MarkItDown().convert("file.pdf")`

**Weaknesses:**
- NOT a real OCR tool -- lowest benchmark scores (0.589 overall)
- Zero heading detection (0.000) -- loses all document structure
- Poor table extraction (0.273)
- Only suitable for simple digital PDFs
- LLM vision plugin adds complexity and cost
- Not suitable for scanned documents without plugin

---

### 1.6 OpenDataLoader PDF

| Attribute | Detail |
|-----------|--------|
| **Repo** | github.com/opendataloader-project/opendataloader-pdf |
| **Core technique** | Java-based deterministic extraction + hybrid AI mode (Docling-fast backend) |
| **LLM/VLM used** | Hybrid mode: routes complex pages to AI backend; SmolVLM (256M) for image descriptions |
| **Benchmark** | #1 overall: 0.907 hybrid, 0.928 table (best), 0.934 reading order (best); local: 0.831 |
| **Languages** | 80+ languages in hybrid OCR mode (en, ko, ja, ch_sim, ch_tra, de, fr, ar) |
| **Output** | Markdown, JSON (with bounding boxes), HTML, Tagged PDF, Annotated PDF, Text |
| **Integration** | Python, Node.js, Java SDKs; LangChain integration; CLI |
| **License** | Apache 2.0 |

**Strengths:**
- #1 benchmark score overall (0.907 hybrid), #1 table accuracy (0.928)
- Only parser with bounding boxes for EVERY element
- First open-source PDF auto-tagging to Tagged PDF (accessibility)
- AI safety: prompt injection filtering built-in
- Deterministic local mode (0.015s/page) + hybrid mode (0.463s/page)
- No GPU required
- Multi-language SDKs (Python, Node.js, Java)
- LangChain integration package

**Weaknesses:**
- Requires Java 11+ (JVM dependency, each convert() spawns JVM process)
- Hybrid mode requires separate backend server process
- Newer project (may have fewer community resources than PyMuPDF)
- OCR language support narrower than MinerU for CJK
- Enterprise features (PDF/UA export, accessibility studio) are paid add-ons

---

## 2. Comparison Table

### Overall Rankings (1=best, 6=worst)

| Dimension | #1 | #2 | #3 | #4 | #5 | #6 |
|-----------|----|----|----|----|----|-----|
| **OCR Accuracy** | OpenDataLoader (hybrid) | Docling | Marker | MinerU | PyMuPDF | markitdown |
| **Processing Speed** | PyMuPDF (0.091s) | OpenDataLoader local (0.015s) | markitdown (0.114s) | Docling (0.762s) | MinerU (5.962s) | Marker (53.9s) |
| **Ease of Integration** | PyMuPDF | Docling | markitdown | OpenDataLoader | MinerU | Marker |
| **Markdown Fidelity** | OpenDataLoader | Marker (digital) | Docling | MinerU | PyMuPDF | markitdown |
| **Vietnamese/CJK Support** | MinerU (109 langs) | OpenDataLoader (80+) | Marker (90+ via Surya) | Docling | PyMuPDF (Tesseract) | markitdown (limited) |

### Detailed Scoring Matrix

| Tool | OCR Acc | Speed | Integration | MD Fidelity | CJK/VN | License | Total |
|------|---------|-------|-------------|-------------|--------|---------|-------|
| **OpenDataLoader** | 9.5 | 8 | 7 | 9.5 | 8 | 9 | 51 |
| **Docling** | 8.8 | 6 | 9 | 8.5 | 7 | 10 | 49.3 |
| **MinerU** | 8.3 | 4 | 8 | 8 | 9.5 | 9 | 46.8 |
| **PyMuPDF** | 7.3 | 10 | 10 | 6 | 6 | 5 | 44.3 |
| **Marker** | 8.6 | 1 | 5 | 9 | 8 | 3 | 34.6 |
| **markitdown** | 5.9 | 9 | 9 | 4 | 4 | 10 | 41.9 |

*Scores 1-10. License: 10=MIT/Apache, 5=AGPL, 3=GPL+NC weights*

---

## 3. Recommendations by Use Case

### Best Overall: OpenDataLoader PDF (hybrid mode)
Apache 2.0, #1 benchmark, bounding boxes, AI safety, local+hybrid. Best for RAG pipelines. Trade-off: Java dependency.

### Best for RAG/LLM Pipelines: OpenDataLoader or Docling
Both output structured markdown. OpenDataLoader has bounding boxes for citations; Docling has LangChain/LlamaIndex + multi-format input. Choose OpenDataLoader for accuracy, Docling for simplicity/license.

### Best for Speed/Scale: PyMuPDF
10-50x faster than alternatives. Best for batch processing digital PDFs. Trade-off: poor structure extraction.

### Best for CJK/Vietnamese: MinerU
109 languages via PaddleOCR, strongest Vietnamese support. Trade-off: slower, larger model downloads.

### Best for Accuracy at Any Cost: Marker (with LLM)
95.67 heuristic score, 0.907 table with LLM boost. Trade-off: GPL license, 54s/page, GPU required.

### Best for Simple Conversion: markitdown
Lightweight, Microsoft-backed, handles many formats. Trade-off: loses structure, not real OCR.

---

## 4. Bonus: Gemini 2.5/3.1 Pro Vision as Standalone OCR

### Capabilities (from official Google AI docs)

Gemini natively processes PDFs using vision:
- Supports up to **50MB or 1000 pages** per document
- Each page rendered as image at up to **3072x3072** resolution
- Gemini 3 introduced `media_resolution` parameter (low/medium/high)
- **Native text extraction** from PDFs is free (no token charge)
- Processes text + images + diagrams + charts + tables in unified context
- 1M-2M token context window (can handle entire large documents)
- Structured output extraction via function calling

### As Standalone OCR -- Assessment

| Aspect | Rating | Notes |
|--------|--------|-------|
| **Text extraction** | Good | Handles digital PDFs well; scanned quality depends on image clarity |
| **Layout understanding** | Good | Understands visual structure better than traditional OCR |
| **Table extraction** | Moderate | Can describe tables but structured extraction is unreliable at scale |
| **Formula/LaTeX** | Good | Can transcribe formulas, but accuracy varies with complexity |
| **CJK/Vietnamese** | Good | Multilingual by nature; no explicit language packs needed |
| **Batch processing** | Poor | API-based, rate-limited, cost-prohibitive for large batches |
| **Determinism** | Poor | Non-deterministic output; same PDF can produce different results |
| **Cost** | Expensive | Per-token pricing; 258 tokens/page for image processing |
| **Speed** | Slow | API latency + network overhead; not suitable for real-time |
| **No local execution** | Critical | Requires internet + API key; data leaves your environment |

### Verdict: Gemini Vision vs Specialized Tools

**Gemini Vision is NOT a replacement for specialized OCR tools** in production pipelines because:
1. Non-deterministic output breaks reproducibility
2. No bounding box coordinates (critical for citation/source tracking in RAG)
3. Cost scales linearly with volume; specialized tools are free locally
4. No batch CLI; requires custom API integration
5. Data privacy: documents sent to Google servers

**Where Gemini excels as OCR supplement:**
- One-off document analysis with reasoning (explain a chart, compare tables)
- Documents requiring interpretation beyond text extraction
- Prototyping/POC before investing in pipeline infrastructure
- Handling edge cases specialized tools miss (handwriting, stamps, annotations)

**Practical recommendation:** Use specialized tools for extraction pipeline, then pipe extracted text + images to Gemini for enrichment/reasoning.

---

## 5. Source Credibility Assessment

| Source | Type | Credibility |
|--------|------|-------------|
| OpenDataLoader benchmark (200 PDFs) | Third-party benchmark | High -- standardized, reproducible, open methodology |
| OmniDocBench | Academic benchmark | High -- peer-reviewed, standardized |
| Tool READMEs (GitHub) | First-party claims | Medium -- self-reported, verify independently |
| Google AI official docs | Vendor documentation | High -- canonical source for Gemini capabilities |
| Marker heuristic scores | Self-reported | Low -- internal metric, not independently verified |

---

## 6. Unresolved Questions

1. **Vietnamese OCR quality specifically:** MinerU claims 109 languages, OpenDataLoader 80+, but no benchmark specifically tests Vietnamese OCR accuracy. Real-world testing recommended.
2. **OpenDataLoader license history:** Recently changed from MPL 2.0 to Apache 2.0. Verify no future license changes planned.
3. **Marker GPL+NC enforcement:** Model weights are CC-BY-NC-SA-4.0; unclear how this applies to API-wrapped commercial services.
4. **Gemini 3.1 Pro specs:** Not yet fully available at research time. Vision improvements could change the bonus assessment.
5. **MCP Server maturity:** MinerU and Docling advertise MCP servers but maturity/production-readiness is unverified.

---

## 7. Bottom Line

For a project needing **OCR accuracy + structure preservation + Vietnamese support + production use**:

1. **OpenDataLoader PDF** (primary) -- best accuracy, Apache 2.0, bounding boxes, hybrid AI mode
2. **MinerU** (fallback for CJK) -- 109 languages, strongest Vietnamese, VLM-enhanced
3. **Docling** (if MIT license required) -- best permissive license, multi-format, enterprise backing

Avoid: markitdown (too limited), Marker (license/speed issues), PyMuPDF-only (poor structure).
