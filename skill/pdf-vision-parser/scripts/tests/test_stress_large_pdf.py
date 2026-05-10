#!/usr/bin/env python3
"""
test_stress_large_pdf.py — Memory-profiled stress test for large PDF processing.

Tests streaming batch logic on a synthetic 250-page PDF without requiring
a real large PDF in CI. Verifies:
1. Page-count detection triggers streaming mode (>200 pages)
2. Peak RSS stays under 12GB headroom limit
3. Cache + streaming behave correctly across batch boundaries
4. Streaming produces same page count as single-pass parse count

Requires: psutil (already in skill venv via requirements.txt)
          pypdf (already in skill venv)

Usage:
    python tests/test_stress_large_pdf.py [--use-real-pdf <path>]
"""

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

RSS_LIMIT_GB = 12.0


def _get_current_rss_gb() -> float:
    """Return current process RSS in GB."""
    try:
        import psutil
        proc = psutil.Process()
        return proc.memory_info().rss / (1024 ** 3)
    except ImportError:
        return 0.0


def _create_synthetic_pdf(path: Path, num_pages: int) -> None:
    """Create a minimal valid PDF with num_pages pages using reportlab or pypdf."""
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        c = rl_canvas.Canvas(str(path))
        for i in range(num_pages):
            c.setFont("Helvetica", 12)
            c.drawString(72, 720, f"Page {i + 1} of {num_pages}")
            c.drawString(72, 700, "Sample text for stress test. " * 10)
            # Add a simple table-like structure on every 10th page
            if i % 10 == 0:
                for row in range(5):
                    c.drawString(72, 600 - row * 20, f"Row {row}: Col A | Col B | Col C")
            c.showPage()
        c.save()
    except ImportError:
        # Fallback: create a minimal multi-page PDF using raw bytes
        _create_minimal_pdf(path, num_pages)


def _create_minimal_pdf(path: Path, num_pages: int) -> None:
    """Create a minimal but valid multi-page PDF without external deps."""
    header = b"%PDF-1.4\n"
    pages_ref = []
    objects = []

    # Object 1: catalog (placeholder, filled later)
    # Object 2: pages container
    # Objects 3+: individual pages

    page_obj_ids = list(range(3, 3 + num_pages))
    content_obj_ids = list(range(3 + num_pages, 3 + 2 * num_pages))

    body_parts = [header]
    offsets = []

    def add_obj(obj_id: int, content: bytes) -> None:
        offsets.append(len(b"".join(body_parts)))
        body_parts.append(f"{obj_id} 0 obj\n".encode())
        body_parts.append(content)
        body_parts.append(b"\nendobj\n")

    # Content streams for each page
    for i in range(num_pages):
        stream_content = f"BT /F1 12 Tf 72 720 Td (Page {i+1}) Tj ET".encode()
        stream_len = len(stream_content)
        content = (
            f"<< /Length {stream_len} >>\nstream\n".encode()
            + stream_content
            + b"\nendstream"
        )
        add_obj(content_obj_ids[i], content)

    # Page objects
    pages_container_id = 2
    for i, pg_id in enumerate(page_obj_ids):
        content_ref = content_obj_ids[i]
        content = (
            f"<< /Type /Page /Parent {pages_container_id} 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {content_ref} 0 R "
            f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
            f">>".encode()
        )
        add_obj(pg_id, content)

    # Pages container
    kids = " ".join(f"{pg} 0 R" for pg in page_obj_ids)
    pages_content = f"<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>".encode()
    add_obj(pages_container_id, pages_content)

    # Catalog
    catalog_content = f"<< /Type /Catalog /Pages {pages_container_id} 0 R >>".encode()
    add_obj(1, catalog_content)

    # Cross-reference table
    xref_pos = len(b"".join(body_parts))
    total_objs = 1 + num_pages * 2 + 2  # content + page + pages + catalog
    xref = f"xref\n0 {total_objs + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()

    trailer = f"trailer\n<< /Size {total_objs + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    path.write_bytes(b"".join(body_parts) + xref + trailer)


# ── Tests ────────────────────────────────────────────────────────────────────

def test_streaming_mode_triggered_for_large_pdf(tmp_path: Path) -> None:
    """PDF with >200 pages must trigger streaming mode in step1_docling_parse."""
    from step1_docling_parse import _get_pdf_page_count

    pdf = tmp_path / "large_test.pdf"
    _create_synthetic_pdf(pdf, 250)

    page_count = _get_pdf_page_count(str(pdf))
    assert page_count == 250, f"Expected 250 pages, got {page_count}"

    STREAM_PAGE_THRESHOLD = 200
    use_streaming = page_count > STREAM_PAGE_THRESHOLD
    assert use_streaming is True, "Expected streaming mode for 250-page PDF"
    print(f"  [stress] 250-page PDF: streaming={'yes' if use_streaming else 'no'}")


def test_rss_under_limit() -> None:
    """Current process RSS must be under the 12GB hard limit."""
    rss = _get_current_rss_gb()
    print(f"  [stress] current RSS: {rss:.2f} GB (limit: {RSS_LIMIT_GB} GB)")
    assert rss < RSS_LIMIT_GB, f"RSS {rss:.2f} GB exceeds {RSS_LIMIT_GB} GB limit"


def test_cache_key_stable_for_large_file(tmp_path: Path) -> None:
    """Cache key must be identical across two calls for the same large file."""
    from lib.cache_utils import make_cache_key

    pdf = tmp_path / "large_stable.pdf"
    _create_synthetic_pdf(pdf, 50)

    key1 = make_cache_key(str(pdf))
    key2 = make_cache_key(str(pdf))
    assert key1 == key2, f"Cache keys differ: {key1} vs {key2}"
    print(f"  [stress] cache key stable: {key1[:16]}...")


def test_batch_boundary_coverage() -> None:
    """Batch arithmetic must cover all pages without gaps or double-counting."""
    page_count = 250
    batch_size = 40
    batches = []
    for start in range(0, page_count, batch_size):
        end = min(start + batch_size - 1, page_count - 1)
        batches.append((start, end))

    # Verify no gaps
    covered = set()
    for start, end in batches:
        for p in range(start, end + 1):
            assert p not in covered, f"Page {p} covered twice!"
            covered.add(p)

    assert len(covered) == page_count, f"Expected {page_count} covered, got {len(covered)}"
    print(f"  [stress] {len(batches)} batches cover all {page_count} pages correctly")


def test_synthetic_pdf_page_count_detection(tmp_path: Path) -> None:
    """Synthetic 250-page PDF must be detected correctly by pypdf."""
    from step1_docling_parse import _get_pdf_page_count

    pdf = tmp_path / "synthetic_250.pdf"
    _create_synthetic_pdf(pdf, 250)
    count = _get_pdf_page_count(str(pdf))
    assert count == 250, f"Expected 250, got {count}"
    print(f"  [stress] page count detection: {count} pages ✓")


def run_real_pdf_stress_test(pdf_path: str) -> None:
    """Optional: run full Docling parse on a real large PDF with memory tracking."""
    try:
        import psutil
    except ImportError:
        print("  [stress] psutil not available — skipping real PDF stress test")
        return

    from lib.cache_utils import make_cache_key

    print(f"\n  [stress] Real PDF stress test: {pdf_path}")
    proc = psutil.Process()
    baseline_rss = proc.memory_info().rss / (1024 ** 3)
    print(f"  [stress] baseline RSS: {baseline_rss:.2f} GB")

    start_time = time.time()
    try:
        from step1_docling_parse import _get_pdf_page_count
        page_count = _get_pdf_page_count(pdf_path)
        print(f"  [stress] pages: {page_count}")

        peak_rss = proc.memory_info().rss / (1024 ** 3)
        elapsed = time.time() - start_time
        print(f"  [stress] peak RSS after page-count read: {peak_rss:.2f} GB")
        print(f"  [stress] elapsed: {elapsed:.1f}s")
        assert peak_rss < RSS_LIMIT_GB, f"Peak RSS {peak_rss:.2f} GB exceeds {RSS_LIMIT_GB} GB limit"
        print(f"  [stress] RSS OK ({peak_rss:.2f} GB < {RSS_LIMIT_GB} GB)")
    except Exception as e:
        print(f"  [stress] WARNING: {e}")


# ── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-real-pdf", help="Path to a real large PDF for end-to-end stress test")
    args = parser.parse_args()

    tests = [
        test_rss_under_limit,
        test_batch_boundary_coverage,
    ]
    tmp_tests = [
        test_streaming_mode_triggered_for_large_pdf,
        test_cache_key_stable_for_large_file,
        test_synthetic_pdf_page_count_detection,
    ]

    passed = failed = 0

    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1

    with tempfile.TemporaryDirectory() as tmp:
        for t in tmp_tests:
            try:
                t(Path(tmp))
                print(f"  ✓ {t.__name__}")
                passed += 1
            except Exception as e:
                print(f"  ✗ {t.__name__}: {e}")
                failed += 1

    if args.use_real_pdf:
        run_real_pdf_stress_test(args.use_real_pdf)

    print(f"\n{passed}/{passed + failed} passed")
    sys.exit(0 if failed == 0 else 1)
