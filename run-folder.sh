#!/usr/bin/env bash
#
# run-folder.sh — batch-convert every PDF in a folder, SEQUENTIALLY (one file at
# a time, never in parallel), through the /pdf-convert skill on Antigravity CLI
# (agy). Each file runs in a FRESH `agy -p` print session that drives the skill's
# NATIVE-VISION path: the active agy model reads each rendered page image itself.
# There is NO gemini -p subprocess and NO external API — Google retired the
# Gemini CLI, so the legacy subprocess driver is dead; agy native is the only
# working path. Sequential on purpose: one agy session at a time keeps Gemini
# request pressure low.
#
# Resume:     a PDF whose final JSON already exists (non-empty) is skipped.
# Retry:      re-invoke agy up to MAX_RETRIES on failure; optional model fallback.
# Fail-loud:  if a file never produces a non-empty JSON, stop AT that file and
#             print how to resume.
#
# Single-file use stays plain `/pdf-convert <file>` inside agy — this is only the
# unattended bulk wrapper around it.
#
# Usage:   run-folder.sh <folder-with-pdfs>
# Env:     PDF_MODEL        agy model         (default: "Gemini 3.1 Pro (High)")
#          PDF_FALLBACK     alt agy model     (default: ""  → just retry same model)
#          PDF_MAX_RETRIES  retries per file  (default: 10)
#          PDF_TIMEOUT      agy print timeout (default: 3h)
#          PDF_DRYRUN       =1 → print the agy command instead of running it

set -uo pipefail

MODEL="${PDF_MODEL:-Gemini 3.1 Pro (High)}"
FALLBACK="${PDF_FALLBACK:-}"
MAX_RETRIES="${PDF_MAX_RETRIES:-10}"
TIMEOUT="${PDF_TIMEOUT:-3h}"
DRYRUN="${PDF_DRYRUN:-0}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Final JSON destination — hardcoded by step3_merge.py; used for resume + verify.
OUT_DIR="/home/dung/ANTIGRAVITY/SÁCH CONVERT"

die() { echo "❌ $*" >&2; exit 1; }

[ $# -eq 1 ] || die "Usage: run-folder.sh <folder-with-pdfs>"
FOLDER="${1%/}"
[ -d "$FOLDER" ] || die "Không phải thư mục: $FOLDER"
command -v agy >/dev/null || die "Thiếu 'agy' CLI trong PATH."

# Pre-flight: fail loud if a pinned model no longer exists in agy (Google renames
# / retires models) instead of silently running a wrong/weaker one.
check_model() {
  agy models 2>/dev/null | grep -qF "$1" || {
    echo "❌ Model '$1' không còn trong agy. Danh sách hiện có:" >&2
    agy models >&2
    die "Sửa PDF_MODEL/PDF_FALLBACK rồi chạy lại."
  }
}
if [ "$DRYRUN" != "1" ]; then
  check_model "$MODEL"
  [ -n "$FALLBACK" ] && check_model "$FALLBACK"
fi

# Collect PDFs in lexical filename order; process them sequentially.
mapfile -t PDFS < <(find "$FOLDER" -maxdepth 1 -type f -iname '*.pdf' | sort)
[ ${#PDFS[@]} -gt 0 ] || die "Không có file *.pdf nào trong: $FOLDER"

echo "▶ Folder: $FOLDER | files: ${#PDFS[@]} | model: $MODEL${FALLBACK:+ → fallback $FALLBACK} | timeout/file: $TIMEOUT"
echo "  Output: $OUT_DIR"

# run_agy <file> <model> — one fresh agy print session driving /pdf-convert. The
# model does native-vision extraction per the skill; output lands in OUT_DIR.
# --add-dir grants workspace access to the inputs, repo scripts, the /tmp render
# workspace, and the output dir.
run_agy() {
  local file="$1" model="$2"
  local prompt="/pdf-convert \"$file\""
  if [ "$DRYRUN" = "1" ]; then
    echo "   DRYRUN: agy -p '$prompt' --model '$model' --print-timeout $TIMEOUT --dangerously-skip-permissions --add-dir '$REPO_DIR' --add-dir '$FOLDER' --add-dir /tmp --add-dir '$OUT_DIR'"
    return 0
  fi
  agy -p "$prompt" \
    --model "$model" \
    --print-timeout "$TIMEOUT" \
    --dangerously-skip-permissions \
    --add-dir "$REPO_DIR" \
    --add-dir "$FOLDER" \
    --add-dir /tmp \
    --add-dir "$OUT_DIR"
}

# convert_one <pdf> <out> — retry loop with optional model alternation. Stops the
# instant the output JSON appears; success is judged by the artifact, not by
# agy's exit code (a session can end noisily yet still have written the file).
convert_one() {
  local file="$1" out="$2" model="$MODEL" count=0
  while [ "$count" -lt "$MAX_RETRIES" ]; do
    echo "   [try $((count + 1))/$MAX_RETRIES] model=$model"
    run_agy "$file" "$model"
    [ -s "$out" ] && return 0
    echo "   ↻ chưa có output sau lần thử này."
    # Alternate to the fallback model if one is set; cool down after a full
    # primary->fallback->primary swing so quota can recover.
    if [ -n "$FALLBACK" ]; then
      if [ "$model" = "$MODEL" ]; then
        model="$FALLBACK"
      else
        model="$MODEL"
        echo "   ⏳ cả 2 model vừa fail liên tiếp — chờ 60s cho quota hồi..."
        sleep 60
      fi
    fi
    count=$((count + 1))
  done
  return 1
}

total=${#PDFS[@]}
idx=0
for file in "${PDFS[@]}"; do
  idx=$((idx + 1))
  stem="$(basename "${file%.*}")"
  out="$OUT_DIR/$stem.json"
  tag="$idx/$total $(basename "$file")"

  if [ -s "$out" ]; then
    echo "⏭  $tag — đã có output, skip ($out)"
    continue
  fi

  echo "▶ $tag — đang convert (agy native vision)"
  if [ "$DRYRUN" = "1" ]; then
    run_agy "$file" "$MODEL"
    echo "   (dry-run — bỏ qua verify)"
    continue
  fi

  convert_one "$file" "$out" || true

  # Verify the artifact ourselves before moving on.
  if [ ! -s "$out" ]; then
    echo "❌ $tag — không tạo được $out sau $MAX_RETRIES lần thử." >&2
    echo "   Resume: chạy lại CHÍNH lệnh này — file đã xong sẽ tự skip, dừng đúng file lỗi:" >&2
    echo "     $0 \"$FOLDER\"" >&2
    die "Dừng fail-loud tại: $file"
  fi
  echo "✅ $tag — xong ($out)"
done

echo "✔ Hoàn tất folder: $FOLDER (${total} file)"
