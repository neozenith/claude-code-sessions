# T2.7: A `summarise sessions` run summarises not-yet-current sessions off ingested data

> - **Gap:** [G2: Per-session human-prompt summarisation](./summariser-G2.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T2.6](./summariser-G2-T2.6.md)

- [x] **Done**

`summarise_sessions(conn, engine, model, scope=None)` — the manual runner behind the CLI — iterates every session ingested to date (optionally filtered to a `scope_path` subtree via G1) and calls `summarise_session`, so a cron-triggered run summarises only the not-yet-current sessions for that model and requires no fresh ingest (ADR2.4 decoupling, ADR2.3 idempotency).

| | |
|--|--|
| Test | `tests/test_summaries.py::test_summarise_sessions_runner_is_incremental_and_scope_filtered` — seed several sessions (some already summarised for the model), run `summarise_sessions` with a call-counting fake engine; assert it calls the engine only for the not-yet-current sessions, and that a `scope='clients'` filter restricts work to that subtree |
| Implements | `src/.../summarise_cli.py` `summarise_sessions` + the `sessions` argparse subcommand |
| Depends on | [T2.1](./summariser-G2-T2.1.md), [T1.2](./summariser-G1-T1.2.md) |
