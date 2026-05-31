# T8.2: ScopeBreadcrumb renders the root→…→project lineage from a scope_path

> - **Gap:** [G8: Summaries explorer page](./summariser-G8.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T8.1](./summariser-G8-T8.1.md)
> - **Next:** [T8.3](./summariser-G8-T8.3.md)

- [ ] **Done**

Given a `scope_path`, `ScopeBreadcrumb` renders one crumb per ancestor segment in order, root first, leaf last.

| | |
|--|--|
| Test | `frontend/src/components/ScopeBreadcrumb.test.ts::renders one crumb per scope_path segment in order` (vitest) — render with a 4-segment path, query `[data-testid="scope-crumb"]`, assert count and text match the segments root→leaf |
| Implements | `frontend/src/components/ScopeBreadcrumb.tsx` (presentational lineage render) |
| Depends on | [T8.1](./summariser-G8-T8.1.md) |
