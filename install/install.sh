#!/usr/bin/env bash
# install.sh — wire repo files into the Gemini CLI runtime via symlinks.
#
# Layout after install:
#   ~/.gemini/commands/pdf-convert.toml  → repo/install/commands/pdf-convert.toml
#   ~/.gemini/pdf-convert/               → repo/install/pdf-convert/
#
# Optional (--with-scripts): also wire the Python pipeline so SOURCE_SCRIPT_DIR
# resolves to the repo's skill dir instead of an out-of-tree copy:
#   <ANTIGRAVITY scripts dir>            → repo/skill/pdf-vision-parser/scripts/
#
# Symlinks (not copies) keep the repo as the single source of truth, so any
# edit in the repo is reflected in the live runtime without re-running install.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="$REPO_ROOT/install"
GEMINI_HOME="${GEMINI_HOME:-$HOME/.gemini}"
ANTIGRAVITY_SCRIPTS="${ANTIGRAVITY_SCRIPTS:-$HOME/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts}"

WITH_SCRIPTS=0
for arg in "$@"; do
    case "$arg" in
        --with-scripts) WITH_SCRIPTS=1 ;;
        -h|--help)
            sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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

echo "[install] repo:        $REPO_ROOT"
echo "[install] gemini home: $GEMINI_HOME"

link_replace "$INSTALL_DIR/commands/pdf-convert.toml" "$GEMINI_HOME/commands/pdf-convert.toml"
link_replace "$INSTALL_DIR/pdf-convert"               "$GEMINI_HOME/pdf-convert"

if [[ "$WITH_SCRIPTS" -eq 1 ]]; then
    echo "[install] antigravity scripts target: $ANTIGRAVITY_SCRIPTS"
    link_replace "$REPO_ROOT/skill/pdf-vision-parser/scripts" "$ANTIGRAVITY_SCRIPTS"
fi

echo "[install] done — verify with: gemini /pdf-convert"
