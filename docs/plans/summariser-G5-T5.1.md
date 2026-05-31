# T5.1: Re-ground merge includes the supplied source excerpts in the engine prompt

> - **Gap:** [G5: SummaryMergerReGround (bottom-up + source re-grounding)](./summariser-G5.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T5.2](./summariser-G5-T5.2.md)

- [ ] **Done**

`SummaryMergerReGround.merge(engine, model, children, excerpts)` with `wants_excerpts=True` folds the provided `SourceExcerpts` text into the engine prompt alongside the child summaries. _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_merge_reground.py::test_reground_includes_excerpts_in_prompt` — call `merge` with canned children + a `SourceExcerpts` carrying known marker text and a fake engine recording its prompt; assert the prompt contains both the children's text and the excerpt markers |
| Implements | `src/.../database/sqlite/merge.py` `SummaryMergerReGround.merge`, `.wants_excerpts=True` |
| Depends on | [T3.1](./summariser-G3-T3.1.md), [T3.3](./summariser-G3-T3.3.md) |
