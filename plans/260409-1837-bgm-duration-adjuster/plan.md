---
title: BGM Duration Adjuster
status: in_progress
priority: high
created: 2026-04-09
blockedBy: []
blocks: []
---

# BGM Duration Adjuster

Portable Windows .exe tool — điều chỉnh độ dài nhạc nền khớp với audio truyện.
Stack: Python 3.12 + CustomTkinter + FFmpeg bundled + PyInstaller.

## Phases

| # | Phase | Status | File |
|---|-------|--------|------|
| 1 | Project Setup & Structure | ✅ done | [phase-01-project-setup.md](phase-01-project-setup.md) |
| 2 | Core Audio Engine | ✅ done | [phase-02-core-audio-engine.md](phase-02-core-audio-engine.md) |
| 3 | Waveform Canvas Widget | ✅ done | [phase-03-waveform-canvas.md](phase-03-waveform-canvas.md) |
| 4 | Single File Tab UI | ✅ done | [phase-04-ui-tab-single.md](phase-04-ui-tab-single.md) |
| 5 | Batch Tab UI | ✅ done | [phase-05-ui-tab-batch.md](phase-05-ui-tab-batch.md) |
| 6 | Build & Packaging | pending (Windows only) | [phase-06-build-packaging.md](phase-06-build-packaging.md) |

## Key Dependencies

- Python 3.12, customtkinter, scipy, numpy, sounddevice, soundfile, pyinstaller
- FFmpeg + FFprobe Windows binaries (bundled inside .exe)
- PyInstaller `--onefile --windowed`

## Output

`dist/bgm-adjuster.exe` — ~55MB, double-click portable, no install needed.
