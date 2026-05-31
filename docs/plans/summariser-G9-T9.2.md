# T9.2: A user selects subagent-thinking and the timeline filters to that kind

> - **Gap:** [G9: SessionDetail evaluation — 18-kind filter + summary lineage](./summariser-G9.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T9.1](./summariser-G9-T9.1.md)
> - **Next:** [T9.3](./summariser-G9-T9.3.md)

- [ ] **Done**

Choosing a `subagent-*` option sets `?msg=<full-kind>` and the timeline keeps only events whose `message_kind` equals that full value (no prefix stripping).

| | |
|--|--|
| Test | `frontend/e2e/session-detail-filter.spec.ts::selecting subagent-thinking filters and round-trips through ?msg=` (playwright) — select `subagent-thinking`, assert URL contains `msg=subagent-thinking` and "events filtered"; reload with that param and assert the dropdown re-reflects the value |
| Implements | `frontend/src/pages/SessionDetail.tsx` `visibleEvents` / `<select data-testid="msg-kind-filter">` |
| Depends on | [T9.1](./summariser-G9-T9.1.md) |
