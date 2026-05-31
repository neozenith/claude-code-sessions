# T4.2: The flag `strict` selects this merger and writes strategy='strict' rows

> - **Gap:** [G4: SummaryMergerStrict (bottom-up, summaries only)](./summariser-G4.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T4.1](./summariser-G4-T4.1.md)
> - **Next:** [T4.3](./summariser-G4-T4.3.md)

- [ ] **Done**

With the feature flag set to `strict`, `get_merger('strict')` returns `SummaryMergerStrict` and the G3 driver writes `rollup_summaries` rows carrying `strategy='strict'`.

| | |
|--|--|
| Test | `tests/test_merge_strict.py::test_strict_flag_drives_rollup` — run `roll_up_scopes` with `strategy='strict'` over a seeded leaf scope; assert the written row's `strategy` column is `'strict'` and its content came from the strict merger |
| Implements | `src/.../database/sqlite/merge.py` `MERGER_REGISTRY['strict'] = SummaryMergerStrict()` |
| Depends on | [T4.1](./summariser-G4-T4.1.md), [T3.3](./summariser-G3-T3.3.md) |
