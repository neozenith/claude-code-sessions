"""Evidence-based context-window sizing for the ADR3.2 summariser sweep.

Answers "what n_ctx do we actually need?" from measured data, not guesses:

1. Calibrates a word-token -> LLM(BPE)-token ratio from the REAL overflow ground
   truth recorded in the round-2 result JSONs (every extract/rollup that exceeded
   its context reported its exact LLM token count).
2. PART A - per-session EXTRACTION prompt size distribution (header + the session's
   human texts), the cost of `summarise_session`.
3. PART B - per-(scope, grain, bucket) REGROUND MERGE prompt size, dominated by the
   top-`_EXCERPT_K` full human messages `select_excerpts` injects (no per-excerpt
   length cap -> the real overflow driver).

Then reports, for candidate n_ctx values, what fraction of sessions/merges fit.

Run:  uv run --frozen scripts/ctx_sizing.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from claude_code_sessions.config import CACHE_DB_PATH, PROJECTS_PATH
from claude_code_sessions.database.sqlite.summaries import _EXCERPT_K, _PROMPT_HEADER
from claude_code_sessions.project_resolver import ProjectResolver, ancestor_scopes

RESULTS_DIR = Path(__file__).resolve().parent.parent / "tmp" / "summary_bench_adr32"
CANDIDATE_CTX = [16384, 32768, 65536, 98304, 131072]
_WORD = re.compile(r"\w+")


def word_tokens(text: str) -> int:
    """Word-token count (the bench's `_tokenize` unit)."""
    return len(_WORD.findall(text))


def bucket_key(ts: str, grain: str) -> str:
    """Approximate the SQL bucket_expr: day=YYYY-MM-DD, month=YYYY-MM, week=YYYY-Www."""
    if grain == "day":
        return ts[:10]
    if grain == "month":
        return ts[:7]
    # week: ISO-ish year-week from the date prefix
    try:
        import datetime as _dt

        d = _dt.date.fromisoformat(ts[:10])
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except ValueError:
        return ts[:7]


def calibrate_ratio(conn: sqlite3.Connection) -> float:
    """LLM_tokens / word_tokens, fit from recorded overflow errors.

    Each `extract <sid8>: ... prompt (N tokens) exceeds context` gives the LLM
    token count of that session's extraction prompt; we recompute the same
    prompt's word tokens and take the median ratio.
    """
    # Map session_id prefix -> measured LLM prompt tokens (from any result JSON).
    measured: dict[str, int] = {}
    for jf in RESULTS_DIR.glob("*.json"):
        rec = json.loads(jf.read_text(encoding="utf-8"))
        for err in rec.get("extract_errors", []):
            m = re.search(r"extract (\w{8}): muninn_chat: prompt \((\d+) tokens\)", err)
            if m:
                measured[m.group(1)] = max(measured.get(m.group(1), 0), int(m.group(2)))
    if not measured:
        return 1.45  # fallback: typical English+code BPE inflation

    ratios: list[float] = []
    for sid8, llm_tok in measured.items():
        rows = conn.execute(
            """SELECT message_content FROM events
               WHERE session_id LIKE ? AND msg_kind='human' AND message_content IS NOT NULL
               ORDER BY timestamp, line_number""",
            (sid8 + "%",),
        ).fetchall()
        if not rows:
            continue
        prompt = _PROMPT_HEADER + "\n\n".join(str(r[0]) for r in rows)
        wt = word_tokens(prompt)
        if wt > 0:
            ratios.append(llm_tok / wt)
    ratios.sort()
    if not ratios:
        return 1.45
    median = ratios[len(ratios) // 2]
    print(
        f"Calibration: {len(ratios)} overflow sessions -> "
        f"LLM/word ratio median={median:.3f} "
        f"(min={ratios[0]:.3f}, max={ratios[-1]:.3f})"
    )
    return median


def pct(sorted_vals: list[int], p: float) -> int:
    if not sorted_vals:
        return 0
    return sorted_vals[min(len(sorted_vals) - 1, int(p / 100 * len(sorted_vals)))]


def fit_table(llm_sizes: list[int], label: str) -> None:
    n = len(llm_sizes)
    if n == 0:
        print(f"  ({label}: no data)")
        return
    s = sorted(llm_sizes)
    print(
        f"  {label}: n={n}  median={pct(s, 50):,}  p90={pct(s, 90):,}  "
        f"p95={pct(s, 95):,}  p99={pct(s, 99):,}  max={s[-1]:,}"
    )
    for c in CANDIDATE_CTX:
        fits = sum(1 for v in s if v <= c)
        print(f"      n_ctx {c:>7,}: fits {fits:>4}/{n}  ({100 * fits / n:5.1f}%)")


def main() -> None:
    resolver = ProjectResolver(PROJECTS_PATH)
    conn = sqlite3.connect(f"file:{CACHE_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    ratio = calibrate_ratio(conn)
    to_llm = lambda wt: int(wt * ratio)  # noqa: E731

    # --- gather all human events once: (project_id, session_id, ts, text) ---
    rows = conn.execute(
        """SELECT project_id, session_id, timestamp, message_content AS txt
           FROM events
           WHERE msg_kind='human' AND message_content IS NOT NULL AND timestamp IS NOT NULL"""
    ).fetchall()

    # Resolve each project's ancestor scope chain once (skip unresolvable).
    chain: dict[str, list[str]] = {}
    for pid in {r["project_id"] for r in rows}:
        try:
            chain[pid] = ancestor_scopes(resolver, pid)
        except KeyError:
            chain[pid] = []

    # ---------------- PART A: per-session extraction prompts ----------------
    sess_texts: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        if chain.get(r["project_id"]):
            sess_texts[(r["project_id"], r["session_id"])].append(str(r["txt"]))
    sess_llm = [
        to_llm(word_tokens(_PROMPT_HEADER + "\n\n".join(txts))) for txts in sess_texts.values()
    ]
    print(f"\n=== PART A: session EXTRACTION prompts (n={len(sess_llm)} sessions) ===")
    fit_table(sess_llm, "extraction prompt LLM tokens")

    # ---------------- PART B: reground MERGE prompts ----------------
    # All scopes in the trie = union of every project's ancestor chain (incl. '').
    all_scopes: set[str] = {s for ch in chain.values() for s in ch}
    print(f"\n=== PART B: reground MERGE prompts (excerpt-dominated, K={_EXCERPT_K}) ===")
    print(f"  scopes in trie: {len(all_scopes)}  (incl. root '')")
    for grain in ("day", "week", "month"):
        # bucket -> scope -> list[(ts, word_tokens_of_msg)]
        per: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
        for r in rows:
            ch = chain.get(r["project_id"])
            if not ch:
                continue
            b = bucket_key(str(r["timestamp"]), grain)
            wt = word_tokens(str(r["txt"]))
            for sc in ch:
                per[(sc, b)].append((str(r["timestamp"]), wt))
        merge_llm: list[int] = []
        for msgs in per.values():
            # select_excerpts: top-K by recency (then length) -> sum FULL texts.
            msgs.sort(key=lambda x: (x[0], x[1]), reverse=True)
            excerpt_wt = sum(wt for _ts, wt in msgs[:_EXCERPT_K])
            n_children = min(len(msgs), _EXCERPT_K)  # rough child-summary allowance
            merge_wt = 200 + n_children * 225 + excerpt_wt  # header + child summaries + excerpts
            merge_llm.append(to_llm(merge_wt))
        fit_table(merge_llm, f"{grain} merge LLM tokens")

    conn.close()


if __name__ == "__main__":
    main()
