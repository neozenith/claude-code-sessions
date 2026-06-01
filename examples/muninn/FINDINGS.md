# CR2 — muninn LLM dial-in findings

The recipe the summariser (CR1) should adopt, and the evidence behind it.

## The recipe

Drive generation with the **4-arg** call, never the bare 2-arg form:

```sql
muninn_chat(model, prompt, THREE_LENS_GBNF, max_tokens)   -- max_tokens = 512
```

`THREE_LENS_GBNF` bounds each lens string to `LENS_MAX = 300` chars; `max_tokens = 512` is generous
headroom above the grammar's max possible output, so the object always completes.

- **`max_tokens` bounds time** — without it a thinking model generates until EOS and
  can hang for minutes (the CR1 stall: 7+ min on one session at ~7% CPU).
- **The GBNF grammar bounds shape** — it forces exactly
  `{"task_summary": "...", "patterns": "...", "decisions_values": "..."}` and, because a
  grammar-constrained decode must match `root` from the first token, **the model cannot emit a
  `<think>` preamble at all**. No per-model thinking-disable flag (`/no_think`) was needed — the
  grammar is the cleaner lever. This also eliminates the non-JSON parse failures seen earlier.

The grammar lives in `examples/muninn/_muninn.py` as `THREE_LENS_GBNF`.

## Two GBNF gotchas (both cost real debugging)

1. **`root` must be a single logical line.** muninn's GBNF parser treats a newline as
   end-of-rule, so a wrapped `root ::=` errors with `expecting name` and then **segfaults the
   process** (exit 139). Keep `root` on one line; alternation rules go on their own lines.
2. **The unescaped string class must exclude control chars** — `[^"\\\x00-\x1F]`. Without the
   `\x00-\x1F` exclusion the model emits a raw newline inside a value and `json.loads` fails with
   *Invalid control character*. Allow only valid JSON escapes: `"\\" ["\\/bfnrt]`.
3. **Bound each string's length in the grammar** — `{0,300}`. On the *sample* an unbounded string
   was fine, but on a real 12k-char session the model wrote a long `task_summary` that ran past
   `max_tokens` and truncated **mid-string** → *Unterminated string*. Bounding the string in the
   grammar guarantees the object closes within budget regardless of how verbose the model is; a
   bigger `max_tokens` alone does not (a verbose model just hits the higher cap).

## Evidence (max_tokens=512, LENS_MAX=300, 2026-06-01)

Sample prompt, `--all`:

| model | n_ctx | load | gen | valid JSON | all keys |
|-------|------:|-----:|----:|:----------:|:--------:|
| Qwen3.5-4B  | 32768 | 0.5s | 15.7s | ✅ | ✅ |
| gemma-4-E4B | 16384 | 0.7s | 21.2s | ✅ | ✅ |
| Qwen3.5-2B  | 32768 | 0.4s | 11.4s | ✅ | ✅ |
| gemma-4-E2B | 16384 | 0.6s | 19.0s | ✅ | ✅ |

Real session (12,162 chars of human prompts, Qwen3.5-4B): grammar recipe **valid JSON, all keys,
31.1s** (the larger figure is prefill of the longer input); `muninn_summarize` returned clean prose
in 11.3s but **not** the 3-lens shape — which is why the summariser needs the grammar recipe, not
`muninn_summarize`.

All four bench models produce bounded, valid, 3-lens JSON — the CR2.5 done-gate, confirmed on both
sample and real input. **Qwen models carry 2× the context (32k vs 16k)** — better headroom for the
large-session tail; the ~50k-char outlier still overflows even 32k and should fast-fail (record as
data).

Reproduce: `uv run examples/muninn/json_grammar_probe.py --all`
and `uv run examples/muninn/summarize_probe.py`

## Handoff to CR1

`MuninnSummaryEngine.summarise` (G2) and the G3 merge calls switch from
`muninn_chat(model, prompt)` to `muninn_chat(model, prompt, THREE_LENS_GBNF, max_tokens)`. With
generation bounded, the real 4-model × 36-cell dogfood sweep is tractable (~hours, predictable) and
resumes from its durable `session_summaries` checkpoint. The robust JSON extraction in
`summary_json.parse_lenses` stays as a belt-and-braces guard, but grammar-constrained output should
now always parse.
