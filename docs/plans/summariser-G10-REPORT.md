# G10 Benchmark Report

Permutations ranked by the automated screen — mean(ROUGE-L, BLEU, F1) of each
model's session extraction against the curated gold set. The metric *screens
the model*; merge-strategy faithfulness is the human's call (T10.7) reading the
rollups in the G8/G9 UI. These numbers rank and surface; they do not decide.

| Rank | Permutation | model | strategy | n | ROUGE-L | BLEU | F1 | Combined | status | sec |
|------|-------------|-------|----------|--:|--------:|-----:|---:|---------:|--------|----:|
| 1 | `gemma-4-E2B__flat`  — review candidate | gemma-4-E2B | flat | 3 | 0.206 | 0.077 | 0.367 | 0.217 | ok | 52.11 |
| 2 | `gemma-4-E2B__reground` | gemma-4-E2B | reground | 3 | 0.206 | 0.077 | 0.367 | 0.217 | error | 112.84 |
| 3 | `gemma-4-E2B__strict` | gemma-4-E2B | strict | 3 | 0.206 | 0.077 | 0.367 | 0.217 | ok | 85.95 |
| 4 | `Qwen3.5-2B__flat` | Qwen3.5-2B | flat | 3 | 0.198 | 0.070 | 0.336 | 0.202 | ok | 35.22 |
| 5 | `Qwen3.5-2B__reground` | Qwen3.5-2B | reground | 3 | 0.198 | 0.070 | 0.336 | 0.202 | error | 21.65 |
| 6 | `Qwen3.5-2B__strict` | Qwen3.5-2B | strict | 3 | 0.198 | 0.070 | 0.336 | 0.202 | ok | 105.6 |

## Strategy failures (empirical cost)

- `gemma-4-E2B__reground` — rollup failed: muninn_chat: prompt (27301 tokens) exceeds context (16384)
- `Qwen3.5-2B__reground` — rollup failed: no balanced JSON object found in model output

## Recommendation

Top automated candidate: `gemma-4-E2B__flat`.

<!-- PROCEED/ABANDON pending the binding human taste review (T10.7) of the top survivors via the G8/G9 UI. The reference metrics above do not decide. -->
