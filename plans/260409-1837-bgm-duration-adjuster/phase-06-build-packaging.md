# Phase 6: Build & Packaging

## Overview
- **Priority:** High (final deliverable)
- **Status:** pending
- **Depends on:** All phases complete
- **Goal:** PyInstaller → single portable `bgm-adjuster.exe` (~55MB)

## Files to Create
- `bgm-adjuster.spec` — PyInstaller spec
- `build.bat` — one-click build script

---

## PyInstaller Spec

```python
# bgm-adjuster.spec
import os
block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[
        ('assets/ffmpeg.exe', '.'),    # bundle vào root của .exe
        ('assets/ffprobe.exe', '.'),
    ],
    datas=[],
    hiddenimports=[
        'customtkinter',
        'scipy',
        'scipy.signal',
        'numpy',
        'sounddevice',
        'soundfile',
        'packaging',
        'darkdetect',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'PIL', 'cv2', 'PyQt5', 'PyQt6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='bgm-adjuster',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # compress với UPX để giảm size
    upx_exclude=[
        'ffmpeg.exe',  # không compress ffmpeg — có thể break
        'ffprobe.exe',
    ],
    runtime_tmpdir=None,
    console=False,     # --windowed: không mở console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,         # thêm icon.ico nếu có
)
```

---

## build.bat

```batch
@echo off
echo ============================================
echo   BGM Adjuster - Build Script
echo ============================================

REM Kiểm tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12+
    pause
    exit /b 1
)

REM Cài dependencies
echo [1/4] Installing dependencies...
pip install -r requirements.txt -q

REM Kiểm tra FFmpeg binaries
if not exist "assets\ffmpeg.exe" (
    echo [ERROR] assets\ffmpeg.exe not found!
    echo Download from: https://www.gyan.dev/ffmpeg/builds/
    pause
    exit /b 1
)
if not exist "assets\ffprobe.exe" (
    echo [ERROR] assets\ffprobe.exe not found!
    pause
    exit /b 1
)

REM Clean build artifacts
echo [2/4] Cleaning previous build...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

REM Build
echo [3/4] Building with PyInstaller...
pyinstaller bgm-adjuster.spec

REM Kiểm tra kết quả
if exist "dist\bgm-adjuster.exe" (
    echo [4/4] Build SUCCESS!
    echo Output: dist\bgm-adjuster.exe
    for %%A in ("dist\bgm-adjuster.exe") do echo Size: %%~zA bytes
) else (
    echo [ERROR] Build FAILED. Check output above.
    pause
    exit /b 1
)

echo.
echo Done! Double-click dist\bgm-adjuster.exe to run.
pause
```

---

## FFmpeg Binary Setup

```
# Cách lấy ffmpeg.exe + ffprobe.exe cho Windows:

1. Vào: https://www.gyan.dev/ffmpeg/builds/
2. Download: ffmpeg-release-essentials.zip (hoặc ffmpeg-git-essentials.7z)
3. Extract → vào thư mục bin/
4. Copy ffmpeg.exe và ffprobe.exe vào assets/

# Kích thước:
# ffmpeg.exe  ~45MB
# ffprobe.exe ~45MB (có thể dùng chung binary trong một số build)
#
# Để giảm size: dùng ffmpeg-essentials (không có codecs ít dùng)
# Target: ffmpeg.exe < 50MB
```

---

## UPX Compression (optional, giảm ~30%)

```batch
REM Download UPX từ https://github.com/upx/upx/releases
REM Đặt upx.exe vào PATH hoặc cùng thư mục

REM PyInstaller tự dùng UPX nếu có trong PATH
REM Kết quả: ~55MB → ~38MB
```

---

## Windows Defender False Positive

PyInstaller .exe đôi khi bị Defender flag là virus (heuristic). Giải pháp:

1. **Exclusion** (dành cho dev): Add `dist/` folder vào Windows Defender exclusions
2. **Code signing** (dành cho distribution): Mua cert ~$70/năm
3. **VirusTotal** test: Upload lên virustotal.com để kiểm tra → hầu hết scanners sạch
4. **Workaround**: Thêm `--key` cho PyInstaller encryption (giảm false positive)

---

## Test Checklist (sau khi build)

```
Môi trường test: Windows 10/11 sạch (không có Python cài sẵn)

[ ] Double-click bgm-adjuster.exe → mở ngay (không cần cài gì)
[ ] Tab "Đơn lẻ" hiển thị đúng
[ ] Browse narration file → waveform hiện
[ ] Browse BGM file → waveform + loop markers hiện
[ ] Kéo fade out slider → waveform cập nhật
[ ] Preview button → phát âm thanh
[ ] Xử lý 1 file → output đúng độ dài
[ ] Tab "Batch" → scan folder → list files
[ ] Batch process 3 files → tất cả hoàn thành
[ ] Preset save/load → hoạt động
[ ] Đóng app → mở lại → preset vẫn còn
```

---

## Expected Output Size

| Component | Size |
|-----------|------|
| Python runtime | ~8MB |
| customtkinter + tkinter | ~5MB |
| scipy + numpy | ~15MB |
| sounddevice + soundfile | ~3MB |
| ffmpeg.exe | ~45MB |
| ffprobe.exe | ~45MB |
| **Total (no UPX)** | **~121MB** |
| **Total (UPX + shared ffmpeg)** | **~60-70MB** |

**Tối ưu size:**
- Dùng `ffmpeg-essentials` build thay vì `ffmpeg-full`
- Một số build nhỏ hơn: `ffmpeg-n7.x-win64-gpl.zip` ~30MB
- Exclude unused scipy submodules trong spec

---

## Todo

- [ ] Download FFmpeg essentials Windows binaries vào `assets/`
- [ ] Viết `bgm-adjuster.spec` với hiddenimports đúng
- [ ] Viết `build.bat`
- [ ] Chạy `build.bat` → kiểm tra `dist/bgm-adjuster.exe`
- [ ] Test trên Windows sạch (hoặc VM)
- [ ] Test Defender false positive
- [ ] Đo size output và optimize nếu cần

## Success Criteria
- `build.bat` chạy không lỗi trong < 3 phút
- `bgm-adjuster.exe` chạy được mà không cần Python cài sẵn
- Tất cả test checklist pass
- Size .exe < 100MB
