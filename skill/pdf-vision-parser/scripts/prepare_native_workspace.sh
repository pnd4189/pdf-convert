#!/usr/bin/env bash
# prepare_native_workspace.sh — preprocessing only for Gemini CLI native-model PDF conversion.
#
# This script intentionally stops before vision extraction. The active Gemini
# CLI slash-command model must inspect rendered page images itself and write
# page_N.md files. Do not call `gemini -p`, Google GenAI SDKs, Vertex, or any
# API-key path from here.
set -euo pipefail

SOURCE_SCRIPT_DIR="${PDF_CONVERT_SOURCE_SCRIPT_DIR:-/home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts}"
if [[ ! -d "$SOURCE_SCRIPT_DIR" ]]; then
    SOURCE_SCRIPT_DIR="/home/dung/VIBE_CODING/skill/pdf-vision-parser/scripts"
fi
if [[ ! -d "$SOURCE_SCRIPT_DIR" ]]; then
    echo "ERROR: pdf-vision-parser scripts not found. Set PDF_CONVERT_SOURCE_SCRIPT_DIR." >&2
    exit 1
fi

PYTHON="${HOME}/.claude/skills/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3)"
fi

python_has_module() {
    "$1" -c "import $2" >/dev/null 2>&1
}

FITZ_PYTHON="$PYTHON"
if ! python_has_module "$FITZ_PYTHON" fitz && command -v python3 >/dev/null && python3 -c "import fitz" >/dev/null 2>&1; then
    FITZ_PYTHON="$(command -v python3)"
fi
export HF_HUB_OFFLINE=1

INPUT_FILE=""
OUTPUT_NAME=""
FAST_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fast)        FAST_MODE=true; shift ;;
        --keep-temp)   shift ;;
        --name)        OUTPUT_NAME="$2"; shift 2 ;;
        -*)            echo "Unknown flag: $1" >&2; exit 1 ;;
        *)             INPUT_FILE="$1"; shift ;;
    esac
done

if [[ -z "$INPUT_FILE" ]]; then
    echo "Usage: prepare_native_workspace.sh <input_file> [--fast] [--keep-temp] [--name <output_name>]" >&2
    exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "ERROR: File not found: $INPUT_FILE" >&2
    exit 1
fi

if [[ -z "$OUTPUT_NAME" ]]; then
    OUTPUT_NAME="$(basename "${INPUT_FILE%.*}")"
fi

TEMP_BASE="/tmp/pdf_convert_${OUTPUT_NAME}"
TEMP_PNG="${TEMP_BASE}/temp_png"
TEMP_MD="${TEMP_BASE}/temp_md"
mkdir -p "$TEMP_PNG" "$TEMP_MD"

FILE_EXT="${INPUT_FILE##*.}"
FILE_EXT="${FILE_EXT,,}"
IS_EPUB=false
[[ "$FILE_EXT" == "epub" ]] && IS_EPUB=true

IS_IMAGE=false
case "$FILE_EXT" in
    png|jpg|jpeg|gif|webp|bmp|tif|tiff) IS_IMAGE=true ;;
esac

echo "[prepare_native] input: $INPUT_FILE (format: $FILE_EXT)" >&2
echo "[prepare_native] output name: $OUTPUT_NAME" >&2
echo "[prepare_native] workspace: $TEMP_BASE" >&2
echo "[prepare_native] mode: ACTIVE_GEMINI_CLI_MODEL_ONLY (no subprocess Gemini/API)" >&2

# Docling is unreliable for PDFs (sparse extraction on OCR'd / scanned-like PDFs
# leads to visual_audit false-positives + repair-loop blowups). PDFs now always
# go vision-only. Images skip Docling too — they're already pure vision input.
# Docling stays load-bearing for DOCX/PPTX/EPUB where structural extraction wins.
if [[ "$FILE_EXT" == "pdf" || "$IS_IMAGE" == "true" ]]; then
    if [[ "$FAST_MODE" == "false" ]]; then
        echo "[prepare_native] $FILE_EXT format -> bypassing Docling (vision-only pipeline)" >&2
    fi
    FAST_MODE=true
fi

CACHE_JSON_PATH=""
if [[ "$FAST_MODE" == "false" ]]; then
    echo "[prepare_native] STEP 0: cache check" >&2
    CACHE_RESULT=$("$PYTHON" "$SOURCE_SCRIPT_DIR/step0_cache_check.py" "$INPUT_FILE")
    CACHED=$(echo "$CACHE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d['cached']).lower())")
    CACHE_KEY=$(echo "$CACHE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['key'])")
    CACHE_JSON_PATH=$(echo "$CACHE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['path'])")
    echo "[prepare_native] cache hit: $CACHED (key: ${CACHE_KEY:0:16}...)" >&2

    if [[ "$CACHED" == "false" ]]; then
        echo "[prepare_native] STEP 1: Docling parse" >&2
        CACHE_JSON_PATH=$("$PYTHON" "$SOURCE_SCRIPT_DIR/step1_docling_parse.py" "$INPUT_FILE" --cache-key "$CACHE_KEY")
        echo "[prepare_native] Docling cache written: $CACHE_JSON_PATH" >&2
    fi

    echo "[prepare_native] STEP 1.5: render pages" >&2
    if ! "$PYTHON" "$SOURCE_SCRIPT_DIR/step1.5_render_pages.py" "$CACHE_JSON_PATH" "$TEMP_PNG" "$INPUT_FILE" >&2; then
        echo "[prepare_native] WARNING: page rendering failed — native extraction may be text-only" >&2
        touch "$TEMP_PNG/.skip"
    fi
else
    echo "[prepare_native] STEP 1 (fast): split via step1_split.py ($FILE_EXT)" >&2
    "$FITZ_PYTHON" "$SOURCE_SCRIPT_DIR/step1_split.py" "$INPUT_FILE" "$TEMP_PNG" >&2
    PAGE_COUNT=$(find "$TEMP_PNG" -maxdepth 1 -name '*.png' | wc -l)
    CACHE_JSON_PATH="${TEMP_BASE}/fast_cache.json"
    "$PYTHON" -c "
import json
pages = [{'page_no': i, 'elements': [], 'tables': [], 'size': [0, 0]} for i in range(1, $PAGE_COUNT + 1)]
print(json.dumps({'version': 'fast-native', 'source_hash': '', 'format': '$FILE_EXT', 'pages': pages}))
" > "$CACHE_JSON_PATH"
fi

EPUB_SKIP_GEMINI=false
if [[ "$IS_EPUB" == "true" && "$FAST_MODE" == "false" && -n "$CACHE_JSON_PATH" ]]; then
    echo "[prepare_native] STEP 1.7: EPUB fast-path routing" >&2
    EPUB_ROUTE_RESULT=$("$PYTHON" "$SOURCE_SCRIPT_DIR/step1_7_epub_route.py" "$CACHE_JSON_PATH" "$TEMP_MD" "$TEMP_BASE")
    echo "[prepare_native] EPUB routing: $EPUB_ROUTE_RESULT" >&2

    EPUB_GEMINI_CACHE=$(echo "$EPUB_ROUTE_RESULT" | grep -oP 'media_cache=\K[^\s]+' || true)
    MEDIA_COUNT=$(echo "$EPUB_ROUTE_RESULT" | grep -oP 'media_pages=\K\d+' || echo "0")
    if [[ -n "$EPUB_GEMINI_CACHE" && "$MEDIA_COUNT" -gt "0" ]]; then
        CACHE_JSON_PATH="$EPUB_GEMINI_CACHE"
        echo "[prepare_native] EPUB: $MEDIA_COUNT media page(s) queued for native model extraction" >&2
    else
        echo "[prepare_native] EPUB: all text-only — native vision step skipped" >&2
        EPUB_SKIP_GEMINI=true
    fi
fi

MANIFEST="${TEMP_BASE}/native_manifest.json"
SKIP_VISUAL_AUDIT="false"
if [[ "$FILE_EXT" == "pdf" || "$FAST_MODE" == "true" ]]; then
    # No reliable Docling baseline -> visual_audit would false-positive on every
    # text-dense page. Trust Gemini vision instead.
    SKIP_VISUAL_AUDIT="true"
fi

"$PYTHON" - "$INPUT_FILE" "$OUTPUT_NAME" "$TEMP_BASE" "$TEMP_PNG" "$TEMP_MD" "$CACHE_JSON_PATH" "$EPUB_SKIP_GEMINI" "$SOURCE_SCRIPT_DIR" "$SKIP_VISUAL_AUDIT" "$FILE_EXT" > "$MANIFEST" <<'PY'
import json
import sys
from pathlib import Path
import importlib.util

(input_file, output_name, temp_base, png_dir, md_dir, cache_json,
 skip_native, source_script_dir, skip_visual_audit, file_ext) = sys.argv[1:]
pages = []
cache_path = Path(cache_json)
if cache_json and cache_path.exists():
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        pages = [p.get("page_no") for p in data.get("pages", []) if p.get("page_no") is not None]
    except Exception:
        pages = []
if not pages:
    pages = sorted(int(p.stem) for p in Path(png_dir).glob("*.png") if p.stem.isdigit())

# visual_audit only runs when we have a real Docling baseline. For PDFs (now
# always vision-only) and other formats explicitly opted out, skip it.
visual_candidates = []
skip_va = skip_visual_audit.lower() == "true"
visual_audit_path = Path(source_script_dir) / "visual_audit.py"
if (not skip_va and cache_json and visual_audit_path.exists()
        and not (Path(png_dir) / ".skip").exists()):
    spec = importlib.util.spec_from_file_location("pdf_convert_visual_audit", visual_audit_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        visual_candidates = module.build_visual_candidates(cache_json, png_dir)

print(json.dumps({
    "mode": "active_gemini_cli_model_only",
    "input_file": input_file,
    "output_name": output_name,
    "format": file_ext,
    "workspace": temp_base,
    "png_dir": png_dir,
    "md_dir": md_dir,
    "docling_cache": cache_json,
    "visual_candidates": visual_candidates,
    "skip_visual_audit": skip_va,
    "skip_native_extraction": skip_native.lower() == "true",
    "pages": pages,
    "page_count": len(pages),
    "output_json": f"/home/dung/ANTIGRAVITY/SÁCH CONVERT/{output_name}.json",
}, ensure_ascii=False, indent=2))
PY

echo "[prepare_native] READY: $MANIFEST" >&2
echo "[prepare_native] Rendered pages: $TEMP_PNG" >&2
echo "[prepare_native] Markdown output dir: $TEMP_MD" >&2
echo "$MANIFEST"
