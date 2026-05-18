# /pdf-convert install

Wires this repo into the Gemini CLI runtime as a single source of truth.
After install, the `/pdf-convert` slash command resolves directly to files
in this repo via symlinks — edit the repo, the runtime sees it immediately.

## Install

```bash
./install/install.sh                # commands + driver only
./install/install.sh --with-scripts # also symlink the Python pipeline
                                    # to <ANTIGRAVITY scripts dir>
```

Pre-existing files at the target paths are renamed `*.bak-<timestamp>` before
the symlink is created — nothing is overwritten silently.

## What gets linked

| Target (runtime)                                         | Source (this repo)                                |
| -------------------------------------------------------- | ------------------------------------------------- |
| `~/.gemini/commands/pdf-convert.toml`                    | `install/commands/pdf-convert.toml`               |
| `~/.gemini/pdf-convert/`                                 | `install/pdf-convert/`                            |
| `$ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts` * | `skill/pdf-vision-parser/scripts/`                |

\* only with `--with-scripts`. Defaults to `$HOME/ANTIGRAVITY/.agent/skills/pdf-vision-parser/scripts`; override with `ANTIGRAVITY_SCRIPTS=...`.

## Why this layout

Earlier versions shipped a workspace `.gemini/` inside the repo. When the
user also had `~/.gemini/commands/pdf-convert.toml`, Gemini CLI saw two
definitions of the same command and auto-renamed both to
`/workspace.pdf-convert` / `/user.pdf-convert`, breaking the bare
`/pdf-convert` invocation.

Moving the shipped files under `install/` (not `.gemini/`) means the repo is
no longer recognized as a workspace skill source by Gemini, eliminating the
collision. The installer then wires user-scope only.

## Uninstall

```bash
rm ~/.gemini/commands/pdf-convert.toml
rm ~/.gemini/pdf-convert
# (optional) restore the latest backup:
# mv ~/.gemini/commands/pdf-convert.toml.bak-<ts> ~/.gemini/commands/pdf-convert.toml
```
