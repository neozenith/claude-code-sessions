# T8.6: A user viewing an un-summarised scope sees the not_summarised empty state

> - **Gap:** [G8: Summaries explorer page](./summariser-G8.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T8.5](./summariser-G8-T8.5.md)

- [ ] **Done**

When the G7 API reports a scope has no summary, the page renders a `not_summarised` empty state instead of empty/blank lens cards.

| | |
|--|--|
| Test | `frontend/e2e/summaries.spec.ts::un-summarised scope shows not_summarised empty state` (playwright) — `goto` with a `?path=` known un-summarised, `waitForFunction` until settled, assert `[data-testid="summary-empty"]` visible and the three `lens-*` cards absent |
| Implements | `frontend/src/pages/Summaries.tsx` (empty-state branch keyed on the API `not_summarised` status) |
| Depends on | [T8.4](./summariser-G8-T8.4.md), [T7.4](./summariser-G7-T7.4.md) |
