#!/usr/bin/env python3
"""
step1_split.py — Split a PDF into per-page PNG images at 300 DPI.
Landing.AI ADE Standard: Zero-based page indexing.

Usage:
    python3 step1_split.py <path_to_pdf>
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
        sys.exit(1)
    pdf_path = sys.argv[1]
    out_dir = os.path.join(os.getcwd(), ".agents", "temp", "temp_pages")
    os.makedirs(out_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(ZOOM, ZOOM)
    for i, page in enumerate(doc, start=0):
        page.get_pixmap(matrix=mat).save(os.path.join(out_dir, f"page_{i}.png"))
        if i % 10 == 0 or i == len(doc) - 1:
            print(f"  Rendered {i}/{len(doc)-1} pages...")
    doc.close()


if __name__ == "__main__":
    main()
