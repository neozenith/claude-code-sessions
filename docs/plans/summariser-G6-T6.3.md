# T6.3: The flag `flat` selects this merger and the driver honors raw_sessions gathering

> - **Gap:** [G6: SummaryMergerFlat (re-summarise raw sessions per scope)](./summariser-G6.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T6.2](./summariser-G6-T6.2.md)

- [ ] **Done**

With the feature flag `flat`, `get_merger('flat')` returns `SummaryMergerFlat` and the driver, reading `merger.child_mode == 'raw_sessions'`, takes the raw-session gathering path and writes `strategy='flat'` rows.

| | |
|--|--|
| Test | `tests/test_merge_flat.py::test_flat_flag_drives_raw_session_path` — run `roll_up_scopes` with `strategy='flat'`; assert the written rows carry `strategy='flat'` and (via a spy on the gather step or row provenance) that the raw-session path was taken, not child-rollup gathering |
| Implements | `src/.../database/sqlite/merge.py` `MERGER_REGISTRY['flat'] = SummaryMergerFlat()`; driver `child_mode` dispatch |
| Depends on | [T6.1](./summariser-G6-T6.1.md), [T3.3](./summariser-G3-T3.3.md) |
