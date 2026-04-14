#!/usr/bin/env python3
"""
Compare DuckDB vs SQLite API latency from Playwright network timing JSON.

Reads every `E00_DUCKDB-*.network.json` / `E01_SQLITE-*.network.json` pair,
aligns them by the slug after the engine prefix, and prints:

1. Per-slug totals — same slug, different engines, side-by-side
2. Per-endpoint aggregates — each API endpoint summed across all slugs
3. Biggest bottlenecks — slowest endpoints on SQLite, with DuckDB comparison

Usage:
    uv run scripts/compare_engines.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

SCREENSHOT_DIR = Path("frontend/e2e-screenshots")
ENGINE_PREFIX_RE = re.compile(r"^E\d+_([A-Z]+)-(.*)\.network\.json$")

# Collapse URLs with unique IDs/slugs into endpoint templates for aggregation.
# Example: /api/timeline/events/-Users-joshpeak-x -> /api/timeline/events/:id
ENDPOINT_TEMPLATES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"/api/timeline/events/[^/?]+"), "/api/timeline/events/:project"),
    (re.compile(r"/api/sessions/[^/?]+/[^/?]+"), "/api/sessions/:project/:session"),
    (re.compile(r"/api/sessions/[^/?]+"), "/api/sessions/:project"),
]


def normalize_url(url: str) -> str:
    """Strip the host and query string, collapse path IDs to template form."""
    path = url.split("://", 1)[-1]
    path = "/" + path.split("/", 1)[-1] if "/" in path else path
    path = path.split("?", 1)[0]
    for pattern, template in ENDPOINT_TEMPLATES:
        if pattern.search(path):
            return pattern.sub(template, path)
    return path


def load_runs() -> dict[str, dict[str, dict[str, Any]]]:
    """Return {slug: {engine: network_summary}}."""
    runs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for path in sorted(SCREENSHOT_DIR.glob("E*.network.json")):
        match = ENGINE_PREFIX_RE.match(path.name)
        if not match:
            continue
        engine, slug = match.group(1).lower(), match.group(2)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        runs[slug][engine] = data
    return runs


def compare_slugs(runs: dict[str, dict[str, dict[str, Any]]]) -> None:
    """Print side-by-side slug totals (API duration only)."""
    print("=" * 90)
    print("PER-SLUG API DURATION (ms) — SQLite vs DuckDB")
    print("=" * 90)
    print(f"{'Slug':<55} {'SQLite':>10} {'DuckDB':>10} {'Δ (D-S)':>10}")
    print("-" * 90)

    rows = []
    for slug, per_engine in runs.items():
        sqlite_ms = per_engine.get("sqlite", {}).get("api_duration_ms", 0)
        duckdb_ms = per_engine.get("duckdb", {}).get("api_duration_ms", 0)
        if sqlite_ms == 0 and duckdb_ms == 0:
            continue
        rows.append((slug, sqlite_ms, duckdb_ms, duckdb_ms - sqlite_ms))

    rows.sort(key=lambda r: -r[3])  # biggest DuckDB-SQLite gap first
    for slug, s, d, delta in rows:
        print(f"{slug:<55} {s:>10} {d:>10} {delta:>+10}")


def aggregate_endpoints(
    runs: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, list[int]]]:
    """{endpoint_template: {engine: [duration_ms, ...]}}"""
    agg: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for per_engine in runs.values():
        for engine, summary in per_engine.items():
            for req in summary.get("all_requests", []):
                if not req.get("is_api"):
                    continue
                endpoint = normalize_url(req["url"])
                agg[endpoint][engine].append(req["duration_ms"])
    return agg


def compare_endpoints(runs: dict[str, dict[str, dict[str, Any]]]) -> None:
    print()
    print("=" * 90)
    print("PER-ENDPOINT LATENCY — median / p95 / count")
    print("=" * 90)
    print(
        f"{'Endpoint':<45} {'Engine':<8} {'median':>8} {'p95':>8} {'max':>8} {'count':>8}"
    )
    print("-" * 90)

    def pct(values: list[int], p: float) -> int:
        if not values:
            return 0
        s = sorted(values)
        idx = min(len(s) - 1, int(len(s) * p))
        return s[idx]

    agg = aggregate_endpoints(runs)

    # Sort endpoints by SQLite p95 descending (biggest bottlenecks first)
    def sqlite_p95(entry: tuple[str, dict[str, list[int]]]) -> int:
        return pct(entry[1].get("sqlite", []), 0.95)

    for endpoint, per_engine in sorted(agg.items(), key=sqlite_p95, reverse=True):
        for engine in ("sqlite", "duckdb"):
            values = per_engine.get(engine, [])
            if not values:
                continue
            med = pct(values, 0.5)
            p95 = pct(values, 0.95)
            mx = max(values)
            print(f"{endpoint:<45} {engine:<8} {med:>8} {p95:>8} {mx:>8} {len(values):>8}")
        print()


def bottleneck_report(runs: dict[str, dict[str, dict[str, Any]]]) -> None:
    print("=" * 90)
    print("TOP SQLITE BOTTLENECKS — ranked by SQLite p95, with DuckDB comparison")
    print("=" * 90)

    def pct(values: list[int], p: float) -> int:
        if not values:
            return 0
        s = sorted(values)
        idx = min(len(s) - 1, int(len(s) * p))
        return s[idx]

    agg = aggregate_endpoints(runs)
    ranked = []
    for endpoint, per_engine in agg.items():
        sqlite_vals = per_engine.get("sqlite", [])
        duckdb_vals = per_engine.get("duckdb", [])
        if not sqlite_vals:
            continue
        s_p95 = pct(sqlite_vals, 0.95)
        d_p95 = pct(duckdb_vals, 0.95) if duckdb_vals else 0
        ranked.append((endpoint, s_p95, d_p95, d_p95 - s_p95))

    ranked.sort(key=lambda r: -r[1])

    print(f"{'Endpoint':<45} {'SQLite p95':>12} {'DuckDB p95':>12} {'SQLite faster by':>18}")
    print("-" * 90)
    for endpoint, s, d, delta in ranked[:10]:
        marker = "SQLite faster" if delta > 0 else "DuckDB faster" if delta < 0 else "tied"
        print(f"{endpoint:<45} {s:>12} {d:>12} {delta:>+14} ms  ({marker})")


def main() -> None:
    runs = load_runs()
    if not runs:
        print(f"No *.network.json files found in {SCREENSHOT_DIR}/")
        return

    print(f"Loaded timing data from {len(runs)} distinct slugs\n")

    compare_slugs(runs)
    compare_endpoints(runs)
    bottleneck_report(runs)


if __name__ == "__main__":
    main()
