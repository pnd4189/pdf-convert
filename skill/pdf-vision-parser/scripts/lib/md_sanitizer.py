"""
md_sanitizer.py — Best-effort cleanup of Gemini-emitted ADE Markdown.

Two responsibilities:
  1. normalize_box_coords(md)
     Rewrite box='[...]' attributes so coordinates that arrived in scientific
     notation (e.g. 5.4851e-01) become plain decimals (0.5485). QA regex and
     downstream parsers expect plain floats in [0.00, 1.00].

  2. force_accept_stuck_page(md, page_no, reasons)
     For pages the auto-repair loop cannot fix, produce a "best-effort" version
     that still merges cleanly: insert a QA_WARNING marker, clamp bad coords,
     and ensure at least one valid anchor exists so step3 grounding/chunking
     produces something for the page instead of dropping it.

Pure functions — no I/O. Tested via step4_quality_report and the driver.
"""

from __future__ import annotations

import re
from typing import Iterable

# Match the box='[...]' attribute on an <a id='X-Y'> anchor.
_BOX_ATTR_RE = re.compile(
    r"""(box\s*=\s*['"])\s*\[([^\]]*)\]\s*(['"])""",
    re.IGNORECASE,
)

# Lenient float that includes scientific notation (e.g. 5.48e-01, 1E+0).
_LENIENT_FLOAT_RE = re.compile(
    r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
)

# Anchor tag (kept loose so we tolerate stray whitespace and quoting styles).
_ANCHOR_RE = re.compile(
    r"""<a\s+id\s*=\s*['"](\d+-\d+)['"]\s*(?:box\s*=\s*['"]([^'"]+)['"])?\s*>\s*</a>""",
    re.IGNORECASE,
)

VISION_SOURCE_MARKER = "<!-- VISION_SOURCE:"
QA_WARNING_PREFIX = "<!-- QA_WARNING:"


def _format_coord(value: float) -> str:
    """Clamp to [0, 1] and format as a 4-digit decimal."""
    if value < 0:
        value = 0.0
    elif value > 1:
        value = 1.0
    return f"{value:.4f}"


def _rewrite_box(match: re.Match) -> str:
    prefix, body, suffix = match.group(1), match.group(2), match.group(3)
    nums = _LENIENT_FLOAT_RE.findall(body)
    if len(nums) != 4:
        return match.group(0)
    try:
        coords = [float(n) for n in nums]
    except ValueError:
        return match.group(0)
    formatted = ", ".join(_format_coord(c) for c in coords)
    return f"{prefix}[{formatted}]{suffix}"


def normalize_box_coords(md: str) -> str:
    """Rewrite every box='[...]' attribute so all 4 coords are plain decimals
    in [0, 1]. No-op for boxes already in plain form."""
    if not md or "box" not in md.lower():
        return md
    return _BOX_ATTR_RE.sub(_rewrite_box, md)


def has_any_anchor(md: str) -> bool:
    return bool(_ANCHOR_RE.search(md or ""))


def has_vision_source(md: str) -> bool:
    return VISION_SOURCE_MARKER in (md or "")


def force_accept_stuck_page(
    md: str,
    page_no: int,
    reasons: Iterable[str],
    png_path: str | None = None,
) -> str:
    """Return a best-effort version of a stuck page so step3 can merge it.

    - Always normalize box coords (handles scientific notation).
    - If no VISION_SOURCE marker, prepend one (placeholder) so QA hard-check
      against missing provenance does not trip merge.
    - If no anchor exists, inject a minimal anchor for the visible content.
    - Prepend a QA_WARNING comment listing reasons so downstream report and
      humans can see exactly why this page is partial.
    """
    cleaned = normalize_box_coords(md or "")
    lines: list[str] = []

    reasons_str = " | ".join(r.strip() for r in reasons if r and r.strip()) or "stuck after retries"
    lines.append(f"{QA_WARNING_PREFIX} page {page_no}: {reasons_str} -->")

    if not has_vision_source(cleaned):
        src = png_path or f"temp_png/{page_no:04d}.png"
        lines.append(f"<!-- VISION_SOURCE: {src} -->")

    if cleaned.strip():
        lines.append(cleaned.rstrip())
    else:
        lines.append(f"<a id='{page_no}-1' box='[0.0000, 0.0000, 1.0000, 1.0000]'></a>")
        lines.append(f"<!-- page {page_no} could not be extracted by vision model -->")

    if not has_any_anchor("\n".join(lines)):
        # Inject placeholder anchor at top of body so step3 still produces a chunk.
        lines.insert(2 if has_vision_source(cleaned) else 1,
                     f"<a id='{page_no}-1' box='[0.0000, 0.0000, 1.0000, 1.0000]'></a>")

    return "\n".join(lines) + "\n"


def extract_qa_warnings(md: str) -> list[str]:
    """Return the QA_WARNING comments on a page (used by the quality report)."""
    if not md or QA_WARNING_PREFIX not in md:
        return []
    return [
        m.group(1).strip()
        for m in re.finditer(
            r"<!--\s*QA_WARNING:\s*(.*?)\s*-->", md, re.IGNORECASE | re.DOTALL
        )
    ]
