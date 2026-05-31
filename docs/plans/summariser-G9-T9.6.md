# T9.6: A user navigates the scope lineage via the ScopeBreadcrumb on SessionDetail

> - **Gap:** [G9: SessionDetail evaluation — 18-kind filter + summary lineage](./summariser-G9.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T9.5](./summariser-G9-T9.5.md)

- [ ] **Done**

SessionDetail mounts the G8 `ScopeBreadcrumb` so the session links up its `scope_path` ancestors to the explorer scope and root summaries (ADR9.2 shared lineage navigation).

| | |
|--|--|
| Test | `frontend/e2e/session-detail-filter.spec.ts::session detail breadcrumb links to the explorer scope` (playwright) — assert the breadcrumb is visible and a crumb's `href` targets the explorer scope route for an ancestor in `scope_path` |
| Implements | `frontend/src/pages/SessionDetail.tsx` (mount `ScopeBreadcrumb`) |
| Depends on | [T9.1](./summariser-G9-T9.1.md), [T8.2](./summariser-G8-T8.2.md) |
