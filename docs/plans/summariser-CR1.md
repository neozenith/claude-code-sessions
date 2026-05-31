# CR1: Make the G10 benchmark real, runnable, and self-contained in `summarise_cli`

> - **Index:** [summariser.md](./summariser.md)
> - **Type:** Change Request (midflight discovery)
> - **Discovered in:** [G10](./summariser-G10.md) / [T10.7](./summariser-G10-T10.7.md) — the decision gate could never be reached because the benchmark harness shipped unrunnable.
> - **Status:** done (2026-06-01)

## Why this CR exists

G10's tickets (T10.1–T10.6) were each marked done and each passed its named test, yet
`scripts/summary_bench.py` could not produce a single real result row:

- `_generate_candidate` (the model-execution seam) was a `NotImplementedError` stub.
- `_gguf_available` hard-coded `return True` — no real downloaded-vs-missing inventory.
- The curated gold reference set (`data/summary_bench/references/`) was never created.
- The harness was a parallel `scripts/` script that **re-implemented** summarisation rather
  than calling the in-package production path (`summarise_cli.py`'s `summarise_session` /
  `roll_up_scopes` / mergers / `score_summary`).

Net: the two-tier gate (T10.7) was unreachable — no survivor could be generated to review.
A blameless retrospective (general-purpose subagent, 2026-06-01) traced this to the plan-gap
skill having **no "executable evidence" acceptance bar**, a `Mocks` row that legitimised a
load-bearing stub, a tracer that proved the scorer instead of the generate→score→write path,
and no "smoke-run-before-full-sweep" rule. See the linked recommendations in the session log.

This CR makes the benchmark **real, self-contained in `summarise_cli`, and reused** — and is
**done only when two already-available GGUFs have been swept across all their permutations and
scored with real numbers** (the executable-evidence bar the original plan lacked).

## Scope of work

Fold the benchmark into `src/claude_code_sessions/summarise_cli.py` (reusing the engine,
mergers, driver, and scorer already there) and delete the parallel `scripts/summary_bench.py`.
No KG/embedding/chunking is needed — only events ingestion (already present in the cache), so
short runs over a small batch of sessions are fast.

| Ticket | Behavior | Real-input bar |
|--------|----------|----------------|
| CR1.1 | A real model registry + `models` inventory subcommand: each desired model_id → GGUF filename, searched across `~/.claude/cache/models` + the local models dir; lists downloaded vs missing with path/size. | unit + lists the 2 copied GGUFs as present |
| CR1.2 | Permutation registry + `manifest` folded into `summarise_cli` (model × strategy), with `--missing/--done/--limit/--sort/--commands/--force`; `done` = result-file existence; a permutation whose GGUF is absent is flagged unavailable + logged. Remove `scripts/summary_bench.py`. | unit |
| CR1.3 | A small curated gold reference set under `data/summary_bench/references/` (real sessions: source human text + hand-curated 3-lens gold) + a loader. | committed fixtures |
| CR1.4 | Real `bench run --id <perm> [--force]`: register the model's GGUF, run `summarise_session` over the reference sessions, `roll_up_scopes` via the strategy, score the model's per-session extraction vs gold with `score_summary`, write the result row. Robust JSON extraction from model output (strip `<think>`/prose). Default skips a done cell; `--force` overwrites. | tracer runs the **real** path (GGUF SQL fn is the only boundary) |
| CR1.5 | `report` ranks the real result rows into `summariser-G10-REPORT.md`. | report shows real scores |
| **CR1.6 (done gate)** | Copy 2 GGUFs (gemma-4-E2B + Qwen3.5-2B), sweep both across all strategies over the small batch, and produce the report with **real** ROUGE-L/BLEU/F1 + speed per permutation. | committed real result rows + report |

## Notes / decisions

- **Scored unit = per-session 3-lens extraction vs gold** (the spec's gold is per-session, ADR10.1),
  so the automated score screens the **model**; the **strategy** axis is judged by the human on
  rollup faithfulness in the G8/G9 UI (T10.7). Each permutation still *runs* its rollup (real
  artifact for review); the result row records both the model-level score and the strategy.
- **Events-only**: the existing cache already holds events (1,437 sessions / 7,732 human events);
  no reingest, no chunking, no KG needed for the sweep.
- Available chat GGUFs (copyable from `~/play/sqlite-vector-graph/models/`): gemma-4 E2B/E4B,
  Qwen3.5 0.8B/2B/4B.

## Done evidence (CR1.6 gate met — 2026-06-01)

Two real GGUFs (gemma-4-E2B, Qwen3.5-2B) swept across **all three** strategies over the
3-session curated gold set, scored with real numbers. Report:
[summariser-G10-REPORT.md](./summariser-G10-REPORT.md).

| Permutation | ROUGE-L | BLEU | F1 | status | sec |
|-------------|--------:|-----:|---:|--------|----:|
| `gemma-4-E2B__flat`     | 0.206 | 0.077 | 0.367 | ok    | 52.1 |
| `gemma-4-E2B__strict`   | 0.206 | 0.077 | 0.367 | ok    | 86.0 |
| `gemma-4-E2B__reground` | 0.206 | 0.077 | 0.367 | error | 112.8 |
| `Qwen3.5-2B__flat`      | 0.198 | 0.070 | 0.336 | ok    | 35.2 |
| `Qwen3.5-2B__strict`    | 0.198 | 0.070 | 0.336 | ok    | 105.6 |
| `Qwen3.5-2B__reground`  | 0.198 | 0.070 | 0.336 | error | 21.7 |

**Empirical findings the real run surfaced (the point of the executable-evidence bar):**

1. The automated screen ranks the **model** — extraction scores are identical across a model's
   three strategies (same `summarise_session`; ADR10.1), and gemma-4-E2B edges out Qwen3.5-2B.
2. **`reground` is infeasible for both models on this corpus**: gemma's excerpt-laden merge
   prompt hit 27,301 tokens vs the 16,384 context window; Qwen returned no parseable JSON.
   `select_excerpts` bounds excerpt *count* (ADR5.1) but not *total tokens* — a real cost of the
   reground strategy, recorded as first-class data (`status: error` + `rollup_error`), not hidden.
3. The benchmark now records a model-boundary failure as a result row rather than crashing the
   sweep, so the report is always complete and the failures are auditable.

**Reuse achieved:** the harness calls the production path verbatim — `summarise_session`,
`roll_up_scopes`, the registered mergers, and `score_summary` — with the registered GGUF
`muninn_chat` SQL function as the *only* external boundary. `scripts/summary_bench.py` (the
parallel re-implementation with stubs) was deleted.

### Open follow-up (out of CR1 scope)

`reground`'s unbounded excerpt-token budget is a genuine product gap surfaced here, not a CR1
deliverable. If the strategy is to remain viable it needs a token-budgeted excerpt selector
(bound total tokens, not just count) — a candidate for a future CR or the G10 ABANDON-branch
"new gap-analysis for the discovered failure modes."

- [x] **Done** — two GGUFs × all permutations swept and scored with real numbers; report committed.
