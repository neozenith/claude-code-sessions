# T4.1: Strict merge synthesises one summary from two child summaries

> - **Gap:** [G4: SummaryMergerStrict (bottom-up, summaries only)](./summariser-G4.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T4.2](./summariser-G4-T4.2.md)

- [x] **Done**

`SummaryMergerStrict.merge(engine, model, children, None)` returns one `Summary` whose three lenses synthesise the two child summaries via the engine; the engine prompt contains the children's lens text and no raw source excerpts. _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_merge_strict.py::test_strict_merge_synthesises_children` — call `merge` with two canned child `Summary` objects + a fake engine that records its prompt; assert the returned `Summary` has all three lenses and the prompt contains the children's text |
| Implements | `src/.../database/sqlite/merge.py` `SummaryMergerStrict.merge`, `.child_mode='child_rollups'`, `.wants_excerpts=False` |
| Depends on | [T3.1](./summariser-G3-T3.1.md), [T3.3](./summariser-G3-T3.3.md) |
