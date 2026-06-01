# ADR3.2 — Production merge strategy (RESOLVED)

> - **Status:** Accepted (2026-06-01) — resolves the `<!-- UNRESOLVED -->` placeholder in
>   [summariser-G3.md](./summariser-G3.md) via the [G10](./summariser-G10.md) empirical gate (T10.7).
> - **Decision owner:** human verdict on the benchmark evidence below (ADR3.1 deferred this to G10).
> - **Evidence:** [summariser-G10-REPORT.md](./summariser-G10-REPORT.md) (42 cells) · scoring method
>   [summariser-SCORING.md](./summariser-SCORING.md) · scorecard rationale [CR4](./summariser-CR4.md).

## Context

[ADR3.1](./summariser-G3.md) built all three merge strategies behind one flagged `SummaryMerger`
interface and **deferred the production choice to an empirical benchmark** rather than upfront
reasoning. CR1–CR4 made that benchmark real: a source-grounded sweep (no fabricated gold) over the
**real dogfood corpus** — 4 projects (2 `play`, 2 `work`), last 7 days, 21 sessions — across a
**7-model panel** × **3 strategies** × **day/week** grains (42 cells), scored with a *located*
scorecard (lexical ROUGE-L/BLEU/F1 + compression-normalised + lead anchor + embedding cosine + speed).

## How the three strategies work (the mechanics that drive this decision)

Two **independent** axes: **scope height** (leaf project → domain → root) and **time grain**
(day/week/month). The merge tree is over *height*; **grain does not stack** — each grain is its own
walk from `session_summaries`, so coarser grain means *bigger buckets*, not more tree layers.

- **strict** (`child_rollups`, no excerpts) — bottom-up, summaries-only: each ancestor merges its
  direct child *scopes'* rollups. Drift compounds with height; ancestor prompts stay small (N child
  scopes) → most overflow-resistant at high scopes.
- **reground** (`child_rollups` + excerpts) — same tree as strict, but every merge also injects a
  bounded sample of **raw source excerpts**, re-anchoring each level to what actually happened.
  Counters height-drift; costs excerpt tokens → **overflows context** at big buckets/scopes.
- **flat** (`raw_sessions`, no excerpts) — no height tree: each scope merges **all descendant
  session summaries** in one prompt. No compounding, but the prompt grows with descendant count →
  **explodes first** at high/coarse scopes.

## Evidence

**By strategy (mean over ok cells, all 7 models):**

| strategy | n | rouge_l | bleu | f1 | embed cos |
|----------|--:|--:|--:|--:|--:|
| **reground** | 11 | **0.064** | **0.006** | **0.116** | **0.806** |
| flat | 12 | 0.051 | 0.001 | 0.087 | 0.797 |
| strict | 12 | 0.049 | 0.001 | 0.087 | 0.791 |

**Split by grain (embed cosine):** day — reground **0.830** / flat 0.816 / strict 0.812;
week — flat **0.779** / reground 0.778 / strict 0.769.

**Best cell per model (reground/day) + clean generation speed:**

| model | embed cos | combined | s/summary | ctx |
|-------|--:|--:|--:|--:|
| Llama-3.1-8B | **0.848** | 0.080 | 10.1 | 128k |
| Qwen3.5-4B | 0.839 | 0.077 | 9.8 | 32k |
| gemma-4-E2B | 0.834 | 0.064 | 9.1 | 16k |
| Qwen3.5-9B | 0.827 | **0.090** | 11.4 | 32k |
| Qwen3.5-2B | 0.818 | 0.064 | **5.3** | 32k |
| gemma-4-E4B | 0.815 | 0.055 | 11.5 | 16k |
| Mistral-7B | *reground failed (8k ctx overflow)* | | 9.4 | 8k |

What the numbers establish:
1. **reground is the only strategy whose mechanism is visibly working** — its BLEU is ~6–10× the
   others (0.006–0.010 vs 0.001), i.e. it provably keeps the rollup's wording anchored to source;
   cosine confirms it semantically. It wins overall and **decisively at day grain**.
2. **strict ≈ flat — statistically indistinguishable.** Without re-grounding, how children are
   gathered barely matters; both drift at the same rate. strict is never beaten by flat.
3. **The advantage is grain/height-regime-dependent.** At *week* the three converge (reground's
   excerpts dilute/overflow on a shallow, small corpus). But the mechanics predict the regimes our
   benchmark under-samples: **coarser grain** makes flat overflow first (single all-descendants
   prompt); **deeper tries** make reground's advantage *grow* (more layers to re-anchor) while
   strict's drift compounds harder.

## Decision

**PROCEED — reground is the production strategy, applied grain/height-aware:**

1. **reground @ daily** is the default and the proven winner.
2. **reground at week/month and for multi-height domain refinement is preferred *where the context
   budget holds*** — its advantage increases with depth. This makes it **contingent on a large
   context window** (Llama-3.1-8B's 128k, or a 32k model with [CR3](./summariser-CR3.md) map-reduce
   batching). The 128k context is therefore a *first-class enabler of this decision*, not a nicety.
3. **strict is the deterministic fallback** when the excerpt budget is blown (coarse grain / deep
   trie on a small-context model with no batching) — its bounded ancestor merges scale to high
   scopes. **Not flat** — flat overflows at exactly those scopes and never beat strict on quality.
4. **flat is deprecated to shallow/small scopes only** (where overflow is impossible and its simpler
   dependency graph is a minor convenience); it is not a coarse/deep-regime option.
5. **Model:** any of Qwen3.5-4B (balanced default, 32k), Qwen3.5-2B (~1.9× faster, for full-corpus
   sweeps), or Llama-3.1-8B (best grounding + 128k → reground at scale without CR3). **Mistral-7B is
   rejected** (8k context cannot hold reground). The model choice is a values trade across
   speed/grounding/context, not a quality cliff.

## Consequences

- **The "collapse" (G11) keeps two strategies, not one.** ADR3.1 anticipated collapsing to a single
  winner; the evidence instead supports a **context-aware policy: reground primary, strict fallback**
  (flat removable). G11 should mirror *reground* as the default and retain strict as the bounded
  fallback rather than deleting all losers.
- **reground's viability at scale depends on context** → either standardise on a 128k-class model or
  build **CR3** (map-reduce batching). This couples the model decision to the grain/height decision.
- **The weekly result sits near a regime boundary** and the corpus is shallow (3-level trie, 21
  sessions). Before committing reground at *month* grain and *deep* domains, a confirming slice is
  warranted (see Follow-up) — the mechanics predict reground re-separates from strict with depth, but
  that is reasoned, not yet measured.
- **The G10 gate is satisfied** with real, quantitative, multi-model evidence — the executable bar
  CR1 was raised to restore after the stubbed-benchmark detour.

## Follow-up (to confirm the coarse/deep regime empirically)

- Run a **month-grain** and a **deeper-scope** (≥4-level) slice to verify reground re-separates from
  strict with height and that flat overflows first at high scopes — turning the reasoned regime
  prediction above into measured evidence.
- Build [CR3](./summariser-CR3.md) batching if a 32k model must run reground at coarse/deep scopes.
