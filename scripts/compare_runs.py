#!/usr/bin/env python3
"""
Compare two e2e run snapshots and enforce regression gates.

Expects two directories each containing `*.network.json` files produced by
the e2e suite. Typically these are baseline (before change) and after (after
change) snapshots.

Outputs a markdown report to stdout and optionally a file, and exits non-zero
if any endpoint p95 regressed by more than the threshold.

Usage:
    # Compare with default 10% regression threshold
    uv run scripts/compare_runs.py docs/perf/baseline docs/perf/after

    # Custom threshold + write report
    uv run scripts/compare_runs.py \\
        docs/perf/baseline docs/perf/after \\
        --threshold 15 \\
        --output docs/perf/report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ENGINE_PREFIX_RE = re.compile(r"^E\d+_([A-Z]+)-")

URL_TEMPLATES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"/api/timeline/events/[^/?]+"), "/api/timeline/events/:project"),
    (re.compile(r"/api/sessions/[^/?]+/[^/?]+"), "/api/sessions/:project/:session"),
    (re.compile(r"/api/sessions/[^/?]+"), "/api/sessions/:project"),
]


@dataclass
class Stats:
    """Percentile statistics for one endpoint under one engine."""

    count: int
    p50: int
    p95: int
    p99: int
    max_ms: int


def normalize_endpoint(url: str) -> str:
    """Strip host + query, collapse ID segments to template form."""
    path = url.split("://", 1)[-1]
    path = "/" + path.split("/", 1)[-1] if "/" in path else path
    path = path.split("?", 1)[0]
    for pattern, template in URL_TEMPLATES:
        if pattern.search(path):
            return pattern.sub(template, path)
    return path


def pct(values: list[int], p: float) -> int:
    """Quick percentile — sorted-index method, not interpolated."""
    if not values:
        return 0
    s = sorted(values)
    idx = min(len(s) - 1, int(len(s) * p))
    return s[idx]


def collect(directory: Path) -> dict[str, dict[str, list[int]]]:
    """Return {engine: {endpoint: [duration_ms, ...]}} for API requests only."""
    per_engine: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))

    if not directory.exists():
        return per_engine

    for path in sorted(directory.glob("*.network.json")):
        match = ENGINE_PREFIX_RE.match(path.name)
        if not match:
            continue
        engine = match.group(1).lower()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for req in data.get("all_requests", []):
            if not req.get("is_api"):
                continue
            endpoint = normalize_endpoint(req["url"])
            per_engine[engine][endpoint].append(int(req["duration_ms"]))

    return per_engine


def stats_for(values: list[int]) -> Stats:
    return Stats(
        count=len(values),
        p50=pct(values, 0.50),
        p95=pct(values, 0.95),
        p99=pct(values, 0.99),
        max_ms=max(values) if values else 0,
    )


def format_delta(before: int, after: int) -> str:
    if before == 0:
        return "n/a" if after == 0 else f"new ({after}ms)"
    delta_pct = (after - before) * 100.0 / before
    sign = "+" if delta_pct > 0 else ""
    return f"{sign}{delta_pct:.1f}%"


def is_regression(before: int, after: int, threshold_pct: float) -> bool:
    """True if `after` is worse than `before` by more than threshold_pct."""
    if before == 0:
        return False  # can't regress from nothing
    delta_pct = (after - before) * 100.0 / before
    return delta_pct > threshold_pct


def compare(
    baseline: dict[str, dict[str, list[int]]],
    after: dict[str, dict[str, list[int]]],
    threshold_pct: float,
) -> tuple[list[str], int]:
    """Emit markdown rows and count regressions across all engines+endpoints."""
    lines: list[str] = []
    regressions = 0

    engines = sorted(set(baseline.keys()) | set(after.keys()))

    for engine in engines:
        lines.append(f"\n### Engine: `{engine}`\n")
        lines.append("| Endpoint | count (before/after) | p50 Δ | p95 Δ | p99 Δ | regression? |")
        lines.append("|----------|----------------------|-------|-------|-------|-------------|")

        endpoints = sorted(
            set(baseline.get(engine, {}).keys()) | set(after.get(engine, {}).keys())
        )
        for endpoint in endpoints:
            b = stats_for(baseline.get(engine, {}).get(endpoint, []))
            a = stats_for(after.get(engine, {}).get(endpoint, []))

            p50_delta = format_delta(b.p50, a.p50)
            p95_delta = format_delta(b.p95, a.p95)
            p99_delta = format_delta(b.p99, a.p99)

            # Gate on p95 only — p99 is noisy at small counts
            regressed = is_regression(b.p95, a.p95, threshold_pct)
            if regressed:
                regressions += 1

            marker = "🚨 yes" if regressed else "ok"
            lines.append(
                f"| `{endpoint}` "
                f"| {b.count}/{a.count} "
                f"| {b.p50}→{a.p50} ({p50_delta}) "
                f"| {b.p95}→{a.p95} ({p95_delta}) "
                f"| {b.p99}→{a.p99} ({p99_delta}) "
                f"| {marker} |"
            )

    return lines, regressions


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("baseline_dir", type=Path, help="Directory with baseline *.network.json")
    parser.add_argument("after_dir", type=Path, help="Directory with after-change *.network.json")
    parser.add_argument(
        "--threshold", type=float, default=10.0,
        help="Regression threshold as %%; exit non-zero if any p95 regresses by more",
    )
    parser.add_argument("--output", type=Path, help="Also write report to this .md file")
    args = parser.parse_args()

    baseline = collect(args.baseline_dir)
    after = collect(args.after_dir)

    header = [
        "# Performance Regression Report",
        "",
        f"- Baseline: `{args.baseline_dir}`",
        f"- After:    `{args.after_dir}`",
        f"- Regression threshold: {args.threshold:.1f}% (p95)",
        "",
    ]

    lines, regressions = compare(baseline, after, args.threshold)
    report = "\n".join(header + lines) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)

    print(report)

    if regressions > 0:
        print(
            f"\n🚨 {regressions} endpoint p95(s) regressed by more than "
            f"{args.threshold:.1f}%. Failing.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
