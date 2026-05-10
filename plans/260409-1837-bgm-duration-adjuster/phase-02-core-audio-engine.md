# Phase 2: Core Audio Engine

## Overview
- **Priority:** High (blocker cho Phase 3, 4, 5)
- **Status:** pending
- **Goal:** FFmpeg subprocess wrapper, smart loop detection, normalize

## Files to Create
- `core/audio_processor.py` — FFmpeg logic chính
- `core/smart_loop.py` — Zero-crossing detection

---

## 2.1 audio_processor.py

### Lấy duration bằng ffprobe
```python
import subprocess, os, re
from core.audio_processor import get_ffprobe_path, get_ffmpeg_path

def get_duration(filepath: str) -> float:
    """Return duration in seconds."""
    cmd = [
        get_ffprobe_path(), "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())
```

### Đọc waveform samples (dùng soundfile, không cần ffmpeg)
```python
import soundfile as sf
import numpy as np

def read_waveform_samples(filepath: str, max_points: int = 1000) -> np.ndarray:
    """Read audio, downsample to max_points for waveform display."""
    data, samplerate = sf.read(filepath, always_2d=True)
    mono = data.mean(axis=1)  # stereo → mono
    # Downsample
    step = max(1, len(mono) // max_points)
    samples = mono[::step][:max_points]
    # Normalize to [-1, 1]
    peak = np.abs(samples).max()
    if peak > 0:
        samples = samples / peak
    return samples
```

### Process BGM (loop/trim + fade + volume + normalize)
```python
def process_bgm(
    bgm_path: str,
    narration_duration: float,
    output_path: str,
    volume: float = 1.0,          # 0.0–1.0
    fade_in: float = 0.0,         # seconds
    fade_out: float = 3.0,        # seconds
    normalize: bool = True,
    output_format: str = "mp3",   # "mp3" | "wav"
    bitrate: str = "192k",        # mp3 only
    loop_point: float = None,     # smart loop point offset (seconds)
    progress_callback=None,       # callable(percent: float)
):
    bgm_duration = get_duration(bgm_path)
    
    # Build audio filter chain
    filters = []
    if volume != 1.0:
        filters.append(f"volume={volume:.2f}")
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in:.2f}")
    fade_start = max(0, narration_duration - fade_out)
    if fade_out > 0:
        filters.append(f"afade=t=out:st={fade_start:.2f}:d={fade_out:.2f}")
    if normalize:
        filters.append("loudnorm=I=-18:LRA=11:TP=-1.5")
    
    af = ",".join(filters) if filters else None
    
    # Build ffmpeg command
    cmd = [get_ffmpeg_path(), "-y"]
    
    if bgm_duration < narration_duration:
        # Need to loop
        cmd += ["-stream_loop", "-1"]
    
    cmd += ["-i", bgm_path]
    cmd += ["-t", str(narration_duration)]
    
    if af:
        cmd += ["-af", af]
    
    # Output format
    if output_format == "mp3":
        cmd += ["-codec:a", "libmp3lame", "-b:a", bitrate]
    else:  # wav
        cmd += ["-codec:a", "pcm_s16le"]
    
    cmd += [output_path]
    
    # Run with progress parsing
    _run_ffmpeg_with_progress(cmd, narration_duration, progress_callback)
```

### Progress parsing từ FFmpeg stderr
```python
def _run_ffmpeg_with_progress(cmd, total_duration, callback=None):
    """Parse ffmpeg stderr for time= field to report progress."""
    proc = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, text=True, 
        encoding="utf-8", errors="replace"
    )
    time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    
    for line in proc.stderr:
        if callback and (m := time_pattern.search(line)):
            h, m2, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            current = h * 3600 + m2 * 60 + s
            percent = min(100.0, current / total_duration * 100)
            callback(percent)
    
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg failed with code {proc.returncode}")
```

---

## 2.2 smart_loop.py — Zero-Crossing Detection

**Mục đích:** Tìm điểm trong BGM gần cuối file nhất mà waveform đang qua zero → tránh pop/click khi loop.

```python
import soundfile as sf
import numpy as np

def find_best_loop_point(filepath: str, search_window: float = 2.0) -> float:
    """
    Find best loop point near end of audio using zero-crossing detection.
    
    Returns offset in seconds from END of file where loop is cleanest.
    search_window: how many seconds before end to search (default 2s).
    """
    data, samplerate = sf.read(filepath, always_2d=True)
    mono = data.mean(axis=1)
    
    total_samples = len(mono)
    window_samples = int(search_window * samplerate)
    search_start = max(0, total_samples - window_samples)
    
    # Find zero crossings in search window
    segment = mono[search_start:]
    signs = np.sign(segment)
    crossings = np.where(np.diff(signs) != 0)[0]
    
    if len(crossings) == 0:
        return 0.0  # fallback: no smart loop
    
    # Pick crossing closest to end
    best_crossing = crossings[-1]
    offset_from_end = (window_samples - best_crossing) / samplerate
    return offset_from_end


def get_smart_loop_trim_point(filepath: str) -> float:
    """
    Return trim point (seconds from start) for cleanest loop.
    Use as: ffmpeg -i bgm.mp3 -t {trim_point} ...
    """
    duration = get_duration(filepath)  # import from audio_processor
    offset = find_best_loop_point(filepath)
    return duration - offset
```

**Tích hợp vào process_bgm:**
- Nếu `smart_loop=True` và bgm_duration < narration_duration:
  - Tính `trim_point = get_smart_loop_trim_point(bgm_path)`
  - Dùng concat filter thay vì `-stream_loop`:
  ```bash
  ffmpeg -i bgm.mp3 -filter_complex \
    "[0]atrim=0:{trim_point},aloop=loop=-1:size=999999999[looped];\
     [looped]atrim=0:{narration_duration}[out]" \
    -map "[out]" output.mp3
  ```

---

## 2.3 preset_manager.py

```python
import json, os
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class Preset:
    name: str
    volume: float = 0.7
    fade_in: float = 1.0
    fade_out: float = 3.0
    normalize: bool = True
    smart_loop: bool = True
    output_format: str = "mp3"
    bitrate: str = "192k"

PRESETS_FILE = os.path.join(os.path.expanduser("~"), ".bgm_adjuster_presets.json")

def save_preset(preset: Preset):
    presets = load_all_presets()
    presets[preset.name] = asdict(preset)
    with open(PRESETS_FILE, "w") as f:
        json.dump(presets, f, indent=2)

def load_all_presets() -> dict:
    if not os.path.exists(PRESETS_FILE):
        return {}
    with open(PRESETS_FILE) as f:
        return json.load(f)

def load_preset(name: str) -> Optional[Preset]:
    presets = load_all_presets()
    if name in presets:
        return Preset(**presets[name])
    return None
```

---

## Todo

- [ ] Implement `get_duration()` + `get_ffmpeg_path()` / `get_ffprobe_path()`
- [ ] Implement `read_waveform_samples()`
- [ ] Implement `process_bgm()` với progress callback
- [ ] Test FFmpeg loop command với file thực
- [ ] Implement `find_best_loop_point()` trong smart_loop.py
- [ ] Implement `preset_manager.py`
- [ ] Unit test: duration detection, progress parsing

## Success Criteria
- `get_duration("test.mp3")` trả về đúng giây
- `process_bgm(...)` tạo ra file output đúng độ dài
- Progress callback được gọi với % tăng dần 0→100
- Smart loop không tạo tiếng pop khi nghe output
- Preset save/load round-trip không mất data
