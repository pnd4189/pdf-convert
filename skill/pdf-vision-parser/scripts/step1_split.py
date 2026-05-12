#!/usr/bin/env python3
"""
step1_split.py — Split a PDF into per-page PNG images at 300 DPI.

Usage:
    python3 step1_split.py <path_to_pdf> [output_dir]
"""

import os
import sys

try:
    import fitz
except ImportError:
    os.system(f"{sys.executable} -m pip install PyMuPDF -q")
    import fitz

DPI = 300
ZOOM = DPI / 72


def main():
    if len(sys.argv) < 2:
        print("Usage: step1_split.py <pdf_path> [output_dir]", file=sys.stderr)
        sys.exit(1)
    pdf_path = sys.argv[1]
    # Accept output dir from argv[2] (passed by auto_convert.sh)
    out_dir = sys.argv[2] if len(sys.argv) >= 3 else os.path.join(os.getcwd(), ".agents", "temp", "temp_pages")
    os.makedirs(out_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(ZOOM, ZOOM)
    page_count = len(doc)
    for i, page in enumerate(doc, start=0):
        # 1-indexed, zero-padded to match step2 expectation: {page_no:04d}.png
        page_no = i + 1
        page.get_pixmap(matrix=mat).save(os.path.join(out_dir, f"{page_no:04d}.png"))
        if i % 10 == 0 or i == page_count - 1:
            print(f"  Rendered {page_no}/{page_count} pages...")
    doc.close()
    print(f"[step1_split] rendered {page_count} pages → {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
