#!/usr/bin/env bash
# auto_convert.sh - /pdf-convert automated Gemini CLI driver.
#
# This is the slash-command entrypoint. It intentionally runs page-level
# `gemini -p` subprocesses so large documents can finish without requiring the
# user to type "continue" after each active chat turn. Each subprocess handles
# one page, so context remains bounded and resume stays page-idempotent.
set -euo pipefail

SOURCE_SCRIPT_DIR="${PDF_CONVERT_SOURCE_SCRIPT_DIR:-/home/dung/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts}"
if [[ ! -d "$SOURCE_SCRIPT_DIR" ]]; then
    SOURCE_SCRIPT_DIR="/home/dung/VIBE_CODING/skill/pdf-vision-parser/scripts"
fi
if [[ ! -d "$SOURCE_SCRIPT_DIR" ]]; then
    echo "ERROR: pdf-vision-parser scripts not found. Set PDF_CONVERT_SOURCE_SCRIPT_DIR." >&2
    exit 1
fi

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${HOME}/.claude/skills/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3)"
fi

INPUT_FILE=""
OUTPUT_NAME=""
FAST_MODE=false
KEEP_TEMP=false

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
if [[ -z "$OUTPUT_NAME" ]]; then
    OUTPUT_NAME="$(basename "${INPUT_FILE%.*}")"
fi

PREPARE_ARGS=("$INPUT_FILE" --name "$OUTPUT_NAME" --keep-temp)
if [[ "$FAST_MODE" == "true" ]]; then
    PREPARE_ARGS+=(--fast)
fi

echo "[pdf-convert] STEP 1: prepare deterministic workspace" >&2
MANIFEST="$("$INSTALL_DIR/prepare_native_workspace.sh" "${PREPARE_ARGS[@]}")"

read_manifest_field() {
    "$PYTHON" - "$MANIFEST" "$1" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data.get(sys.argv[2], "")
if isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
PY
}

PNG_DIR="$(read_manifest_field png_dir)"
MD_DIR="$(read_manifest_field md_dir)"
CACHE_JSON="$(read_manifest_field docling_cache)"
SKIP_NATIVE="$(read_manifest_field skip_native_extraction)"
OUTPUT_JSON="$(read_manifest_field output_json)"
WORKSPACE="$(read_manifest_field workspace)"

PIPELINE_SUCCESS=false
cleanup() {
    if [[ "$KEEP_TEMP" == "false" && "$PIPELINE_SUCCESS" == "true" ]]; then
        rm -rf "$WORKSPACE"
        echo "[pdf-convert] cleaned temp: $WORKSPACE" >&2
    else
        echo "[pdf-convert] kept temp: $WORKSPACE (resume-capable)" >&2
    fi
}
trap cleanup EXIT

run_step2() {
    PDF_CONVERT_ALLOW_GEMINI_SUBPROCESS=1 \
        "$PYTHON" "$SOURCE_SCRIPT_DIR/step2_gemini_refine.py" "$CACHE_JSON" "$PNG_DIR" "$MD_DIR"
}

if [[ "$SKIP_NATIVE" == "true" ]]; then
    echo "[pdf-convert] STEP 2: skipped native Gemini extraction" >&2
else
    echo "[pdf-convert] STEP 2: automated page-level Gemini extraction" >&2
    run_step2
fi

echo "[pdf-convert] STEP 2.75: QA sweep with auto-repair" >&2
QA_ATTEMPTS=0
QA_MAX="${PDF_CONVERT_QA_MAX:-3}"
PREV_FAIL_SET=""
SOFT_ACCEPTED=false
while [[ "$QA_ATTEMPTS" -lt "$QA_MAX" ]]; do
    QA_RESULT=$("$PYTHON" "$SOURCE_SCRIPT_DIR/step2.75_qa_sweep.py" \
        --md-dir "$MD_DIR" \
        --manifest "$MANIFEST" 2>&1) && QA_STATUS=0 || QA_STATUS=$?
    printf '%s\n' "$QA_RESULT" >&2
    if [[ "$QA_STATUS" -eq 0 ]]; then
        break
    fi
    if [[ "$QA_STATUS" -eq 2 ]]; then
        # SOFT-only failures (figure/keyword false-positives). Retrying Gemini
        # almost never fixes these. Accept and proceed to merge.
        echo "[pdf-convert] QA reports SOFT-only critical errors — accepting and proceeding to merge." >&2
        SOFT_ACCEPTED=true
        break
    fi

    CRITICAL_PAGES=$(printf '%s\n' "$QA_RESULT" | grep -oP 'page_\d+\.md' | sort -u || true)
    if [[ -z "$CRITICAL_PAGES" || "$SKIP_NATIVE" == "true" ]]; then
        echo "[pdf-convert] QA failed and cannot auto-repair safely." >&2
        exit 1
    fi

    # Stuck-page detection: if the failing set is unchanged since last attempt,
    # repair won't help (Gemini will re-emit the same Markdown). Stop deleting.
    CURRENT_FAIL_SET=$(printf '%s\n' $CRITICAL_PAGES | sort -u | tr '\n' ' ')
    if [[ -n "$PREV_FAIL_SET" && "$CURRENT_FAIL_SET" == "$PREV_FAIL_SET" ]]; then
        echo "[pdf-convert] same pages failing same checks 2x in a row — stopping repair." >&2
        echo "[pdf-convert] stuck pages: $CURRENT_FAIL_SET" >&2
        exit 1
    fi
    PREV_FAIL_SET="$CURRENT_FAIL_SET"

    for f in $CRITICAL_PAGES; do
        echo "[pdf-convert] deleting bad page for retry: $f" >&2
        rm -f "$MD_DIR/$f"
    done

    QA_ATTEMPTS=$((QA_ATTEMPTS + 1))
    if [[ "$QA_ATTEMPTS" -ge "$QA_MAX" ]]; then
        echo "[pdf-convert] QA still failing after $QA_MAX repair attempts." >&2
        # Run one final classification pass to allow soft-accept
        QA_RESULT=$("$PYTHON" "$SOURCE_SCRIPT_DIR/step2.75_qa_sweep.py" \
            --md-dir "$MD_DIR" \
            --manifest "$MANIFEST" 2>&1) && FINAL_STATUS=0 || FINAL_STATUS=$?
        if [[ "$FINAL_STATUS" -eq 2 ]]; then
            echo "[pdf-convert] residual errors are SOFT-only — accepting and merging." >&2
            SOFT_ACCEPTED=true
            break
        fi
        exit 1
    fi
    run_step2
done

echo "[pdf-convert] STEP 3: merge JSON" >&2
"$PYTHON" "$SOURCE_SCRIPT_DIR/step3_merge.py" \
    --name "$OUTPUT_NAME" \
    --md-dir "$MD_DIR" \
    --docling-cache "$CACHE_JSON"

PIPELINE_SUCCESS=true
echo "[pdf-convert] DONE: $OUTPUT_JSON" >&2
