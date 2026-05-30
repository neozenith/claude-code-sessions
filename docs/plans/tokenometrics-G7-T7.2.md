# T7.2: A user can compose the subagent scope toggle with a kind filter

> **[« G7: Frontend surfacing](./tokenometrics-G7.md)**  ·  [Tokenometrics index](./tokenometrics.md)  ·  Ticket 2 of 4 in G7
>
> **Nav:** [« T7.1](./tokenometrics-G7-T7.1.md)  ·  [T7.3 »](./tokenometrics-G7-T7.3.md)


- [x] **Done**
- **Cycle:** RED → GREEN
- **Behavior:** The message-kind helper strips/keeps the `subagent-` prefix so that `?msg=tool_use` matches both `tool_use` and `subagent-tool_use`, while `?scope=subagent` narrows to subagent-prefixed kinds only.
- **Test outline:**
  - File: `frontend/src/lib/message-kinds.test.ts`
  - Name: `subagent scope composes with kind filter`
  - Asserts: the predicate over a small event array for `{msg, scope}` combinations.
- **Implementation outline:**
  - File(s): `frontend/src/lib/message-kinds.ts` (scope predicate + prefix-strip), `api-client.ts` (`MessageKind` allows `subagent-${base}`).
- **Mocks:** `none`
- **Depends on:** [T3.1](./tokenometrics-G3-T3.1.md)
