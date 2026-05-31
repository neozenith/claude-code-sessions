# T9.5: A user sees the session's 3-lens summary card on SessionDetail

> - **Gap:** [G9: SessionDetail evaluation — 18-kind filter + summary lineage](./summariser-G9.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T9.4](./summariser-G9-T9.4.md)
> - **Next:** [T9.6](./summariser-G9-T9.6.md)

- [x] **Done**

SessionDetail renders a summary card showing the session's three summary lenses, sourced from the G7 session-summary API — so the evaluator reads the summary next to the prompts that produced it.

| | |
|--|--|
| Test | `frontend/e2e/session-detail-filter.spec.ts::session detail shows the 3-lens summary card` (playwright) — navigate to the session, assert `[data-testid="session-summary-card"]` is visible with all three lens sections in the DOM |
| Implements | `frontend/src/pages/SessionDetail.tsx` (summary card mount); `frontend/src/lib/api-client.ts` `getSessionSummary` |
| Depends on | [T9.1](./summariser-G9-T9.1.md), [T7.1](./summariser-G7-T7.1.md) |
