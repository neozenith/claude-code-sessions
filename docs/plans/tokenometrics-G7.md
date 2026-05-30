# G7: Frontend surfacing

> **[« Tokenometrics index](./tokenometrics.md)**  ·  Gap 7 of 8
>
> **Depends on:** [G6](./tokenometrics-G6.md)  ·  **Blocks:** none
>
> **Nav:** [« G6](./tokenometrics-G6.md)  ·  [G8 »](./tokenometrics-G8.md)

**Current:** Costs render inflated; no TPS/idle/context views; `MessageKind` is subagent-blind; per-event display shows only In/Out tokens (`SessionDetail.tsx:350`).

**Gap:** Surface the new metrics and the subagent dimension.

**Output(s):**
- `frontend/src/lib/api-client.ts` (TS): extend `SessionEvent`; `MessageKind` allows `subagent-${base}`; add `getSessionMetrics`/`getPerformanceSummary` + interfaces.
- `frontend/src/lib/message-kinds.ts` (TS): subagent dimension; `?msg=` handling.
- `frontend/src/pages/SessionDetail.tsx` (TS/React): per-event context-occupancy bar (smart-zone bands), TPS on heads, idle markers + too-fast badge, subagent badge in `MESSAGE_KIND_CONFIG`.
- `frontend/src/pages/Performance.tsx` (TS/React) + route in `App.tsx` + nav in `Layout.tsx`.
- `frontend/src/pages/ProjectSessions.tsx` / `SessionsList.tsx` (TS/React): new columns.
- E2E: `frontend/e2e/session-detail-metrics.spec.ts`, `frontend/e2e/performance.spec.ts`.

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); the full Test/Implementation outlines live in the per-ticket files linked below.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T7.1](./tokenometrics-G7-T7.1.md) | The frontend zone classifier matches the backend bands | [T2.4](./tokenometrics-G2-T2.4.md) |
| [T7.2](./tokenometrics-G7-T7.2.md) | A user can compose the subagent scope toggle with a kind filter | [T3.1](./tokenometrics-G3-T3.1.md) |
| [T7.3](./tokenometrics-G7-T7.3.md) | A user sees occupancy, TPS and idle markers on the session detail page | [T6.1](./tokenometrics-G6-T6.1.md), [T7.1](./tokenometrics-G7-T7.1.md) |
| [T7.4](./tokenometrics-G7-T7.4.md) | A user sees the Performance page charts | [T6.2](./tokenometrics-G6-T6.2.md) |

