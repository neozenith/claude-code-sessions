# T4.3: Strict ignores source excerpts (summary-only contract)

> - **Gap:** [G4: SummaryMergerStrict (bottom-up, summaries only)](./summariser-G4.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T4.2](./summariser-G4-T4.2.md)

- [ ] **Done**

`SummaryMergerStrict.wants_excerpts` is `False`, and calling `merge` with excerpts supplied produces the same engine prompt as calling it with `None` — strict never consumes source text.

| | |
|--|--|
| Test | `tests/test_merge_strict.py::test_strict_ignores_excerpts` — call `merge` once with `excerpts=None` and once with a non-empty `SourceExcerpts`, recording the engine prompt both times; assert the prompts are identical and `wants_excerpts is False` |
| Implements | `src/.../database/sqlite/merge.py` `SummaryMergerStrict` (excerpts unused) |
| Depends on | [T4.1](./summariser-G4-T4.1.md) |
