# T5.3: Re-ground output differs from strict for the same children

> - **Gap:** [G5: SummaryMergerReGround (bottom-up + source re-grounding)](./summariser-G5.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T5.2](./summariser-G5-T5.2.md)

- [ ] **Done**

Given identical children but non-empty excerpts, the re-ground merger's engine input includes the excerpts while strict's does not — so the two strategies produce observably different prompts (the behavioral distinction the benchmark measures).

| | |
|--|--|
| Test | `tests/test_merge_reground.py::test_reground_prompt_differs_from_strict` — record the engine prompt from `SummaryMergerReGround.merge` and from `SummaryMergerStrict.merge` for the same children + excerpts; assert the reground prompt contains the excerpt markers and the strict one does not |
| Implements | `src/.../database/sqlite/merge.py` `SummaryMergerReGround` (registered `'reground'`) |
| Depends on | [T5.1](./summariser-G5-T5.1.md) |
