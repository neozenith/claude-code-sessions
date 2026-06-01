# CR4: A located, gaming-resistant scorecard (compression, anchors, semantic, LLM-judge)

> - **Index:** [summariser.md](./summariser.md)
> - **Type:** Change Request (midflight discovery)
> - **Discovered in:** [CR1](./summariser-CR1.md) — the bare ROUGE/BLEU/F1 triple is a *relative*
>   screen whose absolutes are uninterpretable (low by construction when scoring vs full source).
> - **Analysis:** [summariser-SCORING.md](./summariser-SCORING.md) — what each score means, its
>   failure/gaming modes, the compression ceiling, and the anchoring method.
> - **Status:** proposed (2026-06-01)

## Why this CR exists

"Are these scores good?" can't be answered by a lexical triple alone — the numbers are low by
construction (summary vs full source) and every lexical metric penalises good abstraction. To place a
row on the **bad→good→great** spectrum we need (a) the compression context that bounds the achievable
score, (b) **anchors** that bracket the band, and (c) a human-aligned absolute. See the analysis doc.

## Scope of work

| Ticket | Behavior | Real-input bar |
|--------|----------|----------------|
| CR4.1 | **Compression ratio + normalisation** — emit `compression_ratio = len(summary)/len(source)` and `rouge_l_normalised = rouge_l / ceiling(compression_ratio)` per scored row (the "% of achievable"). | unit on known lengths |
| CR4.2 | **Anchors** — score, against the same source, a `lead-N` extract (first N chars) and an `oracle-extractive` (greedy ROUGE-maximising extract of the summary's length). Report each row's position on `[lead → oracle]`. | unit: model summary placed between lead and oracle |
| CR4.3 | **Embedding cosine** — `cos(embed(summary), embed(source))` via the local embedder (`muninn_embed` / nomic / bge). Paraphrase-aware grounding that BLEU misses. | runs on real rows; high-cos/low-BLEU surfaces good abstraction |
| CR4.4 | **LLM-as-judge** — a G-Eval-style pass rating each summary 1–5 on faithfulness/coverage/coherence vs source, using a **large** model as judge (judging < generating). The human-aligned absolute. | runs on real rows; judge ≥4 = great |
| CR4.5 | **Report the vector** — every strategy×model row carries lexical + compression + anchors + cosine + (optional) judge + speed; report renders the located scorecard. | the report answers "good/great" with anchors, not a bare triple |
| **CR4.6 (done gate)** | Re-run the 4-project last-week matrix — including the new Qwen3.6 model(s) — so each row reports the **full located scorecard**, and the report states where each model/strategy sits on the lead→oracle band. | committed report with located scores |

## Notes / decisions

- **Keep the lexical triple** — it's the cheap deterministic relative screen and the gaming-balance
  system (SCORING §1). CR4 *contextualises* it, it does not replace it.
- **LLM-judge is the only one that needs a big model** — and judging is the right job for one. This
  is where a downloaded Qwen3.6-27B / 35B-A3B earns its keep (as the *judge*, not necessarily the
  generator).
- **Anchors are deterministic** — lead and oracle are pure functions of source + length, so the
  located score is reproducible.
- **Pairs with CR3** — over-context rows still need map-reduce batching to be scorable at all.

- [ ] **Done** — located scorecard (compression + anchors + cosine + judge) on a re-run of the
  matrix incl. Qwen3.6; report states each row's band position.
