# T3.7: roll_up_scopes runs only the requested level band

> - **Gap:** [G3: SummaryMerger abstraction + roll-up driver](./summariser-G3.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T3.6](./summariser-G3-T3.6.md)

- [ ] **Done**

`roll_up_scopes(..., level='leaf')` writes rollups only for project-leaf scopes and leaves shallower scopes untouched; `level='root'` writes only the all-domains row — so a cadence trigger can run one tier without recomputing the others (ADR3.4).

| | |
|--|--|
| Test | `tests/test_summaries.py::test_rollup_runs_only_requested_level_band` — seed a multi-level trie, run the driver with `level='leaf'` and assert only leaf-scope rows are written; run again with `level='root'` and assert only the `scope_path=''` row is written; intermediate scopes from the first run are unchanged |
| Implements | `src/.../database/sqlite/summaries.py` `level`-band filter in `roll_up_scopes` (selects scopes by `scope_depth`) |
| Depends on | [T3.2](./summariser-G3-T3.2.md) |
