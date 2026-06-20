#!/usr/bin/env bash
# install.sh — wire this repo into the Antigravity CLI (agy) runtime via symlinks
# so the repo stays the single source of truth (edit repo → runtime sees it).
#
# agy reads .agent/skills + .agent/workflows directly. We symlink the skill's
# SKILL.md and Python pipeline into the Antigravity skills dir:
#   <ANTIGRAVITY>/skills/pdf-vision-parser/scripts   → repo/skill/pdf-vision-parser/scripts/
#   <ANTIGRAVITY>/skills/pdf-vision-parser/SKILL.md   → repo/skill/pdf-vision-parser/SKILL.md
#
# (Google retired the Gemini CLI; its ~/.gemini wiring has been removed.)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANTIGRAVITY_SCRIPTS="${ANTIGRAVITY_SCRIPTS:-$HOME/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts}"

for arg in "$@"; do
    case "$arg" in
        -h|--help)
            sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

link_replace() {
    local target="$1" link="$2"
    [[ -e "$target" ]] || { echo "ERROR: target missing: $target" >&2; exit 1; }
    mkdir -p "$(dirname "$link")"
    if [[ -L "$link" ]]; then
        local cur; cur="$(readlink -f "$link")"
        if [[ "$cur" == "$(readlink -f "$target")" ]]; then
            echo "  ok   $link"
            return
        fi
        rm "$link"
    elif [[ -e "$link" ]]; then
        local ts; ts="$(date +%Y%m%d-%H%M%S)"
        mv "$link" "${link}.bak-${ts}"
        echo "  backup ${link} → ${link}.bak-${ts}"
    fi
    ln -s "$target" "$link"
    echo "  link $link → $target"
}

echo "[install] repo:                $REPO_ROOT"
echo "[install] antigravity scripts: $ANTIGRAVITY_SCRIPTS"

link_replace "$REPO_ROOT/skill/pdf-vision-parser/scripts" "$ANTIGRAVITY_SCRIPTS"
# Keep SKILL.md single-sourced too — a divergent copy is what let the dead
# subprocess path resurface before.
link_replace "$REPO_ROOT/skill/pdf-vision-parser/SKILL.md" "$(dirname "$ANTIGRAVITY_SCRIPTS")/SKILL.md"

echo "[install] done — verify with: agy then /pdf-convert <file>"
