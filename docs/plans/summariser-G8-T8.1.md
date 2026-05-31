# T8.1: A user opens /summaries and sees the three lenses for the default scope

> - **Gap:** [G8: Summaries explorer page](./summariser-G8.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T8.2](./summariser-G8-T8.2.md)

- [ ] **Done**

Navigating to `/summaries` mounts the route, calls `getScopeSummary` against the G7 API, and renders all three lens cards for the default (root) scope. _(tracer bullet)_

| | |
|--|--|
| Test | `frontend/e2e/summaries.spec.ts::summaries page renders the three lenses` (playwright) — `goto('/summaries')`, `waitForFunction` on body text `Summaries`, assert `[data-testid="lens-task"]`, `[data-testid="lens-patterns"]`, `[data-testid="lens-decisions"]` visible |
| Implements | `frontend/src/pages/Summaries.tsx` (shell + route in `App.tsx` + nav in `Layout.tsx`); `frontend/src/lib/api-client.ts` `getScopeSummary` |
| Depends on | [T7.1](./summariser-G7-T7.1.md) |
