# T8.3: A user drills down via child links and up via ancestor crumbs

> - **Gap:** [G8: Summaries explorer page](./summariser-G8.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T8.2](./summariser-G8-T8.2.md)
> - **Next:** [T8.4](./summariser-G8-T8.4.md)

- [x] **Done**

Clicking a child-scope link appends its segment to `?path=`; clicking an ancestor crumb truncates `?path=` to that segment — both via `useSearchParams` (page-local).

| | |
|--|--|
| Test | `frontend/src/components/ScopeBreadcrumb.test.ts::ancestor crumb truncates path and child link extends it` (vitest) — render breadcrumb + child list in a `MemoryRouter`, click a child then an ancestor crumb, assert the resulting `?path=` via a router location probe (URL state, not a callback spy) |
| Implements | `frontend/src/components/ScopeBreadcrumb.tsx` (crumb/child `to=` over `?path=`); `frontend/src/lib/api-client.ts` `listScopeChildren` |
| Depends on | [T8.2](./summariser-G8-T8.2.md), [T7.6](./summariser-G7-T7.6.md) |
