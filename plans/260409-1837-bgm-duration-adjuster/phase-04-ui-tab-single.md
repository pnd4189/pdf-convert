# Phase 4: Single File Tab UI

## Overview
- **Priority:** High
- **Status:** pending
- **Depends on:** Phase 2 (audio engine), Phase 3 (waveform widget)
- **Goal:** Tab xử lý 1 file — browse, waveform, controls, preview, process

## File to Create
- `ui/tab_single.py`

---

## Layout

```
┌─────────────────────────────────────────────────────────┐
│  Audio Truyện:  [/path/to/truyen.mp3]        [Browse]  │
│  Thời lượng: 45:23                                      │
│  [  waveform narration (height=70)                   ]  │
│                                                         │
│  Nhạc Nền:      [/path/to/nhac.mp3]          [Browse]  │
│  Thời lượng: 3:45 → sẽ loop ~12 lần                    │
│  [  waveform BGM với loop markers + fade region      ]  │
│  [▶ Nghe thử 30s cuối]                                  │
│                                                         │
│  ─────────────── Cài đặt ────────────────────────────  │
│  Volume nhạc:   [━━━━━━━━━━━━━━] 70%                   │
│  Fade in:       [━━━━] 1.0s                             │
│  Fade out:      [━━━━━━] 3.0s                           │
│  [☑] Normalize -18 LUFS   [☑] Smart loop               │
│                                                         │
│  Output:        [/path/output.mp3]           [Browse]  │
│  Format: [MP3▾]  Quality: [192kbps▾]                   │
│                                                         │
│  [Lưu Preset]  [Tải Preset]       [▶ Xử Lý]           │
│                                                         │
│  [████████████████░░░░░░░░] 65% — Loop 8/12 ...        │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation

```python
# ui/tab_single.py
import threading, os
import customtkinter as ctk
from tkinter import filedialog, messagebox
import sounddevice as sd
import soundfile as sf
import numpy as np

from ui.waveform_canvas import WaveformCanvas
from core.audio_processor import (
    get_duration, read_waveform_samples, process_bgm, get_ffmpeg_path
)
from core.smart_loop import get_smart_loop_trim_point
from core.preset_manager import Preset, save_preset, load_all_presets, load_preset


def fmt_duration(seconds: float) -> str:
    """Format seconds → MM:SS or HH:MM:SS."""
    s = int(seconds)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class TabSingle(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._narration_path = ""
        self._bgm_path = ""
        self._narration_duration = 0.0
        self._bgm_duration = 0.0
        self._preview_thread = None
        self._preview_playing = False
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        # ── Narration section ──────────────────────────────
        narr_frame = ctk.CTkFrame(self, fg_color="transparent")
        narr_frame.pack(fill="x", **pad)
        ctk.CTkLabel(narr_frame, text="Audio Truyện:", width=110, anchor="w").pack(side="left")
        self.narr_entry = ctk.CTkEntry(narr_frame, placeholder_text="Chọn file audio truyện...")
        self.narr_entry.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(narr_frame, text="Browse", width=70,
                      command=self._browse_narration).pack(side="left")

        self.narr_duration_label = ctk.CTkLabel(self, text="Thời lượng: —", anchor="w",
                                                  text_color="gray60", font=("Arial", 11))
        self.narr_duration_label.pack(fill="x", padx=12)

        self.narr_waveform = WaveformCanvas(self, height=70)
        self.narr_waveform.pack(fill="x", padx=12, pady=(0, 8))

        # ── BGM section ────────────────────────────────────
        bgm_frame = ctk.CTkFrame(self, fg_color="transparent")
        bgm_frame.pack(fill="x", **pad)
        ctk.CTkLabel(bgm_frame, text="Nhạc Nền:", width=110, anchor="w").pack(side="left")
        self.bgm_entry = ctk.CTkEntry(bgm_frame, placeholder_text="Chọn file nhạc nền...")
        self.bgm_entry.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(bgm_frame, text="Browse", width=70,
                      command=self._browse_bgm).pack(side="left")

        self.bgm_duration_label = ctk.CTkLabel(self, text="Thời lượng: —", anchor="w",
                                                 text_color="gray60", font=("Arial", 11))
        self.bgm_duration_label.pack(fill="x", padx=12)

        self.bgm_waveform = WaveformCanvas(self, height=70)
        self.bgm_waveform.pack(fill="x", padx=12, pady=(0, 4))

        self.preview_btn = ctk.CTkButton(self, text="▶ Nghe thử 30s cuối", width=160,
                                          fg_color="#2d5a27", hover_color="#3d7a37",
                                          command=self._toggle_preview, state="disabled")
        self.preview_btn.pack(anchor="w", padx=12, pady=(0, 8))

        # ── Settings ───────────────────────────────────────
        ctk.CTkLabel(self, text="─── Cài đặt ───────────────────────────────────",
                     text_color="gray50", font=("Arial", 11)).pack(fill="x", padx=12, pady=(4, 0))

        self._build_slider("Volume nhạc:", "volume_slider", 0.0, 1.0, 0.7,
                           lambda v: f"{int(v*100)}%")
        self._build_slider("Fade in (giây):", "fade_in_slider", 0.0, 10.0, 1.0,
                           lambda v: f"{v:.1f}s")
        self._build_slider("Fade out (giây):", "fade_out_slider", 0.0, 10.0, 3.0,
                           lambda v: f"{v:.1f}s",
                           command=self._on_fade_out_changed)

        checks = ctk.CTkFrame(self, fg_color="transparent")
        checks.pack(fill="x", padx=12, pady=4)
        self.normalize_var = ctk.BooleanVar(value=True)
        self.smart_loop_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(checks, text="Normalize -18 LUFS",
                        variable=self.normalize_var).pack(side="left", padx=(0, 20))
        ctk.CTkCheckBox(checks, text="Smart loop (no pop)",
                        variable=self.smart_loop_var).pack(side="left")

        # ── Output ─────────────────────────────────────────
        out_frame = ctk.CTkFrame(self, fg_color="transparent")
        out_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(out_frame, text="Output:", width=110, anchor="w").pack(side="left")
        self.out_entry = ctk.CTkEntry(out_frame, placeholder_text="Chọn đường dẫn output...")
        self.out_entry.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(out_frame, text="Browse", width=70,
                      command=self._browse_output).pack(side="left")

        fmt_frame = ctk.CTkFrame(self, fg_color="transparent")
        fmt_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(fmt_frame, text="Format:", width=60, anchor="w").pack(side="left")
        self.format_var = ctk.StringVar(value="mp3")
        self.format_menu = ctk.CTkOptionMenu(fmt_frame, values=["mp3", "wav"],
                                              variable=self.format_var, width=80)
        self.format_menu.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(fmt_frame, text="Quality:", anchor="w").pack(side="left")
        self.quality_var = ctk.StringVar(value="192k")
        self.quality_menu = ctk.CTkOptionMenu(fmt_frame, values=["128k", "192k", "320k"],
                                               variable=self.quality_var, width=90)
        self.quality_menu.pack(side="left")

        # ── Preset + Process ───────────────────────────────
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(action_frame, text="Lưu Preset", width=110,
                      fg_color="gray30", command=self._save_preset).pack(side="left", padx=(0, 8))
        ctk.CTkButton(action_frame, text="Tải Preset", width=110,
                      fg_color="gray30", command=self._load_preset).pack(side="left", padx=(0, 8))
        self.process_btn = ctk.CTkButton(action_frame, text="▶  Xử Lý", width=130,
                                          command=self._start_process)
        self.process_btn.pack(side="right")

        # ── Progress ───────────────────────────────────────
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.pack(fill="x", padx=12, pady=(4, 2))
        self.progress_bar.set(0)
        self.status_label = ctk.CTkLabel(self, text="Sẵn sàng.", anchor="w",
                                          text_color="gray60", font=("Arial", 11))
        self.status_label.pack(fill="x", padx=12)

    def _build_slider(self, label, attr, from_, to, default, fmt_fn, command=None):
        """Helper: label + slider + value label row."""
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(row, text=label, width=130, anchor="w").pack(side="left")
        val_label = ctk.CTkLabel(row, text=fmt_fn(default), width=55, anchor="w")

        def on_change(v):
            val_label.configure(text=fmt_fn(float(v)))
            if command:
                command(float(v))

        slider = ctk.CTkSlider(row, from_=from_, to=to, command=on_change)
        slider.set(default)
        slider.pack(side="left", fill="x", expand=True, padx=4)
        val_label.pack(side="left")
        setattr(self, attr, slider)

    # ── File browsing ─────────────────────────────────────

    def _browse_narration(self):
        path = filedialog.askopenfilename(
            filetypes=[("Audio files", "*.mp3 *.wav *.flac *.ogg *.aac"), ("All", "*.*")]
        )
        if not path:
            return
        self._narration_path = path
        self.narr_entry.delete(0, "end")
        self.narr_entry.insert(0, path)
        threading.Thread(target=self._load_narration, daemon=True).start()

    def _load_narration(self):
        dur = get_duration(self._narration_path)
        samples = read_waveform_samples(self._narration_path, max_points=800)
        self._narration_duration = dur
        self.after(0, lambda: self._update_narration_ui(dur, samples))

    def _update_narration_ui(self, dur, samples):
        self.narr_duration_label.configure(text=f"Thời lượng: {fmt_duration(dur)}")
        self.narr_waveform.set_samples(samples)
        self._update_bgm_info_labels()
        self._auto_set_output_path()

    def _browse_bgm(self):
        path = filedialog.askopenfilename(
            filetypes=[("Audio files", "*.mp3 *.wav *.flac *.ogg *.aac"), ("All", "*.*")]
        )
        if not path:
            return
        self._bgm_path = path
        self.bgm_entry.delete(0, "end")
        self.bgm_entry.insert(0, path)
        threading.Thread(target=self._load_bgm, daemon=True).start()

    def _load_bgm(self):
        dur = get_duration(self._bgm_path)
        samples = read_waveform_samples(self._bgm_path, max_points=800)
        self._bgm_duration = dur
        self.after(0, lambda: self._update_bgm_ui(dur, samples))

    def _update_bgm_ui(self, dur, samples):
        loops = int(self._narration_duration / dur) + 1 if self._narration_duration else 0
        loop_txt = f" → sẽ loop ~{loops} lần" if loops > 1 else " → sẽ cắt bớt"
        self.bgm_duration_label.configure(text=f"Thời lượng: {fmt_duration(dur)}{loop_txt}")
        self.bgm_waveform.set_samples(samples)
        self._update_waveform_markers()
        self.preview_btn.configure(state="normal")

    def _update_waveform_markers(self):
        if not self._bgm_duration or not self._narration_duration:
            return
        markers = [self._bgm_duration * i
                   for i in range(1, int(self._narration_duration / self._bgm_duration) + 1)]
        self.bgm_waveform.set_loop_markers(markers, self._narration_duration)
        fade = self.fade_out_slider.get()
        self.bgm_waveform.set_fade_region(
            self._narration_duration - fade, fade, self._narration_duration
        )

    def _on_fade_out_changed(self, val):
        self._update_waveform_markers()

    def _update_bgm_info_labels(self):
        if self._bgm_duration:
            self._update_bgm_ui(self._bgm_duration, None)

    def _auto_set_output_path(self):
        """Auto-suggest output path based on narration filename."""
        if not self._narration_path:
            return
        base = os.path.splitext(self._narration_path)[0]
        ext = self.format_var.get()
        suggested = f"{base}_bgm.{ext}"
        self.out_entry.delete(0, "end")
        self.out_entry.insert(0, suggested)

    def _browse_output(self):
        ext = self.format_var.get()
        path = filedialog.asksaveasfilename(
            defaultextension=f".{ext}",
            filetypes=[(ext.upper(), f"*.{ext}"), ("All", "*.*")]
        )
        if path:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, path)

    # ── Preview ───────────────────────────────────────────

    def _toggle_preview(self):
        if self._preview_playing:
            sd.stop()
            self._preview_playing = False
            self.preview_btn.configure(text="▶ Nghe thử 30s cuối")
        else:
            self._preview_thread = threading.Thread(
                target=self._play_preview, daemon=True
            )
            self._preview_thread.start()

    def _play_preview(self):
        """Play last 30s of BGM with current volume applied."""
        try:
            data, sr = sf.read(self._bgm_path, always_2d=True)
            start = max(0, len(data) - sr * 30)
            segment = data[start:] * self.volume_slider.get()
            self._preview_playing = True
            self.after(0, lambda: self.preview_btn.configure(text="■ Dừng"))
            sd.play(segment.astype(np.float32), sr)
            sd.wait()
        finally:
            self._preview_playing = False
            self.after(0, lambda: self.preview_btn.configure(text="▶ Nghe thử 30s cuối"))

    # ── Process ───────────────────────────────────────────

    def _start_process(self):
        if not self._narration_path or not self._bgm_path:
            messagebox.showwarning("Thiếu file", "Vui lòng chọn cả audio truyện và nhạc nền.")
            return
        out = self.out_entry.get().strip()
        if not out:
            messagebox.showwarning("Thiếu output", "Vui lòng chọn đường dẫn output.")
            return
        self.process_btn.configure(state="disabled", text="Đang xử lý...")
        self.progress_bar.set(0)
        threading.Thread(target=self._run_process, args=(out,), daemon=True).start()

    def _run_process(self, out_path):
        try:
            process_bgm(
                bgm_path=self._bgm_path,
                narration_duration=self._narration_duration,
                output_path=out_path,
                volume=self.volume_slider.get(),
                fade_in=self.fade_in_slider.get(),
                fade_out=self.fade_out_slider.get(),
                normalize=self.normalize_var.get(),
                output_format=self.format_var.get(),
                bitrate=self.quality_var.get(),
                progress_callback=self._on_progress,
            )
            self.after(0, self._on_done)
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _on_progress(self, percent: float):
        self.after(0, lambda: [
            self.progress_bar.set(percent / 100),
            self.status_label.configure(text=f"Đang xử lý... {percent:.0f}%")
        ])

    def _on_done(self):
        self.progress_bar.set(1.0)
        self.status_label.configure(text="Hoàn thành!", text_color="#4AFF6B")
        self.process_btn.configure(state="normal", text="▶  Xử Lý")
        messagebox.showinfo("Hoàn thành", "Xử lý xong! File đã được lưu.")

    def _on_error(self, msg):
        self.status_label.configure(text=f"Lỗi: {msg}", text_color="#FF4444")
        self.process_btn.configure(state="normal", text="▶  Xử Lý")
        messagebox.showerror("Lỗi", msg)

    # ── Preset ────────────────────────────────────────────

    def _save_preset(self):
        dialog = ctk.CTkInputDialog(text="Tên preset:", title="Lưu Preset")
        name = dialog.get_input()
        if name:
            save_preset(Preset(
                name=name,
                volume=self.volume_slider.get(),
                fade_in=self.fade_in_slider.get(),
                fade_out=self.fade_out_slider.get(),
                normalize=self.normalize_var.get(),
                smart_loop=self.smart_loop_var.get(),
                output_format=self.format_var.get(),
                bitrate=self.quality_var.get(),
            ))

    def _load_preset(self):
        presets = load_all_presets()
        if not presets:
            messagebox.showinfo("Không có preset", "Chưa có preset nào được lưu.")
            return
        # Simple selection dialog using CTkToplevel
        win = ctk.CTkToplevel(self)
        win.title("Chọn Preset")
        win.geometry("300x200")
        for name in presets:
            ctk.CTkButton(win, text=name,
                          command=lambda n=name: self._apply_preset(n, win)).pack(pady=4)

    def _apply_preset(self, name, window):
        p = load_preset(name)
        if p:
            self.volume_slider.set(p.volume)
            self.fade_in_slider.set(p.fade_in)
            self.fade_out_slider.set(p.fade_out)
            self.normalize_var.set(p.normalize)
            self.smart_loop_var.set(p.smart_loop)
            self.format_var.set(p.output_format)
            self.quality_var.set(p.bitrate)
        window.destroy()
```

---

## Todo

- [ ] Implement `TabSingle` class hoàn chỉnh
- [ ] Test browse narration → waveform hiển thị
- [ ] Test browse BGM → loop markers xuất hiện
- [ ] Test preview 30s cuối play/stop
- [ ] Test fade out slider → waveform fade region cập nhật
- [ ] Test process button → progress bar chạy
- [ ] Test preset save/load round-trip
- [ ] Test auto-suggest output path

## Success Criteria
- Chọn 2 file → waveform + info hiển thị ngay
- Kéo slider fade out → vùng fade trên waveform cập nhật real-time
- Preview play/stop hoạt động
- Process → progress bar chạy → file output đúng độ dài
- Preset save → load → values khôi phục đúng
