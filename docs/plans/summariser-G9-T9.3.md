# T9.3: The scope composition is retired and the filter matches the full kind value

> - **Gap:** [G9: SessionDetail evaluation — 18-kind filter + summary lineage](./summariser-G9.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T9.2](./summariser-G9-T9.2.md)
> - **Next:** [T9.4](./summariser-G9-T9.4.md)

- [x] **Done**

Filtering is an exact `message_kind === value` predicate over full kind values; the `Scope`/`matchesKindFilter`/`isSubagentKind` composition no longer exists (ADR9.1, supersedes T10.2).

| | |
|--|--|
| Test | `frontend/src/lib/message-kinds.test.ts::filter matches full kind value with no scope composition` (vitest) — filtering `['human','tool_use','subagent-human','subagent-tool_use']` against `tool_use` yields only `['tool_use']` (NOT `subagent-tool_use`), and against `subagent-tool_use` yields only `['subagent-tool_use']` |
| Implements | `frontend/src/lib/message-kinds.ts` (remove `Scope`, `matchesKindFilter`, `isSubagentKind`; rewrite the old scope-composition test cases) |
| Depends on | [T9.1](./summariser-G9-T9.1.md) |
