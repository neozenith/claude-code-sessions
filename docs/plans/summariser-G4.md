# G4: SummaryMergerStrict (bottom-up, summaries only)

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** [G3](./summariser-G3.md)
> - **Blocks:** [G10](./summariser-G10.md)
> - **Prev:** [G3](./summariser-G3.md)
> - **Next:** [G5](./summariser-G5.md)

Implements the strict bottom-up merger behind the [G3](./summariser-G3.md) `SummaryMerger` interface: it synthesises a scope's three lenses from its children's summaries alone, with no source re-grounding — the cheapest, GraphRAG-style strategy.

## Context
`SummaryMergerStrict` sets `child_mode='child_rollups'`, `wants_excerpts=False`, and `name='strict'`. It is one of three benchmarked implementations ([G3](./summariser-G3.md) ADR3.1); the [G10](./summariser-G10.md) gate decides whether it ships. Correctness here is about faithful synthesis of children and the no-excerpts contract.

## Outputs
| File | Change |
|------|--------|
| `src/claude_code_sessions/database/sqlite/merge.py` (py) | `SummaryMergerStrict` implementing the Protocol; registered in `MERGER_REGISTRY` under `'strict'`. |
| `tests/test_merge_strict.py` (py, new) | Correctness tests for the strict merger via the public `merge` + driver. |

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T4.1](./summariser-G4-T4.1.md) | Strict merge synthesises one summary from two child summaries _(tracer)_ | [T3.1](./summariser-G3-T3.1.md), [T3.3](./summariser-G3-T3.3.md) |
| [T4.2](./summariser-G4-T4.2.md) | The flag `strict` selects this merger and writes `strategy='strict'` rows | [T4.1](./summariser-G4-T4.1.md), [T3.3](./summariser-G3-T3.3.md) |
| [T4.3](./summariser-G4-T4.3.md) | Strict ignores source excerpts (summary-only contract) | [T4.1](./summariser-G4-T4.1.md) |
