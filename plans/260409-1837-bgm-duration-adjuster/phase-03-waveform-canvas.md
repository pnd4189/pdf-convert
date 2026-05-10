# Phase 3: Waveform Canvas Widget

## Overview
- **Priority:** Medium
- **Status:** pending
- **Depends on:** Phase 2 (`read_waveform_samples`)
- **Goal:** Widget tkinter Canvas vẽ waveform, loop markers, fade regions

## File to Create
- `ui/waveform_canvas.py`

---

## Design

```
┌─────────────────────────────────────────────────────────┐
│▓▓▒▒▓▓▓▒▒▒▓▓▓▓▒▒▒│▒▓▓▒▒▒│▒▓▓▒▒▒│▒▓▓▒░░░░░░░░░░░░░░░░░│
└─────────────────────────────────────────────────────────┘
                   ↑ loop  ↑ loop            ↑ fade start
```

- Màu waveform: `#4A9EFF` (blue)
- Loop markers: vertical dashed line `#FF6B35` (orange)
- Fade region: overlay `#FF000033` (red transparent)
- Background: `#1E1E2E` (dark)

---

## Implementation

```python
# ui/waveform_canvas.py
import tkinter as tk
import customtkinter as ctk
import numpy as np
from typing import List

class WaveformCanvas(ctk.CTkFrame):
    """
    Draws audio waveform with loop markers and fade region overlay.
    
    Usage:
        wf = WaveformCanvas(parent, height=80)
        wf.set_samples(np.array([...]))       # raw waveform data [-1, 1]
        wf.set_loop_markers([45.0, 90.0, ...])  # seconds
        wf.set_fade_region(start_sec, duration_sec, total_sec)
    """
    
    WAVE_COLOR = "#4A9EFF"
    LOOP_COLOR = "#FF6B35"
    FADE_COLOR = "#FF4444"
    BG_COLOR = "#1a1a2e"
    
    def __init__(self, parent, height=80, **kwargs):
        super().__init__(parent, height=height, **kwargs)
        self.configure(fg_color=self.BG_COLOR)
        
        self._canvas = tk.Canvas(
            self, bg=self.BG_COLOR,
            highlightthickness=0, height=height
        )
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", self._on_resize)
        
        self._samples: np.ndarray = np.array([])
        self._loop_markers: List[float] = []   # seconds
        self._fade_start: float = 0.0
        self._fade_dur: float = 0.0
        self._total_dur: float = 0.0

    def set_samples(self, samples: np.ndarray):
        self._samples = samples
        self._redraw()

    def set_loop_markers(self, markers_sec: List[float], total_dur: float):
        """markers_sec: list of loop point times in seconds."""
        self._loop_markers = markers_sec
        self._total_dur = total_dur
        self._redraw()

    def set_fade_region(self, start_sec: float, fade_dur: float, total_dur: float):
        self._fade_start = start_sec
        self._fade_dur = fade_dur
        self._total_dur = total_dur
        self._redraw()

    def clear(self):
        self._samples = np.array([])
        self._loop_markers = []
        self._canvas.delete("all")

    def _on_resize(self, event):
        self._redraw()

    def _redraw(self):
        self._canvas.delete("all")
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 2 or h < 2 or len(self._samples) == 0:
            return
        
        self._draw_waveform(w, h)
        self._draw_fade_region(w, h)
        self._draw_loop_markers(w, h)

    def _draw_waveform(self, w: int, h: int):
        """Draw waveform as filled polygon."""
        samples = self._samples
        mid = h / 2
        
        # Resample to canvas width
        indices = np.linspace(0, len(samples) - 1, w).astype(int)
        resampled = samples[indices]
        
        # Build polygon points: top half + bottom half mirrored
        points = []
        for i, amp in enumerate(resampled):
            y = mid - amp * mid * 0.9  # top edge
            points.extend([i, y])
        for i, amp in enumerate(reversed(resampled)):
            y = mid + amp * mid * 0.9  # bottom edge (mirrored)
            points.extend([w - 1 - i, y])
        
        if len(points) >= 4:
            self._canvas.create_polygon(
                points, fill=self.WAVE_COLOR,
                outline="", smooth=False
            )

    def _draw_loop_markers(self, w: int, h: int):
        """Draw vertical dashed lines at loop points."""
        if not self._total_dur or not self._loop_markers:
            return
        for marker_sec in self._loop_markers:
            x = int(marker_sec / self._total_dur * w)
            # Dashed line via segments
            dash_h = 6
            for y in range(0, h, dash_h * 2):
                self._canvas.create_line(
                    x, y, x, min(y + dash_h, h),
                    fill=self.LOOP_COLOR, width=1
                )

    def _draw_fade_region(self, w: int, h: int):
        """Draw semi-transparent red overlay for fade-out region."""
        if not self._total_dur or not self._fade_dur:
            return
        x_start = int(self._fade_start / self._total_dur * w)
        # Stipple pattern simulates transparency in tkinter
        self._canvas.create_rectangle(
            x_start, 0, w, h,
            fill=self.FADE_COLOR, stipple="gray25", outline=""
        )
        # Fade label
        self._canvas.create_text(
            x_start + 4, 4,
            text=f"fade {self._fade_dur:.0f}s",
            fill="#FF8888", anchor="nw",
            font=("Arial", 8)
        )
```

---

## Tích hợp với Tab Single

```python
# Trong tab_single.py — sau khi user chọn file:
from core.audio_processor import read_waveform_samples, get_duration
from ui.waveform_canvas import WaveformCanvas

def _on_bgm_selected(self, path):
    samples = read_waveform_samples(path, max_points=800)
    duration = get_duration(path)
    
    # Tính loop markers (mỗi bgm_duration giây là 1 loop point)
    bgm_dur = get_duration(path)
    narr_dur = self._narration_duration
    markers = [bgm_dur * i for i in range(1, int(narr_dur / bgm_dur) + 1)]
    
    self.bgm_waveform.set_samples(samples)
    self.bgm_waveform.set_loop_markers(markers, narr_dur)
    self.bgm_waveform.set_fade_region(
        narr_dur - self.fade_out_slider.get(),
        self.fade_out_slider.get(),
        narr_dur
    )
```

---

## Performance Notes
- `read_waveform_samples` chạy trong thread riêng (Phase 4 dùng `threading.Thread`)
- Waveform redraw chỉ gọi khi có thay đổi thực sự (resize hoặc data mới)
- `max_points=800` đủ cho canvas ~800px wide, không cần nhiều hơn

---

## Todo

- [ ] Implement `WaveformCanvas` class với `set_samples`, `set_loop_markers`, `set_fade_region`
- [ ] Test vẽ waveform với data thực từ MP3
- [ ] Test loop markers hiển thị đúng vị trí
- [ ] Test fade region overlay
- [ ] Test resize behavior

## Success Criteria
- Waveform hiển thị đúng hình dạng âm thanh
- Loop markers xuất hiện đúng vị trí theo thời gian
- Fade region overlay mờ đúng vùng cuối
- Resize window → waveform tự scale
