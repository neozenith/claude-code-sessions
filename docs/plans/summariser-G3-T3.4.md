# T3.4: A (strategy, model) rollup merges only that model's child summaries

> - **Gap:** [G3: SummaryMerger abstraction + roll-up driver](./summariser-G3.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T3.3](./summariser-G3-T3.3.md)
> - **Next:** [T3.5](./summariser-G3-T3.5.md)

- [x] **Done**

When `session_summaries` for the same session exist under two models, `roll_up_scopes(..., model=M)` merges only the model-`M` rows — the resulting rollup's `child_count` and content derive solely from model-`M` children (ADR3.3 model scoping).

| | |
|--|--|
| Test | `tests/test_summaries.py::test_rollup_selects_only_matching_model_children` — seed one leaf scope with session summaries under model A and model B, run the driver for model A, assert the model-A rollup's `child_count` counts only the A rows and a separate model-B run yields a distinct row |
| Implements | `src/.../database/sqlite/summaries.py` `roll_up_scopes` model-scoped child `WHERE model = ?` selection |
| Depends on | [T3.1](./summariser-G3-T3.1.md) |
