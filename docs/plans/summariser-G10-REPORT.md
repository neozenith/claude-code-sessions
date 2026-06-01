# G10 Benchmark Report

Scoped real sweep: the four benchmark projects (two `play`, two `work`), last week,
two fastest models. The model is held constant per table so the **strategies** can be
compared head-to-head on source grounding and speed.

Every score is **source grounding** — the rolled-up summary's ROUGE-L/BLEU/F1 overlap
against the *real* source beneath its scope (the corpus is the reference, no fabricated
gold). Columns (see [SCORING.md](./summariser-SCORING.md)):

- **roll r/b/f** — the lexical triple (relative screen).
- **comp** — compression ratio (summary tokens / source tokens); the recall ceiling.
- **norm** — ROUGE-L as a fraction of its compression-bounded ceiling (achievable %).
- **lead** — combined score of a verbatim first-N-token extract (the extractive ceiling);
  a good *abstractive* summary sits below it — that gap is abstraction the lexical
  metrics can't credit.
- **cos** — embedding cosine (summary vs source, local nomic-embed). Credits paraphrase:
  **high cos with low BLEU = strong *abstractive* grounding** — what lexical misses.

Absolutes are low by construction; *relative* ordering ranks. The binding PROCEED/ABANDON
call is the human taste review of the rollups in the UI (T10.7).

## Qwen3.5-2B

| strategy | grain | n | roll r/b/f | comp | norm | lead | cos | combined | sec | status |
|----------|-------|--:|------------|-----:|-----:|-----:|----:|---------:|----:|--------|
| flat | day | 7 | 0.060/0.000/0.103 | 0.162 | 0.347 | 0.180 | 0.809 | 0.054 | 309 | ok |
| flat | week | 7 | 0.044/0.000/0.080 | 0.106 | 0.382 | 0.125 | 0.809 | 0.041 | 94 | ok |
| reground ⭐ | day | 7 | 0.059/0.006/0.126 | 0.186 | 0.319 | 0.205 | 0.818 | 0.064 | 264 | ok |
| reground | week | 2 | 0.055/0.000/0.110 | 0.084 | 0.349 | 0.103 | 0.799 | 0.055 | 71 | error |
| strict | day | 7 | 0.051/0.000/0.104 | 0.164 | 0.315 | 0.182 | 0.812 | 0.052 | 176 | ok |
| strict | week | 7 | 0.043/0.000/0.076 | 0.105 | 0.377 | 0.123 | 0.788 | 0.040 | 84 | ok |

## Qwen3.5-4B

| strategy | grain | n | roll r/b/f | comp | norm | lead | cos | combined | sec | status |
|----------|-------|--:|------------|-----:|-----:|-----:|----:|---------:|----:|--------|
| flat | day | 7 | 0.053/0.000/0.104 | 0.144 | 0.346 | 0.165 | 0.817 | 0.052 | 477 | ok |
| flat | week | 7 | 0.045/0.004/0.076 | 0.114 | 0.367 | 0.133 | 0.787 | 0.042 | 131 | ok |
| reground ⭐ | day | 7 | 0.067/0.009/0.155 | 0.192 | 0.309 | 0.213 | 0.839 | 0.077 | 447 | ok |
| reground | week | 7 | 0.061/0.005/0.112 | 0.139 | 0.427 | 0.159 | 0.781 | 0.059 | 238 | ok |
| strict | day | 7 | 0.050/0.000/0.105 | 0.145 | 0.320 | 0.166 | 0.827 | 0.052 | 235 | ok |
| strict | week | 7 | 0.044/0.004/0.076 | 0.115 | 0.348 | 0.134 | 0.768 | 0.041 | 127 | ok |

## Qwen3.5-9B

| strategy | grain | n | roll r/b/f | comp | norm | lead | cos | combined | sec | status |
|----------|-------|--:|------------|-----:|-----:|-----:|----:|---------:|----:|--------|
| flat | day | 7 | 0.060/0.000/0.093 | 0.125 | 0.362 | 0.146 | 0.816 | 0.051 | 592 | ok |
| flat | week | 7 | 0.046/0.000/0.065 | 0.084 | 0.420 | 0.098 | 0.781 | 0.037 | 145 | ok |
| reground ⭐ | day | 7 | 0.097/0.028/0.143 | 0.165 | 0.363 | 0.188 | 0.827 | 0.090 | 556 | ok |
| reground | week | 7 | 0.051/0.000/0.083 | 0.092 | 0.366 | 0.108 | 0.758 | 0.045 | 301 | ok |
| strict | day | 7 | 0.058/0.000/0.093 | 0.125 | 0.339 | 0.147 | 0.812 | 0.051 | 295 | ok |
| strict | week | 7 | 0.046/0.000/0.066 | 0.084 | 0.408 | 0.099 | 0.775 | 0.037 | 136 | ok |

## gemma-4-E2B

| strategy | grain | n | roll r/b/f | comp | norm | lead | cos | combined | sec | status |
|----------|-------|--:|------------|-----:|-----:|-----:|----:|---------:|----:|--------|
| flat | day | 7 | 0.059/0.000/0.111 | 0.176 | 0.344 | 0.194 | 0.832 | 0.057 | 388 | ok |
| flat | week | 7 | 0.041/0.000/0.070 | 0.112 | 0.364 | 0.130 | 0.773 | 0.037 | 89 | ok |
| reground ⭐ | day | 7 | 0.066/0.000/0.125 | 0.191 | 0.334 | 0.209 | 0.834 | 0.064 | 274 | ok |
| reground | week | 7 | 0.049/0.000/0.088 | 0.138 | 0.387 | 0.157 | 0.781 | 0.046 | 146 | ok |
| strict | day | 7 | 0.056/0.000/0.111 | 0.175 | 0.316 | 0.194 | 0.828 | 0.056 | 187 | ok |
| strict | week | 7 | 0.041/0.000/0.072 | 0.114 | 0.360 | 0.132 | 0.772 | 0.038 | 90 | ok |

## gemma-4-E4B

| strategy | grain | n | roll r/b/f | comp | norm | lead | cos | combined | sec | status |
|----------|-------|--:|------------|-----:|-----:|-----:|----:|---------:|----:|--------|
| flat | day | 7 | 0.051/0.000/0.094 | 0.145 | 0.341 | 0.166 | 0.798 | 0.048 | 484 | ok |
| flat | week | 7 | 0.038/0.000/0.064 | 0.098 | 0.376 | 0.115 | 0.755 | 0.034 | 113 | ok |
| reground ⭐ | day | 7 | 0.049/0.006/0.111 | 0.169 | 0.315 | 0.187 | 0.815 | 0.055 | 356 | ok |
| reground | week | 7 | 0.047/0.000/0.076 | 0.118 | 0.379 | 0.137 | 0.769 | 0.041 | 207 | ok |
| strict | day | 7 | 0.045/0.000/0.092 | 0.144 | 0.340 | 0.164 | 0.793 | 0.046 | 201 | ok |
| strict | week | 7 | 0.037/0.000/0.064 | 0.098 | 0.360 | 0.114 | 0.748 | 0.034 | 100 | ok |

## Mistral-7B

| strategy | grain | n | roll r/b/f | comp | norm | lead | cos | combined | sec | status |
|----------|-------|--:|------------|-----:|-----:|-----:|----:|---------:|----:|--------|
| flat ⭐ | day | 6 | 0.071/0.014/0.121 | 0.192 | 0.391 | 0.208 | 0.829 | 0.069 | 456 | error |
| flat | week | 6 | 0.044/0.000/0.070 | 0.081 | 0.455 | 0.095 | 0.762 | 0.038 | 130 | error |
| reground | day | 0 | 0.000/0.000/0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 29 | error |
| reground | week | 0 | 0.000/0.000/0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 28 | error |
| strict | day | 6 | 0.067/0.014/0.121 | 0.191 | 0.351 | 0.207 | 0.830 | 0.067 | 215 | error |
| strict | week | 6 | 0.043/0.000/0.072 | 0.082 | 0.430 | 0.096 | 0.755 | 0.038 | 117 | error |

## Llama-3.1-8B

| strategy | grain | n | roll r/b/f | comp | norm | lead | cos | combined | sec | status |
|----------|-------|--:|------------|-----:|-----:|-----:|----:|---------:|----:|--------|
| flat | day | 7 | 0.071/0.008/0.110 | 0.141 | 0.390 | 0.163 | 0.823 | 0.063 | 446 | ok |
| flat | week | 7 | 0.044/0.000/0.075 | 0.102 | 0.423 | 0.119 | 0.766 | 0.039 | 113 | ok |
| reground ⭐ | day | 7 | 0.086/0.010/0.144 | 0.169 | 0.376 | 0.194 | 0.848 | 0.080 | 445 | ok |
| reground | week | 7 | 0.068/0.005/0.111 | 0.113 | 0.431 | 0.132 | 0.801 | 0.061 | 253 | ok |
| strict | day | 7 | 0.068/0.008/0.108 | 0.140 | 0.362 | 0.161 | 0.802 | 0.061 | 190 | ok |
| strict | week | 7 | 0.044/0.000/0.075 | 0.102 | 0.428 | 0.119 | 0.764 | 0.040 | 105 | ok |

## Strategy failures (empirical cost)

- `Mistral-7B__flat__day` — extract 4391e432: no balanced JSON object found in model output
- `Mistral-7B__strict__day` — extract 4391e432: no balanced JSON object found in model output
- `Qwen3.5-2B__reground__week` — rollup failed: no balanced JSON object found in model output
- `Mistral-7B__strict__week` — extract 4391e432: no balanced JSON object found in model output
- `Mistral-7B__flat__week` — extract 4391e432: no balanced JSON object found in model output
- `Mistral-7B__reground__day` — rollup failed: muninn_chat: prompt (10219 tokens) exceeds context (8192)
- `Mistral-7B__reground__day` — extract 4391e432: no balanced JSON object found in model output
- `Mistral-7B__reground__week` — rollup failed: muninn_chat: prompt (11098 tokens) exceeds context (8192)
- `Mistral-7B__reground__week` — extract 4391e432: no balanced JSON object found in model output

## Best strategy per model (automated screen, ok cells only)

- **Qwen3.5-2B**: `reground` (grain day, combined 0.064)
- **Qwen3.5-4B**: `reground` (grain day, combined 0.077)
- **Qwen3.5-9B**: `reground` (grain day, combined 0.090)
- **gemma-4-E2B**: `reground` (grain day, combined 0.064)
- **gemma-4-E4B**: `reground` (grain day, combined 0.055)
- **Mistral-7B**: `flat` (grain day, combined 0.069)
- **Llama-3.1-8B**: `reground` (grain day, combined 0.080)

<!-- PROCEED/ABANDON pending the binding human taste review (T10.7) of the rollups in the G8/G9 UI. The reference metrics above rank and surface; they do not decide. -->
