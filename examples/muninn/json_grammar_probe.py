"""CR2.2 — 3-lens JSON grammar probe (the recipe dial-in).

Forces `muninn_chat` to emit exactly the summariser's 3-lens object via a GBNF
grammar, with an explicit max_tokens bound, and checks per model: valid JSON,
all three keys present, output length, wall time. This is the call shape the
summariser should adopt (replacing its unbounded 2-arg call).

    uv run examples/muninn/json_grammar_probe.py            # dial-in model only
    uv run examples/muninn/json_grammar_probe.py --all      # + validation set
"""

from __future__ import annotations

import argparse
import json
import logging
import time

import _muninn

log = logging.getLogger("json_grammar_probe")

MAX_TOKENS = _muninn.MAX_TOKENS

# A realistic stand-in for a session's concatenated human prompts (CR2.3 runs the
# same recipe over real text pulled from the cache).
SAMPLE = (
    "Build a hierarchical session summariser. Resolve each project to a "
    "home-relative scope path and walk a variable-depth scope trie. Make the merge "
    "strategy pluggable behind a registry — strict, reground, flat — and pick the "
    "winner with an empirical benchmark. Score summaries by grounding them in the "
    "real source text. Keep everything local via the muninn GGUF engine; fail loud, "
    "never silently degrade."
)


def _probe_model(conn: object, model_id: str) -> dict[str, object]:
    prompt = (
        "Summarise the developer's prompts below into a single JSON object with keys "
        '"task_summary", "patterns", "decisions_values".\n\nPrompts:\n' + SAMPLE
    )
    t0 = time.perf_counter()
    row = conn.execute(  # type: ignore[attr-defined]
        "SELECT muninn_chat(?, ?, ?, ?)",
        (model_id, prompt, _muninn.THREE_LENS_GBNF, MAX_TOKENS),
    ).fetchone()
    secs = time.perf_counter() - t0
    raw = row[0] if row and row[0] is not None else ""
    result: dict[str, object] = {"model": model_id, "secs": round(secs, 2), "chars": len(raw)}
    try:
        obj = json.loads(raw)
        missing = [k for k in _muninn.LENS_KEYS if k not in obj]
        result["valid_json"] = True
        result["all_keys"] = not missing
        result["task_summary"] = str(obj.get("task_summary", ""))[:160]
    except json.JSONDecodeError as exc:
        result["valid_json"] = False
        result["all_keys"] = False
        result["error"] = str(exc)
        result["raw_head"] = raw[:160]
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="Also run the 2B/4B validation set")
    args = ap.parse_args()

    models = list(_muninn.MODELS) if args.all else [_muninn.DIAL_IN_MODEL]
    for model_id in models:
        conn = _muninn.open_conn()
        t0 = time.perf_counter()
        n_ctx = _muninn.register(conn, model_id)
        load = time.perf_counter() - t0
        r = _probe_model(conn, model_id)
        verdict = "PASS" if r.get("valid_json") and r.get("all_keys") else "FAIL"
        log.info(
            "[%s] %s  n_ctx=%d load=%.1fs gen=%.2fs out=%dchars valid_json=%s all_keys=%s",
            verdict, model_id, n_ctx, load, r["secs"], r["chars"], r["valid_json"], r["all_keys"],
        )
        if verdict == "PASS":
            log.info("   task_summary: %s", r["task_summary"])
        else:
            log.info("   error=%s raw_head=%s", r.get("error"), r.get("raw_head"))
        conn.close()


if __name__ == "__main__":
    main()
