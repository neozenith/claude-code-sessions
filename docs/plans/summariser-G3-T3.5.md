# T3.5: source_hash freshness scoped by (model, strategy) skips unchanged

> - **Gap:** [G3: SummaryMerger abstraction + roll-up driver](./summariser-G3.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T3.4](./summariser-G3-T3.4.md)
> - **Next:** [T3.6](./summariser-G3-T3.6.md)

- [ ] **Done**

A second driver run over identical inputs computes the same `source_hash` (hash of `strategy`, `model`, child ids + content_hashes) per scope and performs zero engine calls; changing a child summary, the model, or the strategy flips the hash and triggers re-merge (ADR3.3).

| | |
|--|--|
| Test | `tests/test_summaries.py::test_source_hash_freshness_scoped_by_model_strategy` — run twice with a call-counting stub merger (assert second run = 0 calls, `generated_at` unchanged); then mutate a child summary and assert that scope re-merges; then run a different model and assert it computes (distinct row) |
| Implements | `src/.../database/sqlite/summaries.py` `source_hash` computation + skip-if-unchanged guard in `roll_up_scopes` |
| Depends on | [T3.1](./summariser-G3-T3.1.md) |
