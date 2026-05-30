# T7.3: A user sees occupancy, TPS and idle markers on the session detail page

> **[« G7: Frontend surfacing](./tokenometrics-G7.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 3 of 4 in G7
>
> **Nav:** [« T7.2](./tokenometrics-G7-T7.2.md)  ·  [T7.4 »](./tokenometrics-G7-T7.4.md)


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** Loading a real session renders a context-occupancy bar (width ∝ raw `context_ratio`, no zone colors) and TPS on assistant heads, and an idle-gap marker between turns (with a fast-reply badge when flagged).
- **Test outline:**
  - File: `frontend/e2e/session-detail-metrics.spec.ts`
  - Name: `session detail shows occupancy, tps and idle markers`
  - Asserts: testids `context-occupancy-bar`, `response-tps`, `idle-gap` are visible after navigating to a discovered session (follows `session-detail-filter.spec.ts` discovery pattern).
- **Implementation outline:**
  - File(s): `frontend/src/pages/SessionDetail.tsx` (EventCard bar + TPS + idle markers; `MESSAGE_KIND_CONFIG` subagent accent), `api-client.ts` (`SessionEvent` new fields + `getSessionMetrics`).
- **Mocks:** `none` (real backend per project e2e convention).
- **Depends on:** [T6.1](./tokenometrics-G6-T6.1.md)
