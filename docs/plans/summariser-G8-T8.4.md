# T8.4: A user deep-links ?path=&grain= and lands on that scope at that grain

> - **Gap:** [G8: Summaries explorer page](./summariser-G8.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T8.3](./summariser-G8-T8.3.md)
> - **Next:** [T8.5](./summariser-G8-T8.5.md)

- [ ] **Done**

`/summaries?path=<encoded>&grain=week` selects the targeted scope and grain on first paint, with the breadcrumb reflecting `path` and the grain selector reflecting `grain` (ADR8.1; defaults omitted from the URL).

| | |
|--|--|
| Test | `frontend/e2e/summaries.spec.ts::deep-link path and grain selects scope and grain` (playwright) — `goto` with the query string, `waitForFunction` until lenses repopulate, assert the deepest `[data-testid="scope-crumb"]` matches the path leaf and `[data-testid="grain-select"]` shows `week` |
| Implements | `frontend/src/pages/Summaries.tsx` (read `?path=`/`?grain=`/`?bucket=` via `useSearchParams`, drive the API query) |
| Depends on | [T8.3](./summariser-G8-T8.3.md) |
