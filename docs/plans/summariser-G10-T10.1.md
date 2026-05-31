# T10.1: A developer scores a candidate summary against a gold reference

> - **Gap:** [G10: Empirical benchmark & decision gate](./summariser-G10.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T10.2](./summariser-G10-T10.2.md)

- [x] **Done**

`score_summary(candidate, reference)` returns a dict of deterministic `rouge_l`, `bleu`, and `f1` floats in [0,1] for a fixed candidate/reference pair. _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_summary_scorer.py::test_score_summary_known_pair` — assert exact scores for hand-computed pairs (identical text → all 1.0; disjoint → all 0.0) via the public `score_summary` |
| Implements | `src/.../database/sqlite/summaries.py` `score_summary` |
| Depends on | — |
