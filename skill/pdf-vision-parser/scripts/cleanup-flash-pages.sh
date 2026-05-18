#!/usr/bin/env bash
# cleanup-flash-pages.sh — Remove specific page_N.md files from a /pdf-convert
# workspace so the next /pdf-convert run regenerates them (typically: pages
# originally written by a degraded Flash model after an auto-cascade event).
#
# Backs up temp_md/ to temp_md.bak-<timestamp>/ before any deletion. Dry-run
# by default — pass `apply` as the third arg to actually delete.
#
# Usage:
#   cleanup-flash-pages.sh <workspace_dir> <page_list>           # dry-run
#   cleanup-flash-pages.sh <workspace_dir> <page_list> apply     # delete
#
# page_list grammar: comma-separated tokens where each token is either a
# single page number (e.g. "42") or an inclusive range "A-B" (e.g. "220-824").
set -euo pipefail

if [[ $# -lt 2 ]]; then
    cat >&2 <<EOF
Usage: $(basename "$0") <workspace_dir> <page_list> [dry-run|apply]
  page_list: "220-824,2,4,36-37,40"
  mode     : dry-run (default) | apply
EOF
    exit 64
fi

WORKSPACE="$1"
PAGE_LIST="$2"
MODE="${3:-dry-run}"

if [[ ! -d "$WORKSPACE" ]]; then
    echo "ERROR: workspace not found: $WORKSPACE" >&2
    exit 1
fi
TEMP_MD="$WORKSPACE/temp_md"
if [[ ! -d "$TEMP_MD" ]]; then
    echo "ERROR: temp_md dir not found inside workspace: $TEMP_MD" >&2
    exit 1
fi
case "$MODE" in
    dry-run|apply) ;;
    *) echo "ERROR: mode must be 'dry-run' or 'apply', got '$MODE'" >&2; exit 64 ;;
esac

# Expand "220-824,2,4,36-37" → sorted unique page numbers (one per line).
expand_pages() {
    local list="$1"
    python3 - "$list" <<'PY'
import sys
spec = sys.argv[1]
out = set()
for tok in spec.split(","):
    tok = tok.strip()
    if not tok: continue
    if "-" in tok:
        a, b = tok.split("-", 1)
        for n in range(int(a), int(b) + 1):
            out.add(n)
    else:
        out.add(int(tok))
for n in sorted(out):
    print(n)
PY
}

mapfile -t PAGES < <(expand_pages "$PAGE_LIST")
TOTAL_REQUESTED=${#PAGES[@]}
echo "[cleanup] target pages requested: $TOTAL_REQUESTED"
echo "[cleanup] workspace: $WORKSPACE"
echo "[cleanup] mode: $MODE"

EXISTING=()
MISSING=()
for p in "${PAGES[@]}"; do
    f="$TEMP_MD/page_${p}.md"
    if [[ -f "$f" ]]; then
        EXISTING+=("$p")
    else
        MISSING+=("$p")
    fi
done
echo "[cleanup] existing files matched: ${#EXISTING[@]}"
echo "[cleanup] requested-but-missing: ${#MISSING[@]}"

if [[ "$MODE" == "dry-run" ]]; then
    echo "[cleanup] DRY-RUN — no files modified. Re-run with 'apply' to delete."
    exit 0
fi

if [[ ${#EXISTING[@]} -eq 0 ]]; then
    echo "[cleanup] nothing to delete."
    exit 0
fi

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="$WORKSPACE/temp_md.bak-$TS"
echo "[cleanup] backing up $TEMP_MD → $BACKUP"
cp -a "$TEMP_MD" "$BACKUP"

for p in "${EXISTING[@]}"; do
    rm -f "$TEMP_MD/page_${p}.md"
done
RETAINED=$(find "$TEMP_MD" -maxdepth 1 -name 'page_*.md' | wc -l)
echo "[cleanup] deleted: ${#EXISTING[@]}"
echo "[cleanup] retained in temp_md: $RETAINED"
echo "[cleanup] backup preserved at: $BACKUP"
