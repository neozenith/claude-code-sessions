# T7.4: A user sees the Performance page charts

> **[« G7: Frontend surfacing](./tokenometrics-G7.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 4 of 4 in G7
>
> **Nav:** [« T7.3](./tokenometrics-G7-T7.3.md)  ·  _(last)_ »


- [ ] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** Navigating to `/performance` renders the TPS-by-model chart, the smart-zone utilization histogram, and the idle-vs-active split, honoring the global `days`/`project` filters.
- **Test outline:**
  - File: `frontend/e2e/performance.spec.ts`
  - Name: `performance page renders charts`
  - Asserts: testids `perf-tps-chart`, `perf-zone-histogram`, `perf-idle-active` visible.
- **Implementation outline:**
  - File(s): `frontend/src/pages/Performance.tsx`, route in `App.tsx`, nav in `Layout.tsx`, `api-client.ts` (`getPerformanceSummary` + interface).
- **Mocks:** `none`
- **Depends on:** [T6.2](./tokenometrics-G6-T6.2.md)
