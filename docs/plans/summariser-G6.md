# G6: SummaryMergerFlat (re-summarise raw sessions per scope)

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** [G3](./summariser-G3.md)
> - **Blocks:** [G10](./summariser-G10.md)
> - **Prev:** [G5](./summariser-G5.md)
> - **Next:** [G7](./summariser-G7.md)

Implements the flat merger behind the [G3](./summariser-G3.md) interface: every scope re-summarises the raw `session_summaries` under its subtree directly, with no intermediate child-rollup tier.

## Context
`SummaryMergerFlat` sets `child_mode='raw_sessions'`, `wants_excerpts=False`, `name='flat'`. The driver, seeing `child_mode='raw_sessions'`, gathers all descendant `session_summaries` (by `scope_path` prefix) for that model rather than child rollups. This is the simplest dependency graph but produces the largest prompts at high tiers — the trade the [G10](./summariser-G10.md) benchmark quantifies.

## Outputs
| File | Change |
|------|--------|
| `src/claude_code_sessions/database/sqlite/merge.py` (py) | `SummaryMergerFlat`; registered under `'flat'`. |
| `src/claude_code_sessions/database/sqlite/summaries.py` (py) | Driver's `raw_sessions` gathering path (descendant `session_summaries` by `scope_path` prefix, scoped to the model). |
| `tests/test_merge_flat.py` (py, new) | Correctness tests for raw-session gathering + child_count semantics. |

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T6.1](./summariser-G6-T6.1.md) | Flat builds a scope's rollup from raw descendant session summaries _(tracer)_ | [T3.1](./summariser-G3-T3.1.md), [T3.3](./summariser-G3-T3.3.md) |
| [T6.2](./summariser-G6-T6.2.md) | A flat ancestor's child_count counts descendant sessions, not child scopes | [T6.1](./summariser-G6-T6.1.md) |
| [T6.3](./summariser-G6-T6.3.md) | The flag `flat` selects this merger and the driver honors raw_sessions gathering | [T6.1](./summariser-G6-T6.1.md), [T3.3](./summariser-G3-T3.3.md) |
