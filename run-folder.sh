#!/usr/bin/env bash
#
# run-folder.sh — batch-convert every PDF in a folder, SEQUENTIALLY (one file at
# a time, never in parallel), through the /pdf-convert skill on Antigravity CLI
# (agy). The wrapper owns ALL deterministic orchestration; the agy model owns
# ONLY the vision step. This split is deliberate — it removes every place the
# model used to derail in unattended `-p` print mode:
#
#   1. Planning-loop: the model used to run prepare itself and the stale workflow
#      told it to pause for "Tiếp tục" — in print mode it exited at 0 pages.
#      → The wrapper pre-renders the workspace; the model starts at vision.
#   2. Filename thrash: the workspace name came from a model-chosen --name, so a
#      Vietnamese (diacritic) title was re-slugged differently each retry → a new
#      empty workspace each time → no resume. → The wrapper pins one deterministic
#      ASCII slug and passes the prepared workspace explicitly.
#   3. Legacy-script hunt: the model used to look for a "finish/merge" step and
#      `find /home` for deleted scripts, hanging on the gdrive mount. → The wrapper
#      runs QA + merge; the model never needs a finish step.
#
# There is NO gemini -p subprocess and NO external API — Google retired the
# Gemini CLI, so the legacy subprocess driver is dead; agy native vision is the
# only working path. Sequential on purpose: one agy session at a time keeps
# Gemini request pressure low.
#
# Resume:     a PDF whose final JSON already exists (non-empty) is skipped; the
#             /tmp workspace is kept so a re-run resumes only the missing pages.
# Retry:      re-invoke agy up to MAX_RETRIES on incomplete pages / QA-hard /
#             merge failure; optional model fallback alternation.
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
SCRIPTS="$REPO_DIR/skill/pdf-vision-parser/scripts"
# Final JSON destination — hardcoded by step3_merge.py; used for resume + verify.
OUT_DIR="/home/dung/ANTIGRAVITY/SÁCH CONVERT"

PYTHON="$HOME/.claude/skills/.venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

die() { echo "❌ $*" >&2; exit 1; }

[ $# -eq 1 ] || die "Usage: run-folder.sh <folder-with-pdfs>"
FOLDER="${1%/}"
[ -d "$FOLDER" ] || die "Không phải thư mục: $FOLDER"
command -v agy >/dev/null || die "Thiếu 'agy' CLI trong PATH."
[ -d "$SCRIPTS" ] || die "Thiếu scripts dir: $SCRIPTS"

# Deterministic ASCII slug from a filename stem — same input always yields the
# same workspace + output name, so retries reuse one workspace (no thrash) and
# diacritic titles never crash the model's name handling.
slugify() {
  "$PYTHON" - "$1" <<'PY'
import sys, re, unicodedata
s = sys.argv[1].replace("đ", "d").replace("Đ", "D")
s = unicodedata.normalize("NFKD", s)
s = "".join(c for c in s if not unicodedata.combining(c))
s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
print(s or "doc")
PY
}

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

# run_vision <file> <slug> <ws> <model> — ONE fresh agy print session that does
# only Step 2 (native vision). The workspace is already prepared; QA + merge are
# the wrapper's job, so the model has a single narrow task and no finish step to
# go hunting for.
#
# The prompt is the canonical ADE contract template rendered inline — NOT a
# `/pdf-convert` slash invocation. Proven on 1500+ pages (2026-06-24): the model
# ignores the ADE format when it reaches it through SKILL.md prose, but complies
# fully when given this concise contract + worked example directly.
run_vision() {
  local file="$1" slug="$2" ws="$3" model="$4" pages="$5"
  local template="$SCRIPTS/ade_prompt_vision.txt"
  [ -f "$template" ] || die "Thiếu prompt template: $template"
  local prompt
  prompt="$(sed -e "s|__PNG_DIR__|$ws/temp_png|g" \
                -e "s|__MD_DIR__|$ws/temp_md|g" \
                -e "s|__NPAGES__|$pages|g" "$template")

[WRAPPER MODE — BATCH] Source: $file | workspace: $ws (đã prepare sẵn, --name cố định = $slug).
- KHÔNG chạy prepare_native_workspace.sh / step2.75_qa_sweep.py / step3_merge.py và KHÔNG dọn workspace — wrapper tự lo QA + merge sau khi bạn xong.
- KHÔNG tìm/khôi phục script cũ. Chỉ view_file + write theo contract ở trên."
  if [ "$DRYRUN" = "1" ]; then
    echo "   DRYRUN: agy -p '<vision prompt for $slug>' --model '$model' --print-timeout $TIMEOUT --dangerously-skip-permissions --add-dir '$REPO_DIR' --add-dir '$FOLDER' --add-dir /tmp --add-dir '$OUT_DIR'"
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

# convert_one — vision/QA/merge retry loop with optional model alternation. Stops
# the instant the output JSON appears; success is judged by the artifact.
convert_one() {
  local file="$1" slug="$2" out="$3" ws="$4" manifest="$5" md_dir="$6" cache="$7" pages="$8"
  local model="$MODEL" count=0 have qa
  while [ "$count" -lt "$MAX_RETRIES" ]; do
    echo "   [try $((count + 1))/$MAX_RETRIES] model=$model"
    run_vision "$file" "$slug" "$ws" "$model" "$pages"

    have=$(find "$md_dir" -maxdepth 1 -name 'page_*.md' 2>/dev/null | wc -l)
    echo "   md: $have/$pages trang"
    if [ "$have" -ge "$pages" ] && [ "$pages" -gt 0 ]; then
      "$PYTHON" "$SCRIPTS/step2.75_qa_sweep.py" --md-dir "$md_dir" --manifest "$manifest"
      qa=$?
      # exit 0 = PASS, 2 = SOFT-only (acceptable) → merge; 1 = HARD → let model repair.
      if [ "$qa" -ne 1 ]; then
        if [ -n "$cache" ]; then
          "$PYTHON" "$SCRIPTS/step3_merge.py" --name "$slug" --md-dir "$md_dir" --docling-cache "$cache"
        else
          "$PYTHON" "$SCRIPTS/step3_merge.py" --name "$slug" --md-dir "$md_dir"
        fi
        [ -s "$out" ] && return 0
        echo "   ⚠ merge chưa tạo được JSON."
      else
        echo "   ⚠ QA HARD fail — retry để model mở lại trang lỗi và sửa."
      fi
    else
      echo "   ↻ chưa đủ trang — resume phiên vision."
    fi

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
  slug="$(slugify "$stem")"
  out="$OUT_DIR/$slug.json"
  tag="$idx/$total $(basename "$file")  [$slug]"

  if [ -s "$out" ]; then
    echo "⏭  $tag — đã có output, skip ($out)"
    continue
  fi

  echo "▶ $tag — đang convert (agy native vision)"

  # Step 1 (deterministic, no model): render PNG + manifest. Pin the ASCII slug
  # so the workspace is stable across retries.
  ws="/tmp/pdf_convert_$slug"
  echo "   prepare workspace → $ws"
  if [ "$DRYRUN" = "1" ]; then
    echo "   DRYRUN: prepare_native_workspace.sh \"$file\" --name \"$slug\" --keep-temp"
    run_vision "$file" "$slug" "$ws" "$MODEL" "N"
    echo "   (dry-run — bỏ qua QA/merge/verify)"
    continue
  fi

  manifest="$(PDF_CONVERT_SOURCE_SCRIPT_DIR="$SCRIPTS" bash "$SCRIPTS/prepare_native_workspace.sh" \
                "$file" --name "$slug" --keep-temp | tail -n1)"
  if [ -z "$manifest" ] || [ ! -s "$manifest" ]; then
    echo "❌ $tag — prepare_native_workspace.sh không tạo được manifest." >&2
    die "Dừng fail-loud tại: $file"
  fi

  # Pull workspace facts the retry loop needs from the manifest. One value per
  # line so an empty docling_cache (PDF fast-path) doesn't collapse the fields.
  { read -r pages; read -r md_dir; read -r cache; } < <("$PYTHON" - "$manifest" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
print(m.get("page_count", 0))
print(m.get("md_dir", ""))
print(m.get("docling_cache") or "")
PY
)
  if [ "${pages:-0}" -le 0 ]; then
    echo "❌ $tag — manifest 0 trang (render fail?). Xem $manifest" >&2
    die "Dừng fail-loud tại: $file"
  fi
  echo "   ready: $pages trang | md_dir=$md_dir"

  convert_one "$file" "$slug" "$out" "$ws" "$manifest" "$md_dir" "$cache" "$pages" || true

  # Verify the artifact ourselves before moving on.
  if [ ! -s "$out" ]; then
    echo "❌ $tag — không tạo được $out sau $MAX_RETRIES lần thử." >&2
    echo "   Workspace giữ tại $ws để resume." >&2
    echo "   Resume: chạy lại CHÍNH lệnh này — file đã xong sẽ tự skip, dừng đúng file lỗi:" >&2
    echo "     $0 \"$FOLDER\"" >&2
    die "Dừng fail-loud tại: $file"
  fi
  echo "✅ $tag — xong ($out)"
done

echo "✔ Hoàn tất folder: $FOLDER (${total} file)"
