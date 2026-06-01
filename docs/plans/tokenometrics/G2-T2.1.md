# T2.1: A caller can resolve a 1M-window model's context window

> - **Gap:** [G2: Context-window utilization annotations](./tokenometrics-G2.md)
> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Next:** [T2.2](./tokenometrics-G2-T2.2.md)

- [x] **Done**

`context_window("claude-opus-4-7")` returns `1_000_000`.  _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_context_window.py::test_window_1m_models` — `context_window("claude-opus-4-7") == 1_000_000` (and opus-4-6/4-8, sonnet-4-6) |
| Implements | `pricing.py` (`CONTEXT_WINDOWS` map + `context_window`) |
| Depends on | — |
