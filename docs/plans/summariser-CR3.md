# CR3: Map-reduce batching for over-context inputs

> - **Index:** [summariser.md](./summariser.md)
> - **Type:** Change Request (midflight discovery)
> - **Discovered in:** [CR1](./summariser-CR1.md) — the real corpus has a long tail of large
>   sessions/scopes (one ~50k-char session; busy domain/all rollups) that exceed the model context
>   window and currently **fast-fail** (recorded as `rollup_error` / `extract_errors`).
> - **Relates to:** [CR2](./summariser-CR2.md) (bounded generation) — CR2 bounds *output*; CR3
>   bounds *input* by batching when it exceeds the window.
> - **Status:** proposed (2026-06-01)

## Why this CR exists

The summariser feeds the whole input into one `muninn_chat` call:

- **session summary** — all of a session's human prompts concatenated;
- **rollup merge** — all of a scope's child summaries (plus, for reground, source excerpts).

When that concatenation exceeds the model's `n_ctx` (16k for gemma, 32k for Qwen — see
`examples/muninn/FINDINGS.md`) the call fails. Today that is recorded as data and the cell is
skipped, which is honest but means the largest, most interesting scopes (a busy week's "all
domains" rollup; a marathon session) produce **no** summary.

The user's insight is the standard fix: **if the collection is larger than the window, batch it,
summarise each batch, then combine the batch summaries as though they were one input** —
map-reduce / hierarchical summarisation. CR2 already gives us the bounded, valid-JSON generation
call to apply at every level; CR3 adds the batching control flow around it.

## Scope of work

| Ticket | Behavior | Real-input bar |
|--------|----------|----------------|
| CR3.1 | A token/char budget derived from the registered model's `n_ctx` (with headroom for the prompt scaffold + bounded output). A single helper decides "does this input fit?" for both call sites. | unit on a known `n_ctx` |
| CR3.2 | **Batch** — split an over-budget collection (a session's human turns, or a scope's child summaries/excerpts) into ordered, budget-fitting batches. Deterministic (stable order), never splits below a single atomic item. | unit: N items over budget → K fitting batches |
| CR3.3 | **Map** — summarise each batch with the CR2 recipe into a partial 3-lens object. | runs on the real ~50k-char session |
| CR3.4 | **Reduce** — merge the partial summaries into one 3-lens object (reuse the existing merge prompt + grammar); recurse if the partials themselves overflow. | over-context session/rollup yields a valid 3-lens summary, not a fast-fail |
| **CR3.5 (done gate)** | The real over-context outliers (the ~50k-char session; an over-context domain/all rollup) produce **valid 3-lens summaries** via batching instead of being skipped; the bench records them as scored rows. | committed result rows for previously-failing cells |

## Notes / decisions

- **Reuse, don't reinvent.** Map and reduce both go through the CR2 4-arg call
  (`THREE_LENS_GBNF` + `max_tokens`); reduce reuses the G3 merge prompt. CR3 is control flow
  (detect → split → map → reduce → recurse), not a new generation path.
- **Determinism.** Batching order is fixed (chronological for a session; the existing
  `select_excerpts` total order for a scope) so the benchmark stays reproducible.
- **Not blocking the current scoped run.** The last-week 4-project matrix is ~21 small sessions and
  fits the window, so the 168-summary run needs no batching. CR3 lands the general capability for
  the large-scope tail and any future full-corpus sweep.

- [ ] **Done** — over-context sessions and rollups produce valid 3-lens summaries via map-reduce
  batching; previously-failing cells now score.
