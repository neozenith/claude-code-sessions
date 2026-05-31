# T7.2: A user can compose the subagent scope toggle with a kind filter

> - **Gap:** [G7: Frontend surfacing](./tokenometrics-G7.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Prev:** [T7.1](./tokenometrics-G7-T7.1.md)
> - **Next:** [T7.3](./tokenometrics-G7-T7.3.md)

- [x] **Done**

The message-kind helper strips/keeps the `subagent-` prefix so that `?msg=tool_use` matches both `tool_use` and `subagent-tool_use`, while `?scope=subagent` narrows to subagent-prefixed kinds only.

| | |
|--|--|
| Test | `frontend/src/lib/message-kinds.test.ts::subagent scope composes with kind filter` — the predicate over a small event array for `{msg, scope}` combinations |
| Implements | `frontend/src/lib/message-kinds.ts` (scope predicate + prefix-strip), `api-client.ts` (`MessageKind` allows `subagent-${base}`) |
| Depends on | [T3.1](./tokenometrics-G3-T3.1.md) |
