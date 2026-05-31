# T2.2: Only the developer's typed prompts reach the summarisation engine

> - **Gap:** [G2: Per-session human-prompt summarisation](./summariser-G2.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T2.1](./summariser-G2-T2.1.md)
> - **Next:** [T2.3](./summariser-G2-T2.3.md)

- [x] **Done**

The text handed to the engine is exactly the concatenation of `msg_kind='human'` events, excluding `subagent-*`, `assistant`, `tool`, `meta`, and `user_text` (ADR2.2).

| | |
|--|--|
| Test | `tests/test_summaries.py::test_only_human_kind_text_is_summarised` — seed a session mixing `human`, `user_text`, `assistant`, `tool`, `subagent-*` with distinctive markers; the fake engine records its prompt; assert the prompt contains the `human` markers and none of the excluded-kind markers |
| Implements | `src/.../database/sqlite/summaries.py` `summarise_session` (human-text gather query) |
| Depends on | [T2.1](./summariser-G2-T2.1.md) |
