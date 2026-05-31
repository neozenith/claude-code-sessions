# T5.2: Excerpt selection is bounded and deterministic

> - **Gap:** [G5: SummaryMergerReGround (bottom-up + source re-grounding)](./summariser-G5.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T5.1](./summariser-G5-T5.1.md)
> - **Next:** [T5.3](./summariser-G5-T5.3.md)

- [ ] **Done**

The excerpt selector returns at most K excerpts, chosen by a fixed key (recency then length), and the same inputs always yield the same selection (ADR5.1).

| | |
|--|--|
| Test | `tests/test_merge_reground.py::test_excerpt_selection_bounded_and_deterministic` — given more than K candidate excerpts, assert the selector returns exactly K, the expected top-K by the fixed key, and an identical result on a second call |
| Implements | `src/.../database/sqlite/merge.py` `select_excerpts(candidates, k)` |
| Depends on | [T5.1](./summariser-G5-T5.1.md) |
