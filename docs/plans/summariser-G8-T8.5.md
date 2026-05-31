# T8.5: A user switches ?strategy=/?model= and the displayed variant changes

> - **Gap:** [G8: Summaries explorer page](./summariser-G8.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T8.4](./summariser-G8-T8.4.md)
> - **Next:** [T8.6](./summariser-G8-T8.6.md)

- [ ] **Done**

With the eval selector present, changing `?strategy=`/`?model=` fetches that variant and swaps the prose shown in the lens cards (ADR7.2 eval-aware viewers).

| | |
|--|--|
| Test | `frontend/e2e/summaries.spec.ts::strategy/model selector switches the displayed variant` (playwright) — load `/summaries?path=<encoded>`, capture lens-task text, change `[data-testid="strategy-select"]`/`[data-testid="model-select"]`, `waitForFunction` until the text differs, assert the URL carries the new params and the prose changed |
| Implements | `frontend/src/pages/Summaries.tsx` (eval selector); `frontend/src/lib/api-client.ts` `listSummaryVariants` |
| Depends on | [T8.4](./summariser-G8-T8.4.md), [T7.7](./summariser-G7-T7.7.md) |
