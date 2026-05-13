#!/usr/bin/env python3
"""
step1_split.py — Split a PDF (or single image) into per-page PNG images at 300 DPI.

Usage:
    python3 step1_split.py <path_to_pdf_or_image> [output_dir]

For image inputs (PNG/JPG/JPEG/GIF/WEBP/BMP/TIFF), writes one normalized PNG
as `0001.png` so the rest of the vision pipeline can treat it as a 1-page doc.
"""

import os
import shutil
import sys

try:
    import fitz
except ImportError:
    os.system(f"{sys.executable} -m pip install PyMuPDF -q")
    import fitz

DPI = 300
ZOOM = DPI / 72
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


def _convert_image(src: str, out_dir: str) -> None:
    """Normalize a single image file to {out_dir}/0001.png."""
    dst = os.path.join(out_dir, "0001.png")
    ext = os.path.splitext(src)[1].lower()
    if ext == ".png":
        shutil.copyfile(src, dst)
        print(f"[step1_split] copied image → {dst}", file=sys.stderr)
        return
    try:
        from PIL import Image
        with Image.open(src) as im:
            if im.mode not in ("RGB", "RGBA", "L"):
                im = im.convert("RGB")
            im.save(dst, format="PNG")
        print(f"[step1_split] converted {ext} → {dst} via PIL", file=sys.stderr)
        return
    except ImportError:
        pass
    # Fallback: PyMuPDF can open many raster formats
    doc = fitz.open(src)
    page = doc.load_page(0)
    page.get_pixmap(matrix=fitz.Matrix(1, 1)).save(dst)
    doc.close()
    print(f"[step1_split] converted {ext} → {dst} via fitz", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print("Usage: step1_split.py <pdf_or_image> [output_dir]", file=sys.stderr)
        sys.exit(1)
    src_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) >= 3 else os.path.join(os.getcwd(), ".agents", "temp", "temp_pages")
    os.makedirs(out_dir, exist_ok=True)

    ext = os.path.splitext(src_path)[1].lower()
    if ext in IMAGE_EXTS:
        _convert_image(src_path, out_dir)
        return

    doc = fitz.open(src_path)
    mat = fitz.Matrix(ZOOM, ZOOM)
    page_count = len(doc)
    for i, page in enumerate(doc, start=0):
        page_no = i + 1
        page.get_pixmap(matrix=mat).save(os.path.join(out_dir, f"{page_no:04d}.png"))
        if i % 10 == 0 or i == page_count - 1:
            print(f"  Rendered {page_no}/{page_count} pages...")
    doc.close()
    print(f"[step1_split] rendered {page_count} pages → {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
