# Phase 5: Batch Tab UI

## Overview
- **Priority:** Medium
- **Status:** pending
- **Depends on:** Phase 2 (audio engine), Phase 4 (patterns từ tab single)
- **Goal:** Tab batch — áp cùng 1 nhạc nền cho cả folder file truyện

## File to Create
- `ui/tab_batch.py`

---

## Layout

```
┌─────────────────────────────────────────────────────────┐
│  Nhạc Nền:   [/path/nhac.mp3]                [Browse]  │
│  Thời lượng: 3:45                                       │
│                                                         │
│  ─── Cài đặt ──────────────────────────────────────── │
│  Volume:  [━━━━━━━━━━] 70%   Fade out: [━━━━] 3.0s     │
│  [☑] Normalize -18 LUFS     [☑] Smart loop              │
│  Format: [MP3▾]  Quality: [192kbps▾]                   │
│                                                         │
│  ─── Files Truyện ─────────────────────────────────── │
│  Folder:  [/stories/season-2/]               [Browse]  │
│  [Chọn tất cả]  [Bỏ chọn tất cả]   24 files tìm thấy  │
│  ┌────────────────────────────────────────────────┐    │
│  │[✓] ep-01.mp3    45:23     Chờ xử lý           │    │
│  │[✓] ep-02.mp3    32:10     Chờ xử lý           │    │
│  │[✓] ep-03.mp3    51:05     Chờ xử lý           │    │
│  │[✗] ep-04.mp3    28:44     Bỏ qua              │    │
│  │...                                             │    │
│  └────────────────────────────────────────────────┘    │
│                                                         │
│  Output folder: [/stories/season-2/output/]  [Browse]  │
│  Suffix output: [_bgm] (vd: ep-01_bgm.mp3)            │
│                                                         │
│  [▶ Xử Lý Tất Cả]                                      │
│  [████████░░░░░░░░] File 3/24 — ep-03.mp3 (65%)        │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation

```python
# ui/tab_batch.py
import os, threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

from core.audio_processor import get_duration, process_bgm
from core.preset_manager import Preset


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a"}


def fmt_duration(seconds: float) -> str:
    s = int(seconds)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class FileRow(ctk.CTkFrame):
    """Single file row with checkbox, filename, duration, status."""

    STATUS_COLORS = {
        "Chờ": "gray60",
        "Đang xử lý": "#4A9EFF",
        "Hoàn thành": "#4AFF6B",
        "Lỗi": "#FF4444",
        "Bỏ qua": "gray40",
    }

    def __init__(self, parent, filepath: str, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.filepath = filepath
        self.duration = 0.0

        self.var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self, variable=self.var, text="",
                        width=24).pack(side="left", padx=4)

        name = os.path.basename(filepath)
        ctk.CTkLabel(self, text=name, anchor="w",
                     width=220).pack(side="left", padx=4)

        self.dur_label = ctk.CTkLabel(self, text="...", width=60,
                                       anchor="w", text_color="gray60",
                                       font=("Arial", 11))
        self.dur_label.pack(side="left", padx=4)

        self.status_label = ctk.CTkLabel(self, text="Chờ xử lý", width=100,
                                          anchor="w", text_color="gray60",
                                          font=("Arial", 11))
        self.status_label.pack(side="left", padx=4)

    def set_duration(self, seconds: float):
        self.duration = seconds
        self.dur_label.configure(text=fmt_duration(seconds))

    def set_status(self, status: str):
        color = self.STATUS_COLORS.get(status, "gray60")
        label = {"Chờ": "Chờ xử lý", "Bỏ qua": "Bỏ qua"}.get(status, status)
        self.status_label.configure(text=label, text_color=color)

    @property
    def selected(self) -> bool:
        return self.var.get()


class TabBatch(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._bgm_path = ""
        self._bgm_duration = 0.0
        self._file_rows: list[FileRow] = []
        self._processing = False
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        # ── BGM ───────────────────────────────────────────
        bgm_frame = ctk.CTkFrame(self, fg_color="transparent")
        bgm_frame.pack(fill="x", **pad)
        ctk.CTkLabel(bgm_frame, text="Nhạc Nền:", width=90, anchor="w").pack(side="left")
        self.bgm_entry = ctk.CTkEntry(bgm_frame, placeholder_text="Chọn file nhạc nền chung...")
        self.bgm_entry.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(bgm_frame, text="Browse", width=70,
                      command=self._browse_bgm).pack(side="left")

        self.bgm_info = ctk.CTkLabel(self, text="", anchor="w",
                                      text_color="gray60", font=("Arial", 11))
        self.bgm_info.pack(fill="x", padx=12)

        # ── Settings (compact) ────────────────────────────
        ctk.CTkLabel(self, text="─── Cài đặt ───────────────────────────",
                     text_color="gray50", font=("Arial", 11)).pack(fill="x", padx=12, pady=(8, 0))

        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(row1, text="Volume:", width=60, anchor="w").pack(side="left")
        self.vol_label = ctk.CTkLabel(row1, text="70%", width=40, anchor="w")
        self.volume_slider = ctk.CTkSlider(row1, from_=0, to=1,
                                            command=lambda v: self.vol_label.configure(
                                                text=f"{int(float(v)*100)}%"))
        self.volume_slider.set(0.7)
        self.volume_slider.pack(side="left", fill="x", expand=True, padx=4)
        self.vol_label.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(row1, text="Fade out:", anchor="w").pack(side="left")
        self.fade_label = ctk.CTkLabel(row1, text="3.0s", width=40, anchor="w")
        self.fade_slider = ctk.CTkSlider(row1, from_=0, to=10, width=100,
                                          command=lambda v: self.fade_label.configure(
                                              text=f"{float(v):.1f}s"))
        self.fade_slider.set(3.0)
        self.fade_slider.pack(side="left", padx=4)
        self.fade_label.pack(side="left")

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=2)
        self.normalize_var = ctk.BooleanVar(value=True)
        self.smart_loop_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(row2, text="Normalize -18 LUFS",
                        variable=self.normalize_var).pack(side="left", padx=(0, 20))
        ctk.CTkCheckBox(row2, text="Smart loop",
                        variable=self.smart_loop_var).pack(side="left", padx=(0, 20))
        ctk.CTkLabel(row2, text="Format:", anchor="w").pack(side="left")
        self.format_var = ctk.StringVar(value="mp3")
        ctk.CTkOptionMenu(row2, values=["mp3", "wav"],
                          variable=self.format_var, width=80).pack(side="left", padx=4)
        ctk.CTkLabel(row2, text="Quality:", anchor="w").pack(side="left")
        self.quality_var = ctk.StringVar(value="192k")
        ctk.CTkOptionMenu(row2, values=["128k", "192k", "320k"],
                          variable=self.quality_var, width=90).pack(side="left", padx=4)

        # ── File list ─────────────────────────────────────
        ctk.CTkLabel(self, text="─── Files Truyện ─────────────────────────",
                     text_color="gray50", font=("Arial", 11)).pack(fill="x", padx=12, pady=(8, 0))

        folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        folder_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(folder_frame, text="Folder:", width=60, anchor="w").pack(side="left")
        self.folder_entry = ctk.CTkEntry(folder_frame,
                                          placeholder_text="Chọn folder chứa file audio truyện...")
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(folder_frame, text="Browse", width=70,
                      command=self._browse_folder).pack(side="left")

        sel_frame = ctk.CTkFrame(self, fg_color="transparent")
        sel_frame.pack(fill="x", padx=12, pady=2)
        ctk.CTkButton(sel_frame, text="Chọn tất cả", width=110, fg_color="gray30",
                      command=self._select_all).pack(side="left", padx=(0, 8))
        ctk.CTkButton(sel_frame, text="Bỏ chọn tất cả", width=120, fg_color="gray30",
                      command=self._deselect_all).pack(side="left")
        self.file_count_label = ctk.CTkLabel(sel_frame, text="", text_color="gray60",
                                              font=("Arial", 11))
        self.file_count_label.pack(side="left", padx=12)

        # Scrollable file list
        self.file_list_frame = ctk.CTkScrollableFrame(self, height=180)
        self.file_list_frame.pack(fill="x", padx=12, pady=4)

        # ── Output ────────────────────────────────────────
        out_frame = ctk.CTkFrame(self, fg_color="transparent")
        out_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(out_frame, text="Output folder:", width=100, anchor="w").pack(side="left")
        self.out_entry = ctk.CTkEntry(out_frame,
                                       placeholder_text="Chọn folder output...")
        self.out_entry.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(out_frame, text="Browse", width=70,
                      command=self._browse_output).pack(side="left")

        suffix_frame = ctk.CTkFrame(self, fg_color="transparent")
        suffix_frame.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(suffix_frame, text="Suffix output:", width=100, anchor="w").pack(side="left")
        self.suffix_entry = ctk.CTkEntry(suffix_frame, width=100)
        self.suffix_entry.insert(0, "_bgm")
        self.suffix_entry.pack(side="left")
        ctk.CTkLabel(suffix_frame, text=" (vd: ep-01_bgm.mp3)",
                     text_color="gray60", font=("Arial", 11)).pack(side="left", padx=8)

        # ── Process button + progress ──────────────────────
        self.process_btn = ctk.CTkButton(self, text="▶  Xử Lý Tất Cả",
                                          command=self._start_batch)
        self.process_btn.pack(pady=8)

        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 2))
        self.progress_bar.set(0)
        self.status_label = ctk.CTkLabel(self, text="Sẵn sàng.", anchor="w",
                                          text_color="gray60", font=("Arial", 11))
        self.status_label.pack(fill="x", padx=12)

    # ── Browsing ──────────────────────────────────────────

    def _browse_bgm(self):
        path = filedialog.askopenfilename(
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.aac"), ("All", "*.*")]
        )
        if not path:
            return
        self._bgm_path = path
        self.bgm_entry.delete(0, "end")
        self.bgm_entry.insert(0, path)
        threading.Thread(target=self._load_bgm_info, daemon=True).start()

    def _load_bgm_info(self):
        dur = get_duration(self._bgm_path)
        self._bgm_duration = dur
        self.after(0, lambda: self.bgm_info.configure(
            text=f"Thời lượng: {fmt_duration(dur)}"
        ))

    def _browse_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.folder_entry.delete(0, "end")
        self.folder_entry.insert(0, folder)
        # Auto-suggest output folder
        if not self.out_entry.get():
            self.out_entry.insert(0, os.path.join(folder, "output"))
        self._scan_folder(folder)

    def _scan_folder(self, folder: str):
        """Find audio files and populate file list."""
        # Clear existing rows
        for row in self._file_rows:
            row.destroy()
        self._file_rows.clear()

        files = sorted([
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS
        ])

        for filepath in files:
            row = FileRow(self.file_list_frame, filepath)
            row.pack(fill="x", pady=1)
            self._file_rows.append(row)

        self.file_count_label.configure(text=f"{len(files)} files tìm thấy")

        # Load durations in background
        threading.Thread(target=self._load_durations, daemon=True).start()

    def _load_durations(self):
        for row in self._file_rows:
            try:
                dur = get_duration(row.filepath)
                self.after(0, lambda r=row, d=dur: r.set_duration(d))
            except Exception:
                pass

    def _browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, folder)

    def _select_all(self):
        for row in self._file_rows:
            row.var.set(True)

    def _deselect_all(self):
        for row in self._file_rows:
            row.var.set(False)

    # ── Batch processing ──────────────────────────────────

    def _start_batch(self):
        if not self._bgm_path:
            messagebox.showwarning("Thiếu", "Vui lòng chọn nhạc nền.")
            return
        selected = [r for r in self._file_rows if r.selected]
        if not selected:
            messagebox.showwarning("Không có file", "Chọn ít nhất 1 file để xử lý.")
            return
        out_folder = self.out_entry.get().strip()
        if not out_folder:
            messagebox.showwarning("Thiếu", "Vui lòng chọn folder output.")
            return
        os.makedirs(out_folder, exist_ok=True)
        self.process_btn.configure(state="disabled")
        self._processing = True
        threading.Thread(
            target=self._run_batch, args=(selected, out_folder), daemon=True
        ).start()

    def _run_batch(self, rows: list[FileRow], out_folder: str):
        total = len(rows)
        suffix = self.suffix_entry.get() or "_bgm"
        fmt = self.format_var.get()

        for i, row in enumerate(rows):
            if not self._processing:
                break
            self.after(0, lambda r=row: r.set_status("Đang xử lý"))
            self.after(0, lambda i=i, name=os.path.basename(row.filepath): (
                self.status_label.configure(
                    text=f"File {i+1}/{total} — {name}",
                    text_color="gray60"
                )
            ))

            try:
                base = os.path.splitext(os.path.basename(row.filepath))[0]
                out_path = os.path.join(out_folder, f"{base}{suffix}.{fmt}")
                narr_dur = row.duration or get_duration(row.filepath)

                def file_progress(pct, file_idx=i):
                    overall = (file_idx + pct / 100) / total
                    self.after(0, lambda: self.progress_bar.set(overall))

                process_bgm(
                    bgm_path=self._bgm_path,
                    narration_duration=narr_dur,
                    output_path=out_path,
                    volume=self.volume_slider.get(),
                    fade_out=self.fade_slider.get(),
                    normalize=self.normalize_var.get(),
                    output_format=fmt,
                    bitrate=self.quality_var.get(),
                    progress_callback=file_progress,
                )
                self.after(0, lambda r=row: r.set_status("Hoàn thành"))
            except Exception as e:
                self.after(0, lambda r=row, err=str(e): [
                    r.set_status("Lỗi"),
                    print(f"Error processing {r.filepath}: {err}")
                ])

        self.after(0, self._on_batch_done)

    def _on_batch_done(self):
        self._processing = False
        self.progress_bar.set(1.0)
        done = sum(1 for r in self._file_rows if r.status_label.cget("text") == "Hoàn thành")
        errors = sum(1 for r in self._file_rows if r.status_label.cget("text") == "Lỗi")
        self.status_label.configure(
            text=f"Hoàn thành {done} file. Lỗi: {errors}.",
            text_color="#4AFF6B" if errors == 0 else "#FFAA44"
        )
        self.process_btn.configure(state="normal")
        messagebox.showinfo("Batch Done", f"Xong {done}/{done+errors} files.")
```

---

## Todo

- [ ] Implement `FileRow` widget (checkbox + name + duration + status)
- [ ] Implement `TabBatch` với scrollable file list
- [ ] Test scan folder → hiển thị danh sách file đúng
- [ ] Test select/deselect all
- [ ] Test duration loading async
- [ ] Test batch processing sequential với progress overall
- [ ] Test output file naming với suffix

## Success Criteria
- Scan folder 50 files → hiển thị đủ trong 2s
- Batch process 5 files → progress bar tổng chạy đúng
- Lỗi 1 file → các file còn lại vẫn tiếp tục
- Output files đúng tên: `{original}{suffix}.{format}`
