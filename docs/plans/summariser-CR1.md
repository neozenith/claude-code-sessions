# CR1: Make the G10 benchmark real, runnable, and self-contained in `summarise_cli`

> - **Index:** [summariser.md](./summariser.md)
> - **Type:** Change Request (midflight discovery)
> - **Discovered in:** [G10](./summariser-G10.md) / [T10.7](./summariser-G10-T10.7.md) — the decision gate could never be reached because the benchmark harness shipped unrunnable.
> - **Status:** in progress — real source-grounded sweep running (2026-06-01). The earlier
>   "done" (2 models, hand-authored gold) was **rejected**: scoring a model against gold *I*
>   invented is circular and not real evidence. See [Correction](#correction-2026-06-01).

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

This CR makes the benchmark **real, self-contained in `summarise_cli`, and reused**. The
done-gate (revised 2026-06-01 after the gold-was-fabricated correction) is: **four real GGUFs
swept across all strategies × all grains over the REAL ingested dogfood corpus, every score
source-grounded against the actual human-prompt text — no fabricated gold anywhere** (the
executable-evidence bar the original plan lacked).

## Scope of work

Fold the benchmark into `src/claude_code_sessions/summarise_cli.py` (reusing the engine,
mergers, driver, and scorer already there) and delete the parallel `scripts/summary_bench.py`.
No KG/embedding/chunking is needed — only events ingestion (already present in the cache), so
short runs over a small batch of sessions are fast.

| Ticket | Behavior | Real-input bar |
|--------|----------|----------------|
| CR1.1 | A real model registry + `models` inventory subcommand: each desired model_id → GGUF filename, searched across `~/.claude/cache/models` + the local models dir; lists downloaded vs missing with path/size. | unit + lists the 2 copied GGUFs as present |
| CR1.2 | Permutation registry + `manifest` folded into `summarise_cli` (model × strategy), with `--missing/--done/--limit/--sort/--commands/--force`; `done` = result-file existence; a permutation whose GGUF is absent is flagged unavailable + logged. Remove `scripts/summary_bench.py`. | unit |
| CR1.3 | ~~Curated gold reference set~~ **Source-grounded scoring** (revised): no fabricated gold. Each generated summary is scored against the *real* human-prompt text it derives from — session summary vs its own prompts (screens model); rollup vs the concatenated real source beneath the scope (screens strategy drift). | no fabrication — corpus is the reference |
| CR1.4 | Real `bench run --id <model__strategy__grain> [--force]`: register the GGUF, `summarise_session` over the in-scope real sessions, score each vs its real source, `roll_up_scopes` via the strategy, score each rollup vs its scope's real source, write the result row. Robust JSON extraction (strip `<think>`/prose). Failures (context overflow, non-JSON) recorded as data. | tracer runs the **real** path (GGUF SQL fn is the only boundary) |
| CR1.5 | `report` ranks the real result rows into `summariser-G10-REPORT.md` by rollup grounding. | report shows real scores |
| **CR1.6 (done gate)** | Sweep **4 GGUFs** (gemma-4-E2B/E4B, Qwen3.5-2B/4B) × 3 strategies × 3 grains = 36 cells over the REAL dogfood corpus (the two repos' resolvable sessions, ~408), full trie depth; produce the report with real source-grounded ROUGE-L/BLEU/F1 + speed per permutation. | committed real result rows + report |

## Notes / decisions

- **No fabricated gold (source grounding).** There is no objective gold summary for a session,
  and hand-authoring one then scoring against it is circular. Instead the *real corpus is the
  reference*: a generated summary is scored by its ROUGE-L/BLEU/F1 overlap with the actual
  human-prompt text it derives from. BLEU here is precision-oriented — fraction of the summary's
  n-grams actually present in the real source — i.e. a direct grounding / anti-hallucination
  measure. Absolute values are low (a summary compresses a much larger source); the *relative*
  ordering is the screen. The binding verdict remains the human taste review (T10.7).
- **Two grounding scores per cell.** Session grounding (summary vs its own prompts) screens the
  **model**; rollup grounding (a scope's rollup vs the concatenated real source beneath it)
  screens the **strategy**'s drift up the hierarchy — the discriminator reground/G5 exists for.
- **Events-only, real ingestion.** The cache already holds the real events; no reingest, chunking
  or KG. The sweep runs over the two dogfood repos' resolvable sessions (~408). Sub-projects whose
  encoded id has no resolvable `sessions-index.json` in `./projects` are skipped (can't be placed
  in the hierarchy) — logged, never faked.
- Chat GGUFs resolve in place from `~/.claude/cache/models` + `~/play/sqlite-vector-graph/models`
  (no copies needed): gemma-4 E2B/E4B, Qwen3.5 0.8B/2B/4B.

## Correction (2026-06-01)

The first pass of this CR was committed as "done" with two models scored against a **hand-authored
3-session gold set** I created and labelled "golden". That is not evidence — it measures only how
closely a model reproduces text *I* invented. Rejected and removed (`data/summary_bench/references/`
deleted, `load_references` gone). The benchmark was rebuilt to:

- score by **source grounding** against the real corpus (no fabricated reference);
- sweep **4 models × 3 strategies × 3 grains** (36 cells) over the **real ingested dogfood corpus**,
  full trie depth — not 3 cherry-picked sessions;
- add session- **and** rollup-level grounding so the strategy axis has a real discriminator.

A 1-session real smoke (the retro's smoke-before-sweep lesson) confirmed the path end-to-end before
the full sweep launched. Real result rows + report are committed when the sweep completes.

### Open follow-up (out of CR1 scope)

`reground`'s unbounded excerpt-token budget is a genuine product gap (its top-scope merge overflows
context on the real corpus). A token-budgeted excerpt selector (bound total tokens, not just count)
is a candidate for a future CR or the G10 ABANDON-branch "new gap-analysis for the discovered
failure modes."

- [ ] **Done** — 4 GGUFs × 36 cells swept over the real dogfood corpus, source-grounded; report committed.
