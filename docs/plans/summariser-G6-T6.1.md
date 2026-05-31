# T6.1: Flat builds a scope's rollup from raw descendant session summaries

> - **Gap:** [G6: SummaryMergerFlat (re-summarise raw sessions per scope)](./summariser-G6.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T6.2](./summariser-G6-T6.2.md)

- [x] **Done**

With the `flat` strategy, `roll_up_scopes` gathers every `session_summaries` row under a scope's `scope_path` prefix (for that model) and `SummaryMergerFlat.merge` synthesises them directly — no child `rollup_summaries` are read. _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_merge_flat.py::test_flat_builds_from_raw_descendant_sessions` — seed an ancestor scope with descendant session summaries (and no child rollups), run the driver with `flat`, assert the ancestor rollup is produced and its content derives from the raw sessions |
| Implements | `src/.../database/sqlite/merge.py` `SummaryMergerFlat` (`child_mode='raw_sessions'`); `src/.../database/sqlite/summaries.py` raw-session gathering path |
| Depends on | [T3.1](./summariser-G3-T3.1.md), [T3.3](./summariser-G3-T3.3.md) |
