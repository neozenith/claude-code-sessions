# T7.4: A user sees the Performance page charts

> - **Gap:** [G7: Frontend surfacing](./tokenometrics-G7.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Prev:** [T7.3](./tokenometrics-G7-T7.3.md)

- [x] **Done**

Navigating to `/performance` renders the TPS-by-model chart, the context-ratio utilization histogram (binned by raw `context_ratio`, no zone labels), and the idle-vs-active split, honoring the global `days`/`project` filters.

| | |
|--|--|
| Test | `frontend/e2e/performance.spec.ts::performance page renders charts` — testids `perf-tps-chart`, `perf-context-histogram`, `perf-idle-active` visible |
| Implements | `frontend/src/pages/Performance.tsx`, route in `App.tsx`, nav in `Layout.tsx`, `api-client.ts` (`getPerformanceSummary` + interface) |
| Depends on | [T6.2](./tokenometrics-G6-T6.2.md) |
