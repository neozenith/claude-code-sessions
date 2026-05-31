# G10 Benchmark Report

Real sweep over the dogfood corpus (no fabricated gold). Every score is
**source grounding** — the generated summary's ROUGE-L/BLEU/F1 overlap against the
*actual human-prompt text it derives from*; the corpus itself is the reference.

- **session (r/b/f)** — a session summary vs its own real prompts → screens the *model*.
- **rollup (r/b/f)** — a scope's rolled-up summary vs the concatenated real source
  beneath it → screens the *strategy*'s drift up the hierarchy (this drives the rank).

Absolute values are low by construction (a summary is a compression of a much larger
source); what matters is the *relative* ordering. These numbers rank and surface — the
binding PROCEED/ABANDON call is the human taste review of the rollups in the UI (T10.7).

| Rank | Permutation | model | strat | grain | sess r/b/f | n | roll r/b/f | n | Combined | status | sec |
|------|-------------|-------|-------|-------|------------|--:|------------|--:|---------:|--------|----:|

## Recommendation

Top automated candidate: `(no results yet)`.

<!-- PROCEED/ABANDON pending the binding human taste review (T10.7) of the top survivors via the G8/G9 UI. The reference metrics above do not decide. -->
