# G10: Empirical benchmark & decision gate

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** [G4](./summariser-G4.md), [G5](./summariser-G5.md), [G6](./summariser-G6.md), [G7](./summariser-G7.md), [G8](./summariser-G8.md), [G9](./summariser-G9.md)
> - **Blocks:** [G11](./summariser-G11.md)
> - **Prev:** [G9](./summariser-G9.md)
> - **Next:** [G11](./summariser-G11.md)

Sweeps the summarisation pipeline across {merge strategy × model family × parameter size}, screens it with reference metrics, lets the user evaluate the survivors **through the real UI** (G7/G8/G9), then makes the binding call that selects the production strategy + model — or abandons. This gap is the decision gate: it produces the information that determines whether the rest of the plan proceeds.

## Context
[G2](./summariser-G2.md) made the engine model-pluggable; [G3](./summariser-G3.md) defined the `SummaryMerger` interface and [G4](./summariser-G4.md)/[G5](./summariser-G5.md)/[G6](./summariser-G6.md) implement strict/reground/flat behind it; [G7](./summariser-G7.md)/[G8](./summariser-G8.md)/[G9](./summariser-G9.md) make every {strategy × model} permutation readable in the UI. Neither winner is known.
The project documents a fit-for-purpose harness in `.claude/rules/python/helper_scripts/cloud_enabled_manifest_pattern.md`: a permutation registry (strategy × model × size), file-existence status tracking, a `manifest` CLI to list/run/resume, one result file per permutation. This gap adopts it rather than inventing a sweeper.
`muninn_chat` loads any GGUF via llama.cpp, so model family/size variants are different GGUF files registered in `temp.muninn_chat_models`.

## Outputs
| File | Change |
|------|--------|
| `data/summary_bench/references/` (curated) | Fixed reference set: sampled sessions with source human text + gold three-lens extraction + model provenance; the ground truth ROUGE-L/BLEU/F1 score against. |
| `scripts/summary_bench.py` (py, new) | Manifest-pattern sweep CLI: permutation registry (strategy × {Gemma,Qwen,Kimi} × {~2B,~4B,~9B}), `manifest`/`run` subcommands, per-permutation result rows, resume via status check; logs skipped (no-GGUF) cells. |
| `src/claude_code_sessions/database/sqlite/summaries.py` (py) | ROUGE-L / BLEU / F1 scorer the bench invokes per generated summary against the reference set. |
| `tmp/summary_bench/` (results) | Per-permutation speed + ROUGE-L/BLEU/F1 outputs (JSON), plus the final ranked comparison. |
| `docs/plans/summariser-G10-REPORT.md` (md, new) | The benchmark report: ranked permutations + the top candidates for human review, recommending PROCEED or ABANDON — the input to the Phase-2 gate. |

## Decision gate
A two-tier gate. **Tier 1 (automated):** ROUGE-L/BLEU/F1 rank the permutations against the curated gold set and discard weak ones. **Tier 2 (human, binding):** the user reads the top survivors **in the explorer (G8) and against the source prompts on SessionDetail (G9)**, applies a subjective threshold, and chooses:

- **PROCEED** — re-enter Phase 2 and **collapse**: settle [ADR3.2](./summariser-G3.md) (production strategy) + the model ([ADR2.1](./summariser-G2.md)), drop the losing `SummaryMerger` implementations + flag, and remove the G7/G8 strategy/model selectors ([ADR7.2](./summariser-G7.md)). Then [G11](./summariser-G11.md) mirrors the collapsed pipeline.
- **ABANDON** — freeze all three strategies as a PoC (the selectors stay), set the default flag to the best-scoring option, stop, and open a new gap-analysis for the discovered failure modes. G11 does not execute.

Per the loop runner, the unresolved selection ADR ([ADR3.2](./summariser-G3.md)) **stops the loop** here until the human reviews the report — the gate is enforced, not advisory.

## ADR10.1: Two-tier evaluation — automated reference metrics, then human taste
- **Decision:** Curate a fixed reference set — a sample of sessions, each holding its source human-message text, a curated gold extraction (the three lenses), and the provenance of which model produced the candidates. Score every permutation against the gold references with **ROUGE-L, BLEU, and F1** as a first-pass automated screen. The top performers then go to a **binding human review** in the G8/G9 UI where the user applies a subjective effectiveness threshold ("to my taste").
- **Why:** Reference metrics are reproducible, fully local, and a cheap coarse filter for "is the summarisation even working?"; nuanced extraction quality is subjective, so a human gate reading the real UI is the real arbiter. Two tiers keep the human's attention for only the best candidates.
- **Rejected:** Groundedness/entailment alone (measures hallucination but not coverage, adds an unvalidated scorer); LLM-as-judge (judge bias, needs a larger model than those under test); a pure human holdout with no automated screen (would force reviewing every permutation).
- **Caveat:** ROUGE/BLEU reward n-gram overlap and under-credit good abstractive extraction; they screen and rank, never pass/fail — the human taste gate ([ADR10.3](./summariser-G10.md)) is binding.

## ADR10.2: Sweep family × parameter size
- **Decision:** The model axis sweeps three families — **Gemma, Qwen, Kimi** — across three approximate parameter buckets — **~2B, ~4B, ~9B** — combined with the three merge strategies. The manifest registry enumerates only the {family × size} cells with an available GGUF and logs any cell skipped for lack of a build (no silent caps).
- **Why:** Isolates the two axes the user wants to tune (family and size) against the strategy axis; the size buckets bound runtime while spanning small→mid local models.
- **Rejected:** A single coder family (misses the cross-family comparison); "whatever is cached" (not a principled grid).

## ADR10.3: Terminal outcomes — proceed-and-collapse vs abandon-as-PoC
- **Decision:** The gate has two terminal outcomes. **PROCEED:** the winner clears the human taste threshold → collapse (drop losing mergers + flag, remove eval selectors) and continue to [G11](./summariser-G11.md). **ABANDON:** nothing clears the threshold → freeze all three as a PoC, set the default flag to the best-scoring option, stop, and open a new gap-analysis scoped to the failure modes discovered. G11 is therefore conditional on PROCEED.
- **Why:** The user is the binding reviewer; if the best achievable quality isn't worth their attention, mirroring it into the introspect script (G11) is wasted effort — exactly what this derisk-first structure avoids.
- **Rejected:** Forcing production regardless of the human verdict (defeats the gate); deleting the PoC on abandon (the three implementations + scores are the input to the follow-up plan).

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T10.1](./summariser-G10-T10.1.md) | A developer scores a candidate summary against a gold reference _(tracer)_ | — |
| [T10.2](./summariser-G10-T10.2.md) | A developer enumerates the permutation registry with done/missing status | [T10.1](./summariser-G10-T10.1.md), [T4.1](./summariser-G4-T4.1.md), [T5.1](./summariser-G5-T5.1.md), [T6.1](./summariser-G6-T6.1.md) |
| [T10.3](./summariser-G10-T10.3.md) | A user lists incomplete permutations via `manifest --missing` | [T10.2](./summariser-G10-T10.2.md) |
| [T10.4](./summariser-G10-T10.4.md) | A user runs one permutation and a result row is written | [T10.1](./summariser-G10-T10.1.md), [T10.2](./summariser-G10-T10.2.md), [T4.1](./summariser-G4-T4.1.md), [T5.1](./summariser-G5-T5.1.md), [T6.1](./summariser-G6-T6.1.md) |
| [T10.5](./summariser-G10-T10.5.md) | Skipped no-GGUF cells are logged, never silently dropped | [T10.2](./summariser-G10-T10.2.md) |
| [T10.6](./summariser-G10-T10.6.md) | A reader gets a report ranking every permutation by score | [T10.4](./summariser-G10-T10.4.md) |
| [T10.7](./summariser-G10-T10.7.md) | A human records the binding PROCEED/ABANDON verdict _(non-code gate)_ | [T10.6](./summariser-G10-T10.6.md), [T8.6](./summariser-G8-T8.6.md), [T9.6](./summariser-G9-T9.6.md) |
| [T10.8](./summariser-G10-T10.8.md) | On PROCEED, collapse the pipeline to the winner _(conditional)_ | [T10.7](./summariser-G10-T10.7.md) |
