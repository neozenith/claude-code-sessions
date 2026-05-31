# G7: Frontend surfacing

> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Depends on:** [G6](./tokenometrics-G6.md)
> - **Blocks:** none
> - **Prev:** [G6](./tokenometrics-G6.md)
> - **Next:** [G8](./tokenometrics-G8.md)

Surface the new metrics and the subagent dimension in the React app: per-event occupancy/TPS/idle on SessionDetail, a Performance page, and sessions-list columns.

## Context

Costs render inflated, with no TPS/idle/context views;
`MessageKind` is subagent-blind;
per-event display shows only In/Out tokens (`SessionDetail.tsx:350`).

## Outputs

| File | Change |
|------|--------|
| `frontend/src/lib/api-client.ts` | extend `SessionEvent`; `MessageKind` allows `subagent-${base}`; add `getSessionMetrics`/`getPerformanceSummary` |
| `frontend/src/lib/message-kinds.ts` | subagent scope dimension; `?msg=` handling |
| `frontend/src/pages/SessionDetail.tsx` | occupancy bar (width ∝ raw `context_ratio`, no zone colors), TPS on heads, idle markers + too-fast badge, subagent badge |
| `frontend/src/pages/Performance.tsx` | new page + route in `App.tsx` + nav in `Layout.tsx` |
| `frontend/src/pages/ProjectSessions.tsx` / `SessionsList.tsx` | new columns |
| `frontend/e2e/session-detail-metrics.spec.ts`, `performance.spec.ts` | e2e |

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); full outlines live in the linked files.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T7.1](./tokenometrics-G7-T7.1.md) | ~~The frontend zone classifier matches the backend bands~~ **Dropped** (zone labeling removed per ADR) | [T2.4](./tokenometrics-G2-T2.4.md) |
| [T7.2](./tokenometrics-G7-T7.2.md) | A user can compose the subagent scope toggle with a kind filter | [T3.1](./tokenometrics-G3-T3.1.md) |
| [T7.3](./tokenometrics-G7-T7.3.md) | A user sees occupancy, TPS and idle markers on the session detail page | [T6.1](./tokenometrics-G6-T6.1.md) |
| [T7.4](./tokenometrics-G7-T7.4.md) | A user sees the Performance page charts | [T6.2](./tokenometrics-G6-T6.2.md) |
