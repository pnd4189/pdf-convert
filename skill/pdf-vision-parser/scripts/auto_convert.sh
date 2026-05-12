#!/usr/bin/env bash
# auto_convert.sh — Docling+Gemini hybrid PDF conversion pipeline
# Usage: auto_convert.sh <input_file> [--fast] [--keep-temp] [--name <output_name>]
#
# Pipeline: step0 → step1 (if cache miss) → step1.5 → step2 → step2.75 → step3
# EPUB fast-path: text-only chapters skip step2 (Gemini); only media chapters go through Gemini
# PPTX/DOCX/HTML/Image: handled by Docling step1 natively; full pipeline applies
# --fast: skip Docling, use legacy step1_split.py (Gemini vision-only, PDF only)
# --keep-temp: preserve temp_png/ and temp_md/ after completion
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${HOME}/.claude/skills/.venv/bin/python3"
# Prevent Docling from phoning home to HuggingFace CDN when models are already cached
export HF_HUB_OFFLINE=1

# ── Parse arguments ──────────────────────────────────────────────────────────
INPUT_FILE=""
FAST_MODE=false
KEEP_TEMP=false
OUTPUT_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fast)        FAST_MODE=true; shift ;;
        --keep-temp)   KEEP_TEMP=true; shift ;;
        --name)        OUTPUT_NAME="$2"; shift 2 ;;
        -*)            echo "Unknown flag: $1" >&2; exit 1 ;;
        *)             INPUT_FILE="$1"; shift ;;
    esac
done

if [[ -z "$INPUT_FILE" ]]; then
    echo "Usage: auto_convert.sh <input_file> [--fast] [--keep-temp] [--name <output_name>]" >&2
    exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "ERROR: File not found: $INPUT_FILE" >&2
    exit 1
fi

# Default output name = input file stem
if [[ -z "$OUTPUT_NAME" ]]; then
    OUTPUT_NAME="$(basename "${INPUT_FILE%.*}")"
fi

# ── Deterministic temp directories (resume-capable) ──────────────────────────
# Keyed by OUTPUT_NAME so re-runs find previous results
TEMP_BASE="/tmp/pdf_convert_${OUTPUT_NAME}"
TEMP_PNG="${TEMP_BASE}/temp_png"
TEMP_MD="${TEMP_BASE}/temp_md"
mkdir -p "$TEMP_PNG" "$TEMP_MD"

PIPELINE_SUCCESS=false
cleanup() {
    if [[ "$KEEP_TEMP" == "false" && "$PIPELINE_SUCCESS" == "true" ]]; then
        rm -rf "$TEMP_BASE"
        echo "[auto_convert] cleaned temp: $TEMP_BASE" >&2
    else
        echo "[auto_convert] kept temp: $TEMP_BASE (for resume)" >&2
    fi
}
trap cleanup EXIT

FILE_EXT="${INPUT_FILE##*.}"
FILE_EXT="${FILE_EXT,,}"  # lowercase
IS_EPUB=false
[[ "$FILE_EXT" == "epub" ]] && IS_EPUB=true

echo "[auto_convert] input: $INPUT_FILE (format: $FILE_EXT)" >&2
echo "[auto_convert] output name: $OUTPUT_NAME" >&2
echo "[auto_convert] fast_mode: $FAST_MODE | epub_fast_path: $IS_EPUB" >&2
echo "[auto_convert] workspace: $TEMP_BASE" >&2

# ── Auto-detect scanned PDF ──────────────────────────────────────────────────
if [[ "$FILE_EXT" == "pdf" && "$FAST_MODE" == "false" ]]; then
    AVG_CHARS=$("$PYTHON" -c "
import fitz, sys
try:
    doc = fitz.open(sys.argv[1])
    total = sum(len(p.get_text()) for p in doc)
    n = max(len(doc), 1)
    print(total // n)
    doc.close()
except Exception:
    print(999)
" "$INPUT_FILE" 2>/dev/null || echo "999")
    if [[ "$AVG_CHARS" -lt 5 ]]; then
        echo "[auto_convert] detected scanned PDF (avg ${AVG_CHARS} chars/page) → fast mode" >&2
        FAST_MODE=true
    fi
fi

# ── STEP 0: Cache check ───────────────────────────────────────────────────────
CACHE_KEY=""
CACHE_JSON_PATH=""
CACHED=false

if [[ "$FAST_MODE" == "false" ]]; then
    echo "[auto_convert] STEP 0: cache check" >&2
    CACHE_RESULT=$("$PYTHON" "$SCRIPT_DIR/step0_cache_check.py" "$INPUT_FILE")
    CACHED=$(echo "$CACHE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d['cached']).lower())")
    CACHE_KEY=$(echo "$CACHE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['key'])")
    CACHE_JSON_PATH=$(echo "$CACHE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['path'])")
    echo "[auto_convert] cache hit: $CACHED (key: ${CACHE_KEY:0:16}...)" >&2
fi

# ── STEP 1: Docling parse (cache miss only) ───────────────────────────────────
if [[ "$FAST_MODE" == "false" && "$CACHED" == "false" ]]; then
    echo "[auto_convert] STEP 1: Docling parse" >&2
    CACHE_JSON_PATH=$("$PYTHON" "$SCRIPT_DIR/step1_docling_parse.py" "$INPUT_FILE" --cache-key "$CACHE_KEY")
    echo "[auto_convert] Docling cache written: $CACHE_JSON_PATH" >&2
fi

# ── STEP 1 (fast/legacy): PDF → PNG via step1_split ─────────────────────────
if [[ "$FAST_MODE" == "true" ]]; then
    echo "[auto_convert] STEP 1 (fast): PDF split via step1_split.py" >&2
    "$PYTHON" "$SCRIPT_DIR/step1_split.py" "$INPUT_FILE" "$TEMP_PNG"
fi

# ── STEP 1.5: Render pages to PNG (skipped in fast mode — step1_split already did it) ──
if [[ "$FAST_MODE" == "false" ]]; then
    echo "[auto_convert] STEP 1.5: render pages" >&2
    if ! "$PYTHON" "$SCRIPT_DIR/step1.5_render_pages.py" "$CACHE_JSON_PATH" "$TEMP_PNG" "$INPUT_FILE"; then
        echo "[auto_convert] WARNING: page rendering failed — proceeding without images" >&2
    fi
fi

# ── STEP 1.7: EPUB fast-path routing ─────────────────────────────────────────
# Text-only chapters skip Gemini; only media-bearing chapters go through step2.
# Saves ≥70% Gemini token usage on text-heavy EPUBs (novels, textbooks).
EPUB_SKIP_GEMINI=false
if [[ "$IS_EPUB" == "true" && "$FAST_MODE" == "false" && -n "$CACHE_JSON_PATH" ]]; then
    echo "[auto_convert] STEP 1.7: EPUB fast-path routing" >&2
    EPUB_ROUTE_RESULT=$("$PYTHON" "$SCRIPT_DIR/step1_7_epub_route.py" "$CACHE_JSON_PATH" "$TEMP_MD" "$TEMP_BASE")
    echo "[auto_convert] EPUB routing: $EPUB_ROUTE_RESULT" >&2

    EPUB_GEMINI_CACHE=$(echo "$EPUB_ROUTE_RESULT" | grep -oP 'media_cache=\K[^\s]+' || true)
    MEDIA_COUNT=$(echo "$EPUB_ROUTE_RESULT" | grep -oP 'media_pages=\K\d+' || echo "0")

    if [[ -n "$EPUB_GEMINI_CACHE" && "$MEDIA_COUNT" -gt "0" ]]; then
        CACHE_JSON_PATH="$EPUB_GEMINI_CACHE"
        echo "[auto_convert] EPUB: $MEDIA_COUNT media page(s) queued for Gemini" >&2
    else
        echo "[auto_convert] EPUB: all text-only — skipping Gemini entirely" >&2
        EPUB_SKIP_GEMINI=true
    fi
fi

# ── STEP 2: Gemini ADE refinement ────────────────────────────────────────────
if [[ "$EPUB_SKIP_GEMINI" == "true" ]]; then
    echo "[auto_convert] STEP 2: SKIPPED (EPUB text-only fast-path)" >&2
else
    echo "[auto_convert] STEP 2: Gemini refine" >&2
    if [[ "$FAST_MODE" == "true" ]]; then
        # Legacy: create a minimal fake cache JSON for step2 compatibility
        FAKE_CACHE="${TEMP_BASE}/fast_cache.json"
        PAGE_COUNT=$(ls "$TEMP_PNG"/*.png 2>/dev/null | wc -l)
        "$PYTHON" -c "
import json, sys
pages = [{'page_no': i, 'elements': [], 'tables': [], 'size': [0,0]} for i in range(1, $PAGE_COUNT + 1)]
print(json.dumps({'version':'fast','source_hash':'','format':'pdf','pages':pages}))
" > "$FAKE_CACHE"
        CACHE_JSON_PATH="$FAKE_CACHE"
    fi
    # Graceful: don't let partial failure kill pipeline
    "$PYTHON" "$SCRIPT_DIR/step2_gemini_refine.py" "$CACHE_JSON_PATH" "$TEMP_PNG" "$TEMP_MD" || true
fi

# ── STEP 2.75: QA sweep with retry ───────────────────────────────────────────
echo "[auto_convert] STEP 2.75: QA sweep" >&2
QA_ATTEMPTS=0
QA_MAX=3
while [[ $QA_ATTEMPTS -lt $QA_MAX ]]; do
    QA_RESULT=$("$PYTHON" "$SCRIPT_DIR/step2.75_qa_sweep.py" --md-dir "$TEMP_MD" 2>&1) || true
    CRITICAL_PAGES=$(echo "$QA_RESULT" | grep -oP 'page_\d+\.md' | sort -u || true)
    CRITICAL_COUNT=$(echo "$CRITICAL_PAGES" | grep -c '.' || echo "0")
    echo "[auto_convert] QA attempt $((QA_ATTEMPTS+1)): $CRITICAL_COUNT pages with CRITICAL issues" >&2
    if [[ "$CRITICAL_COUNT" == "0" || -z "$CRITICAL_PAGES" ]]; then
        break
    fi

    # Delete bad page files so step2 re-processes them (page-level caching skips good ones)
    for f in $CRITICAL_PAGES; do
        echo "[auto_convert] deleting bad page for retry: $f" >&2
        rm -f "$TEMP_MD/$f"
    done

    # Re-run step2 for failed pages only (cached pages skipped)
    if [[ "$EPUB_SKIP_GEMINI" != "true" ]]; then
        "$PYTHON" "$SCRIPT_DIR/step2_gemini_refine.py" "$CACHE_JSON_PATH" "$TEMP_PNG" "$TEMP_MD" || true
    fi

    QA_ATTEMPTS=$((QA_ATTEMPTS + 1))
    if [[ $QA_ATTEMPTS -ge $QA_MAX ]]; then
        echo "[auto_convert] WARNING: CRITICAL issues remain after $QA_MAX attempts — proceeding" >&2
    fi
done

# ── STEP 3: Merge → final JSON ────────────────────────────────────────────────
echo "[auto_convert] STEP 3: merge → JSON" >&2
DOCLING_ARG=""
if [[ "$FAST_MODE" == "false" && -n "$CACHE_JSON_PATH" ]]; then
    DOCLING_ARG="--docling-cache $CACHE_JSON_PATH"
fi

"$PYTHON" "$SCRIPT_DIR/step3_merge.py" \
    --name "$OUTPUT_NAME" \
    --md-dir "$TEMP_MD" \
    $DOCLING_ARG

PIPELINE_SUCCESS=true
echo "[auto_convert] DONE: /home/dung/ANTIGRAVITY/SÁCH CONVERT/${OUTPUT_NAME}.json" >&2
