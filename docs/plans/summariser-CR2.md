# CR2: Dial in the base muninn LLM invocation in small focused prototypes

> - **Index:** [summariser.md](./summariser.md)
> - **Type:** Change Request (midflight discovery)
> - **Discovered in:** [CR1](./summariser-CR1.md) — the real source-grounded sweep stalled because the
>   summariser drives `muninn_chat` with the wrong call shape (no output bound, no grammar), so a
>   thinking model runs away on large real sessions.
> - **Blocks:** [CR1](./summariser-CR1.md) (the real sweep cannot be made tractable until the base
>   generation call is dialed in) and the production summariser generation path (G2 `summarise_session`,
>   G3 merge prompts).
> - **Status:** done (2026-06-01) — recipe dialed in: `muninn_chat(model, prompt, THREE_LENS_GBNF,
>   512)` yields bounded, valid 3-lens JSON on all four bench models (sample + real 12k-char input),
>   zero runaway. See [`examples/muninn/FINDINGS.md`](../../examples/muninn/FINDINGS.md). CR1 adopts
>   next and the sweep resumes.

## Why this CR exists

CR1's first real sweep over the dogfood corpus **hung for 7+ minutes on a single session** at ~7%
CPU and made no progress. Root cause, confirmed against the `sqlite-muninn` reference examples:

`MuninnSummaryEngine.summarise` calls the SQL function with **two args** —
`muninn_chat(model, prompt)` — which has **no output-token cap and no output grammar**. The real
signature is:

```
muninn_chat(model, prompt [, grammar [, max_tokens]])
```

So on a large, messy real session a thinking model (Qwen3) emits an unbounded
`<think>…</think>` block and never reaches the answer — *"empty — model exhausted tokens on
reasoning"* in the reference example. That is the same defect behind the earlier non-JSON parse
failures. A summariser that can hang indefinitely on one real session is broken independently of
the benchmark.

The reference repo solves exactly this with small, runnable prototypes that drive the base
functions directly and dial in the knobs **before** wiring them into anything larger:

- `sqlite-vector-graph/examples/llm_chat/*.py` — `muninn_chat` plain, `<think>` separation, and
  **GBNF-grammar-constrained JSON** ("GBNF guarantees valid JSON — no think blocks possible").
- `sqlite-vector-graph/examples/llm_summarize/*.py` — `muninn_summarize(model, text)`, which strips
  `<think>` internally and returns clean output.
- `sqlite-vector-graph/examples/er_v3/*.py` — a higher-level `muninn_extract_er()` C function (the
  pattern of a fixed system+user prompt + structured output baked into one call).

This CR ports that practice into this repo: a handful of focused probe scripts that nail the base
LLM call (bounded output, valid JSON, per-model thinking control) for our 3-lens summary and merge
needs — then CR1 adopts the dialed-in recipe.

## Scope of work

Small, runnable probe scripts under `examples/muninn/` (mirroring the reference repo's `examples/`
convention), each with a `main()` and run via `uv run`. They drive the real GGUF via the muninn SQL
functions — no mocks, fail-loud.

**Models: dial in on a 4B (`Qwen3.5-4B`); never below 2B.** Sub-2B models are *less capable* and
were the leading cause of the thinking/JSON-termination failures — fewer parameters cause **more**
structured-output issues, not fewer, regardless of any tokens/sec advantage. So iterate on the
reliable 4B, then validate the recipe across the four bench GGUFs (gemma-4-E2B/E4B, Qwen3.5-2B/4B).
The 0.8B is explicitly excluded.

| Ticket | Behavior | Real-input bar |
|--------|----------|----------------|
| CR2.1 | `chat_probe.py` — drive `muninn_chat` in 2/3/4-arg forms across all models; print each model's `n_ctx`, `<think>`/response split, output length, and wall time. Demonstrate the **runaway without `max_tokens`** vs **bounded with it**. | runs on the real GGUFs; shows the bound taking effect |
| CR2.2 | `json_grammar_probe.py` — a GBNF grammar (and/or muninn's JSON-Schema path, if exposed) forcing the **3-lens object** `{task_summary, patterns, decisions_values}`; verify every model emits **valid, bounded** JSON in seconds. Record which models need thinking disabled (e.g. `/no_think`) for the schema to terminate. | valid parseable 3-lens JSON on all 4 bench models |
| CR2.3 | `summarize_probe.py` — `muninn_summarize` vs grammar-constrained `muninn_chat` on a few representative *real* session texts (short, medium, near-context); compare cleanliness, boundedness, and grounding. | runs on real session text pulled from the cache |
| CR2.4 | `examples/muninn/FINDINGS.md` — the dialed-in recipe: per-model `max_tokens`, the grammar/schema, thinking control, and `n_ctx` headroom; plus the over-context behavior (fast-fail vs truncate decision). | a reproducible recipe, not prose |
| **CR2.5 (done gate)** | The recipe demonstrably yields **bounded, valid 3-lens JSON on all four bench models, each in single-digit seconds, with zero runaway**, over a small batch of real session texts — ready for CR1's `MuninnSummaryEngine` to adopt. | committed probe output + FINDINGS recipe |

## Notes / decisions

- **Prototypes, not regression tests (yet).** Like the reference examples these are runnable probes
  whose job is to *dial in* the call, printing observations. A thin real pytest asserting "bounded
  valid 3-lens JSON on the smallest model" lands when CR1 adopts the recipe — not here.
- **Thinking control is per-model.** The user's prior experience: with some models a JSON-Schema
  alone "wouldn't terminate the thinking" — thinking had to be disabled explicitly. CR2.2 records
  the exact knob per model rather than assuming one global setting.
- **Bound output AND constrain shape.** `max_tokens` bounds *time*; a grammar/schema bounds *shape*
  (valid JSON, no think block). The recipe uses both — they solve different failure modes.
- **Over-context is a separate axis.** Sessions whose prompt exceeds `n_ctx` (the ~50k-char tail)
  fast-fail today; CR2.3 records whether to keep fast-fail (record as data) or add a bounded-input
  truncation — a decision handed back to CR1, not silently taken here.

## How CR1 consumes this

CR1's `MuninnSummaryEngine.summarise` (and the G3 merge prompts) switch from the bare 2-arg
`muninn_chat(model, prompt)` to the dialed-in 4-arg form (grammar + `max_tokens`) — or to
`muninn_summarize` where that is cleaner. With generation bounded to single-digit seconds per call,
the real 4-model × 36-cell dogfood sweep becomes tractable (~1–2h) and the non-JSON failures
disappear. CR1 resumes from its durable `session_summaries` checkpoint once the recipe is in.

- [x] **Done** (2026-06-01) — bounded, valid 3-lens JSON on all four bench models (sample + real
  input), zero runaway; probes + recipe committed under `examples/muninn/`. CR1 adopts the 4-arg
  call next.
