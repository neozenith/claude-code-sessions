# G7: Summaries query layer & API

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** [G1](./summariser-G1.md), [G2](./summariser-G2.md), [G3](./summariser-G3.md)
> - **Blocks:** [G8](./summariser-G8.md), [G9](./summariser-G9.md), [G10](./summariser-G10.md)
> - **Prev:** [G3](./summariser-G3.md)
> - **Next:** [G8](./summariser-G8.md)

Exposes session and roll-up summaries through typed endpoints honoring the global `days`/`project` filters, addressed by the variable-depth `scope_path`. Built **before** the benchmark because the human-evaluation tier of the [G10](./summariser-G10.md) gate reads summaries through this API.

## Context
Query methods live in `backend.py`, routes in `main.py`, the typed contract in `database/protocol.py`, mirrored in `frontend/src/lib/api-client.ts`.
G2/G3 populate `session_summaries` and `rollup_summaries`. During the [G10](./summariser-G10.md) sweep the tables hold **multiple strategies × models at once**, so every endpoint takes optional `strategy` + `model` selectors (defaulting, post-collapse, to the single production value). Scopes are addressed by `scope_path` (G1); a `children` listing lets the UI drill the trie. An un-summarised scope reports that explicitly (fail-loud), never fabricates.

## Outputs
| File | Change |
|------|--------|
| `src/claude_code_sessions/database/sqlite/backend.py` (py) | `get_session_summary(project_id, session_id, *, model)`; `get_rollup_summary(scope_path, time_granularity, time_bucket, *, strategy, model, days, project)`; `list_scope_children(scope_path, *, days, project)`; `list_summary_variants()` (available strategy/model pairs for the eval picker). |
| `src/claude_code_sessions/database/protocol.py` (py) | Protocol signatures + typed return shapes (incl. the `not_summarised` status union). |
| `src/claude_code_sessions/main.py` (py) | `GET /api/summaries/session/{project_id}/{session_id}`, `GET /api/summaries/scope?path=&grain=&bucket=&strategy=&model=`, `GET /api/summaries/scope/children?path=`, `GET /api/summaries/variants`, honoring `days`/`project`. |
| `tests/` (py) | Endpoint tests: variable-depth scope addressing, strategy/model selection, the "not yet summarised" status path. |

## ADR7.1: Explicit not-summarised status, never a fabricated summary
- **Decision:** An un-summarised but valid scope returns `200` with a discriminated union `{status: "not_summarised"}`; a genuinely unknown scope returns `404`. The endpoint never invents a placeholder summary.
- **Why:** Matches the project's explicit-typed-payload style and the fail-loud rule — the frontend renders a clear empty state, and "exists but not yet summarised" is distinguishable from "no such scope."
- **Rejected:** `404` for an un-summarised scope (conflates "missing" with "not yet computed").

## ADR7.2: Strategy/model-parameterised for evaluation, collapse after
- **Decision:** Every summary endpoint accepts optional `strategy` + `model` selectors so the benchmark's permutations are comparable side-by-side in the UI. After a PROCEED collapse ([ADR10.3](./summariser-G10.md)), the selectors are removed and the API serves only the winning strategy/model.
- **Why:** The human-evaluation tier of the gate needs to compare permutations through the real UI before one is chosen; baking in a single strategy too early would block evaluation.
- **Rejected:** Permanently keeping the selectors in production (contradicts "collapse and remove alternatives"); a separate throwaway eval API (duplicates query logic).

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T7.1](./summariser-G7-T7.1.md) | A consumer retrieves the three lenses of a summarised session _(tracer)_ | [T2.1](./summariser-G2-T2.1.md) |
| [T7.2](./summariser-G7-T7.2.md) | A consumer retrieves a roll-up summary for a scope at a grain+bucket | [T7.1](./summariser-G7-T7.1.md), [T3.1](./summariser-G3-T3.1.md) |
| [T7.3](./summariser-G7-T7.3.md) | A consumer selects a specific strategy/model variant | [T7.2](./summariser-G7-T7.2.md) |
| [T7.4](./summariser-G7-T7.4.md) | A valid-but-unsummarised scope is reported explicitly | [T7.2](./summariser-G7-T7.2.md), [T1.2](./summariser-G1-T1.2.md) |
| [T7.5](./summariser-G7-T7.5.md) | An unknown scope returns 404 | [T7.4](./summariser-G7-T7.4.md) |
| [T7.6](./summariser-G7-T7.6.md) | A consumer drills the scope trie one level via children listing | [T7.2](./summariser-G7-T7.2.md), [T1.2](./summariser-G1-T1.2.md) |
| [T7.7](./summariser-G7-T7.7.md) | A consumer lists the available strategy/model variants | [T7.3](./summariser-G7-T7.3.md) |
