# T2.4: Edited prompts trigger a fresh summary

> - **Gap:** [G2: Per-session human-prompt summarisation](./summariser-G2.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T2.3](./summariser-G2-T2.3.md)
> - **Next:** [T2.5](./summariser-G2-T2.5.md)

- [ ] **Done**

When the human text changes (new/edited `msg_kind='human'` events), the `content_hash` differs and `summarise_session` re-invokes the engine and upserts the refreshed lenses.

| | |
|--|--|
| Test | `tests/test_summaries.py::test_changed_human_text_resummarises` — summarise once, modify a human event, summarise again with a fake engine returning a second distinct payload; assert the row reflects the second payload and `human_event_count` updated |
| Implements | `src/.../database/sqlite/summaries.py` upsert-on-hash-change path in `summarise_session` |
| Depends on | [T2.3](./summariser-G2-T2.3.md) |
