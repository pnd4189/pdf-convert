#!/usr/bin/env python3
"""
generate_quality_report.py — Post-merge audit for a /pdf-convert workspace.

Reads:
  - <workspace>/QUOTA_PROMPT.json (if present) → cascade events
  - <workspace>/temp_md/page_*.md mtimes      → per-page completion times
  - <workspace>/native_manifest.json (optional) → totals, source, output_json

Writes:
  - <workspace>/QUALITY_REPORT.md → human-readable summary

Page→model attribution is best-effort: we partition page mtimes by cascade
event timestamps and attribute each partition to the model active during
that window. If no cascade events are present, all pages map to the
detected model recorded in `_PRO_LADDER[0]` (or 'unknown').

Usage:
    python3 generate_quality_report.py --workspace <dir> [--model <id>]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _collect_page_mtimes(temp_md: Path) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    if not temp_md.exists():
        return out
    for f in temp_md.glob("page_*.md"):
        try:
            n = int(f.stem.removeprefix("page_"))
        except ValueError:
            continue
        try:
            out.append((n, f.stat().st_mtime))
        except OSError:
            continue
    return sorted(out)


def _attribute_pages(
    pages: list[tuple[int, float]],
    cascade_events: list[dict],
    default_model: str,
) -> dict[str, int]:
    """Bucket page count by model based on mtime vs cascade timestamps."""
    if not pages:
        return {}
    if not cascade_events:
        return {default_model or "unknown": len(pages)}

    boundaries = sorted(
        (e for e in cascade_events if e.get("ts") and e.get("to")),
        key=lambda e: e["ts"],
    )
    counts: dict[str, int] = {}
    for _, mtime in pages:
        active = default_model or "unknown"
        for ev in boundaries:
            if mtime >= ev["ts"]:
                active = ev["to"]
        counts[active] = counts.get(active, 0) + 1
    return counts


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "0s"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate post-run quality report.")
    parser.add_argument("--workspace", required=True, help="Path to /tmp/pdf_convert_<name>/")
    parser.add_argument("--model", default="", help="Default model id if no cascade events")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        print(f"ERROR: workspace not found: {workspace}", file=sys.stderr)
        return 1

    quota = _load_json(workspace / "QUOTA_PROMPT.json")
    manifest = _load_json(workspace / "native_manifest.json")
    pages = _collect_page_mtimes(workspace / "temp_md")

    # Quota event log may be a single dict (single cascade) or a list.
    events: list[dict] = []
    if isinstance(quota, dict) and quota:
        # Synthesize a single-event timeline using mtime of QUOTA_PROMPT.json.
        try:
            ts = (workspace / "QUOTA_PROMPT.json").stat().st_mtime
        except OSError:
            ts = 0
        if quota.get("auto_cascaded_to"):
            events.append({
                "ts": ts,
                "from": quota.get("exhausted_model", "?"),
                "to": quota["auto_cascaded_to"],
            })
    elif isinstance(quota, list):
        for ev in quota:
            if ev.get("auto_cascaded_to"):
                events.append({
                    "ts": ev.get("ts") or 0,
                    "from": ev.get("exhausted_model", "?"),
                    "to": ev["auto_cascaded_to"],
                })

    default_model = args.model or (events[0]["from"] if events else "")
    attribution = _attribute_pages(pages, events, default_model)

    if pages:
        wall_start = datetime.fromtimestamp(min(p[1] for p in pages))
        wall_end = datetime.fromtimestamp(max(p[1] for p in pages))
        duration = _format_duration(max(p[1] for p in pages) - min(p[1] for p in pages))
    else:
        wall_start = wall_end = None
        duration = "n/a"

    total = sum(attribution.values()) or len(pages)
    lines: list[str] = []
    lines.append(f"# Quality Report — {workspace.name}")
    lines.append("")
    lines.append(f"- Workspace: `{workspace}`")
    if manifest.get("output_json"):
        lines.append(f"- Output JSON: `{manifest['output_json']}`")
    lines.append(f"- Total pages on disk: {len(pages)}")
    lines.append("")

    lines.append("## Pages by Model (best-effort by mtime)")
    if attribution:
        for m, n in sorted(attribution.items(), key=lambda kv: -kv[1]):
            pct = (100 * n / total) if total else 0
            lines.append(f"- `{m or 'unknown'}`: {n} ({pct:.1f}%)")
    else:
        lines.append("- (no page output found)")
    lines.append("")

    lines.append("## Cascade Events")
    if events:
        for ev in events:
            ts_str = (
                datetime.fromtimestamp(ev["ts"]).isoformat(timespec="seconds")
                if ev.get("ts") else "?"
            )
            lines.append(f"- {ts_str}: {ev.get('from','?')} → {ev['to']}")
    else:
        lines.append("- None — single model used end-to-end.")
    lines.append("")

    lines.append("## Wall-Clock")
    if wall_start:
        lines.append(f"- First page: {wall_start.isoformat(timespec='seconds')}")
        lines.append(f"- Last page : {wall_end.isoformat(timespec='seconds')}")
        lines.append(f"- Duration  : {duration}")
    else:
        lines.append("- (no pages to measure)")
    lines.append("")

    lines.append("## Caveats")
    lines.append("- Page→model attribution uses file mtimes; pages regenerated during retry may shift bucket.")
    lines.append("- Single QUOTA_PROMPT.json captures the latest cascade only; serial cascades are an approximation.")

    out_path = workspace / "QUALITY_REPORT.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
