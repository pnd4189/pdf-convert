# /pdf-convert install

**Runtime = Antigravity CLI (`agy`).** Google retired the Gemini CLI (`gemini`
binary errors `IneligibleTierError`), so agy is the only live runtime. agy reads
`.agent/skills` + `.agent/workflows` directly. This installer symlinks the skill
into the Antigravity skills dir so the repo stays the single source of truth —
edit the repo, the runtime sees it immediately.

## Install

```bash
./install/install.sh    # symlink SKILL.md + Python pipeline into the agy skills dir
```

Override the target with `ANTIGRAVITY_SCRIPTS=...` (defaults to
`$HOME/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts`). Pre-existing files
at the target paths are renamed `*.bak-<timestamp>` before linking — nothing is
overwritten silently.

## What gets linked

| Target (runtime)                                        | Source (this repo)                 |
| ------------------------------------------------------- | ---------------------------------- |
| `$ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts`  | `skill/pdf-vision-parser/scripts/` |
| `$ANTIGRAVITY/.agent/skills/pdf-vision-parser/SKILL.md` | `skill/pdf-vision-parser/SKILL.md` |

## Batch conversion

`bash run-folder.sh <folder>` (repo root) converts every PDF in a folder
sequentially — one `agy -p "/pdf-convert ..."` session per file, native vision.

## Uninstall

```bash
rm "$HOME/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts"   # symlink
rm "$HOME/ANTIGRAVITY/.agent/skills/pdf-vision-parser/SKILL.md"  # symlink
```
