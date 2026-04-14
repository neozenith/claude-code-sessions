#!/usr/bin/env python3
"""
Render a Mermaid Gantt chart for one or more e2e test runs.

Each request in `{slug}.network.json` has `start_offset_ms` (relative to
test start) and `duration_ms`, which together define a timeline bar.

Usage:
    # Print Gantt for a single slug (both engines side by side if paired)
    uv run scripts/render_gantt.py E01_SQLITE-S00_DASHBOARD-T04_30D-P00_ALL

    # Print Gantt for the paired engines run (strips E00_/E01_ prefix)
    uv run scripts/render_gantt.py S00_DASHBOARD-T04_30D-P00_ALL

    # Emit as a standalone .md file under docs/timelines/
    uv run scripts/render_gantt.py S00_DASHBOARD-T04_30D-P00_ALL --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCREENSHOT_DIR = Path("frontend/e2e-screenshots")
OUTPUT_DIR = Path("docs/timelines")

# URL templates for friendly labels (same as compare_engines.py)
URL_TEMPLATES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"/api/timeline/events/[^/?]+"), "/api/timeline/events/:project"),
    (re.compile(r"/api/sessions/[^/?]+/[^/?]+"), "/api/sessions/:project/:session"),
    (re.compile(r"/api/sessions/[^/?]+"), "/api/sessions/:project"),
]


def shorten_url(url: str) -> str:
    """Drop host + query string, collapse IDs to template form."""
    path = url.split("://", 1)[-1]
    path = "/" + path.split("/", 1)[-1] if "/" in path else path
    path = path.split("?", 1)[0]
    for pattern, template in URL_TEMPLATES:
        if pattern.search(path):
            path = pattern.sub(template, path)
            break
    return path


def find_network_files(base_slug: str) -> list[Path]:
    """Resolve the slug to one or more E*-{slug}.network.json files."""
    # If the user passed a full slug with engine prefix, return just that file.
    direct = SCREENSHOT_DIR / f"{base_slug}.network.json"
    if direct.exists():
        return [direct]
    # Otherwise glob for all engine variants.
    return sorted(SCREENSHOT_DIR.glob(f"E*-{base_slug}.network.json"))


def render_gantt(network_file: Path) -> str:
    """Emit a Mermaid gantt block for one network.json file."""
    data = json.loads(network_file.read_text(encoding="utf-8"))
    requests = data.get("all_requests", [])

    # Only show API calls + the initial document load — static assets add noise
    interesting = [
        r for r in requests
        if r.get("is_api") or r.get("resource_type") == "document"
    ]
    if not interesting:
        interesting = requests[:20]

    lines = [
        "```mermaid",
        "gantt",
        f"    title {network_file.stem}",
        "    dateFormat x",  # "x" = unix ms; Mermaid draws relative-time axis
        "    axisFormat %S.%L",
    ]

    # Group by resource_type for visual separation
    by_kind: dict[str, list[dict[str, object]]] = {}
    for r in interesting:
        kind = "API" if r.get("is_api") else (r.get("resource_type") or "other").upper()
        by_kind.setdefault(kind, []).append(r)

    for kind, items in by_kind.items():
        lines.append(f"    section {kind}")
        for r in items:
            label = shorten_url(str(r["url"]))
            # Truncate long labels so the chart doesn't overflow
            if len(label) > 55:
                label = label[:52] + "..."
            # Cast via float to satisfy Pyright — values are always numeric in practice
            start = int(float(r["start_offset_ms"]))  # type: ignore[arg-type]
            duration = max(1, int(float(r["duration_ms"])))  # type: ignore[arg-type]
            lines.append(f"    {label} :{start}, {duration}ms")

    lines.append("```")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("slug", help="Slug to render (with or without E-prefix)")
    parser.add_argument("--write", action="store_true", help="Write a .md file to docs/timelines/")
    args = parser.parse_args()

    files = find_network_files(args.slug)
    if not files:
        print(f"No network.json files found for '{args.slug}'", file=sys.stderr)
        sys.exit(1)

    output_parts: list[str] = [f"# Network Timeline: {args.slug}\n"]

    for nf in files:
        output_parts.append(f"## {nf.stem}\n")
        data = json.loads(nf.read_text(encoding="utf-8"))
        output_parts.append(
            f"- Wall-clock duration: {data.get('wall_clock_duration_ms', 0)} ms\n"
            f"- Total API time: {data.get('api_duration_ms', 0)} ms across "
            f"{data.get('api_requests', 0)} requests\n"
        )
        output_parts.append(render_gantt(nf) + "\n")

    content = "\n".join(output_parts)

    if args.write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{args.slug}.md"
        out_path.write_text(content, encoding="utf-8")
        print(f"Wrote {out_path}", file=sys.stderr)
    print(content)


if __name__ == "__main__":
    main()
