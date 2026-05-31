# T2.3: Re-running on unchanged prompts performs zero engine calls

> - **Gap:** [G2: Per-session human-prompt summarisation](./summariser-G2.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T2.2](./summariser-G2-T2.2.md)
> - **Next:** [T2.4](./summariser-G2-T2.4.md)

- [x] **Done**

A session whose concatenated human text yields an unchanged `content_hash` **for the same `model_id`** is skipped — `summarise_session` issues zero engine calls and leaves the existing row intact; the same text under a different `model_id` is a cache miss that writes a new row (ADR2.3).

| | |
|--|--|
| Test | `tests/test_summaries.py::test_unchanged_human_text_skips_engine_per_model` — run once with a call-counting fake engine, then again on the same session+model (assert call count stays 1, row unchanged), then once more with a different model (assert a second row is written) |
| Implements | `src/.../database/sqlite/summaries.py` content-hash guard in `summarise_session` |
| Depends on | [T2.1](./summariser-G2-T2.1.md) |
