# Phase 1: Project Setup & Structure

## Overview
- **Priority:** High (blocker cho tất cả phases)
- **Status:** pending
- **Goal:** Tạo skeleton project, cài deps, download FFmpeg binaries

## Project Structure

```
bgm-adjuster/
├── main.py                    # Entry point: khởi tạo App, CTk window
├── ui/
│   ├── __init__.py
│   ├── tab-single.py          # Tab xử lý đơn lẻ
│   ├── tab-batch.py           # Tab batch processing
│   └── waveform-canvas.py     # Widget vẽ waveform
├── core/
│   ├── __init__.py
│   ├── audio-processor.py     # FFmpeg subprocess: loop/trim/fade/normalize
│   ├── smart-loop.py          # Zero-crossing detection
│   └── preset-manager.py      # JSON preset save/load
├── assets/
│   ├── ffmpeg.exe             # FFmpeg Windows binary (bundled)
│   └── ffprobe.exe            # FFprobe Windows binary (bundled)
├── requirements.txt
├── bgm-adjuster.spec          # PyInstaller spec file
└── build.bat                  # One-click build script
```

## Requirements

```txt
# requirements.txt
customtkinter==5.2.2
scipy==1.13.0
numpy==1.26.4
sounddevice==0.4.7
soundfile==0.12.1
pyinstaller==6.6.0
```

## Implementation Steps

### 1. Tạo project skeleton
```bash
mkdir bgm-adjuster
cd bgm-adjuster
mkdir ui core assets
touch main.py ui/__init__.py core/__init__.py
touch ui/tab-single.py ui/tab-batch.py ui/waveform-canvas.py
touch core/audio-processor.py core/smart-loop.py core/preset-manager.py
```

### 2. Download FFmpeg binaries
- Download từ https://www.gyan.dev/ffmpeg/builds/ → `ffmpeg-release-essentials.zip`
- Extract `ffmpeg.exe` và `ffprobe.exe` vào `assets/`
- Version: FFmpeg 7.x Windows 64-bit

### 3. Cài Python deps
```bash
pip install -r requirements.txt
```

### 4. Tạo main.py skeleton
```python
# main.py — entry point
import customtkinter as ctk
from ui.tab_single import TabSingle  # note: Python import dùng underscore
from ui.tab_batch import TabBatch

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("BGM Duration Adjuster")
        self.geometry("800x680")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tabview.add("Đơn lẻ")
        self.tabview.add("Batch")
        
        TabSingle(self.tabview.tab("Đơn lẻ")).pack(fill="both", expand=True)
        TabBatch(self.tabview.tab("Batch")).pack(fill="both", expand=True)

if __name__ == "__main__":
    App().mainloop()
```

### 5. Lưu ý đặt tên file vs Python import
- File: `tab-single.py` (kebab-case cho filesystem/LLM)
- Import: `from ui import tab_single` → dùng underscore trong Python
- Giải pháp: trong `ui/__init__.py` re-export với alias

```python
# ui/__init__.py
from ui import tab_single as tab_single
from ui import tab_batch as tab_batch  
from ui import waveform_canvas as waveform_canvas
```

**QUAN TRỌNG:** PyInstaller cần tên module hợp lệ — đổi file thành underscore trong `assets/spec` hoặc dùng `importlib.import_module("ui.tab_single")`.

**Quyết định đơn giản hơn:** Dùng underscore cho Python files trong project này vì PyInstaller cần module names hợp lệ:
- `tab_single.py`, `tab_batch.py`, `waveform_canvas.py`
- `audio_processor.py`, `smart_loop.py`, `preset_manager.py`

## FFmpeg Binary Path Resolution

Khi chạy từ PyInstaller .exe, cần resolve đường dẫn tới bundled binaries:

```python
# core/audio_processor.py
import sys, os

def get_ffmpeg_path():
    """Resolve ffmpeg.exe path — works both dev and PyInstaller."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        base = sys._MEIPASS
    else:
        # Running in development
        base = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(base, 'assets', 'ffmpeg.exe')

def get_ffprobe_path():
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(base, 'assets', 'ffprobe.exe')
```

## Todo

- [ ] Tạo folder structure
- [ ] Download FFmpeg 7.x Windows binaries
- [ ] Tạo requirements.txt
- [ ] Tạo main.py skeleton
- [ ] Verify imports chạy không lỗi: `python main.py`
- [ ] Quyết định naming: dùng `underscore` cho .py files (PyInstaller compat)

## Success Criteria
- `python main.py` mở được window CustomTkinter với 2 tabs
- FFmpeg binaries có mặt trong `assets/`
- Không có import errors
