# T9.4: The e2e filter spec covers the 19-option flat dropdown

> - **Gap:** [G9: SessionDetail evaluation — 18-kind filter + summary lineage](./summariser-G9.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T9.3](./summariser-G9-T9.3.md)
> - **Next:** [T9.5](./summariser-G9-T9.5.md)

- [x] **Done**

The dropdown renders 19 `<option>`s with "All messages" first; existing base-kind selections still deep-link via `?msg=`.

| | |
|--|--|
| Test | `frontend/e2e/session-detail-filter.spec.ts::dropdown has all 19 options (All + 18 kinds)` (playwright) — assert option count is 19 (replacing the "10 options" test), first text "All messages"; existing `?msg=human`/`?msg=tool_use` cases still pass |
| Implements | `frontend/e2e/session-detail-filter.spec.ts` (retarget the count assertion) |
| Depends on | [T9.1](./summariser-G9-T9.1.md), [T9.2](./summariser-G9-T9.2.md) |
