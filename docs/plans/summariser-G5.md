# G5: SummaryMergerReGround (bottom-up + source re-grounding)

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** [G3](./summariser-G3.md)
> - **Blocks:** [G10](./summariser-G10.md)
> - **Prev:** [G4](./summariser-G4.md)
> - **Next:** [G6](./summariser-G6.md)

Implements the re-grounding merger behind the [G3](./summariser-G3.md) interface: it merges children's summaries **plus a bounded sample of source excerpts** so higher tiers stay faithful, mitigating the hallucination amplification of naive summary-of-summaries (Ou & Lapata, ACL 2025).

## Context
`SummaryMergerReGround` sets `child_mode='child_rollups'`, `wants_excerpts=True`, `name='reground'`. The driver supplies `SourceExcerpts` for the scope; this merger folds them into the prompt. It is the most token-heavy strategy — exactly the speed/fidelity trade the [G10](./summariser-G10.md) benchmark quantifies.

## Outputs
| File | Change |
|------|--------|
| `src/claude_code_sessions/database/sqlite/merge.py` (py) | `SummaryMergerReGround` + the excerpt-selection helper; registered under `'reground'`. |
| `src/claude_code_sessions/database/sqlite/summaries.py` (py) | Driver gathers `SourceExcerpts` per scope when `merger.wants_excerpts`. |
| `tests/test_merge_reground.py` (py, new) | Correctness tests for excerpt inclusion + bounded selection. |

## ADR5.1: Bounded, deterministic excerpt selection
- **Decision:** Re-grounding selects a capped, deterministic sample of source excerpts per merge — the top-K human-prompt excerpts under the scope ordered by a fixed key (recency then length), capped at a constant K so prompt size stays bounded.
- **Why:** Determinism keeps the benchmark reproducible (fixed seed/temp + fixed excerpt set); the cap bounds token cost and latency for the largest top-tier scopes.
- **Rejected:** All excerpts (unbounded prompt blow-up at high tiers); random sampling (non-reproducible across benchmark runs).

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T5.1](./summariser-G5-T5.1.md) | Re-ground merge includes the supplied source excerpts in the engine prompt _(tracer)_ | [T3.1](./summariser-G3-T3.1.md), [T3.3](./summariser-G3-T3.3.md) |
| [T5.2](./summariser-G5-T5.2.md) | Excerpt selection is bounded and deterministic | [T5.1](./summariser-G5-T5.1.md) |
| [T5.3](./summariser-G5-T5.3.md) | Re-ground output differs from strict for the same children | [T5.1](./summariser-G5-T5.1.md) |
