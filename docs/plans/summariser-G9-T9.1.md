# T9.1: A developer sees MSG_KIND_OPTIONS expose all 19 entries

> - **Gap:** [G9: SessionDetail evaluation — 18-kind filter + summary lineage](./summariser-G9.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T9.2](./summariser-G9-T9.2.md)

- [x] **Done**

`MSG_KIND_OPTIONS` lists "All messages" plus the 18 canonical `msg_kind` values (9 base × {main, `subagent-`}), each a valid `MessageKind | ''`. _(tracer bullet)_

| | |
|--|--|
| Test | `frontend/src/lib/message-kinds.test.ts::MSG_KIND_OPTIONS has 19 entries including subagent kinds` (vitest) — assert length 19, first value `''`, the non-empty set equals the 18 `MessageKind` values, and `subagent-thinking`/`subagent-human` present |
| Implements | `frontend/src/lib/message-kinds.ts` `MSG_KIND_OPTIONS` |
| Depends on | — |
