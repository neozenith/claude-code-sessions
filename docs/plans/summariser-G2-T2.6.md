# T2.6: The production engine drives muninn_chat with the configured model name

> - **Gap:** [G2: Per-session human-prompt summarisation](./summariser-G2.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T2.5](./summariser-G2-T2.5.md)
> - **Next:** [T2.7](./summariser-G2-T2.7.md)

- [ ] **Done**

The production `MuninnSummaryEngine.summarise(model, prompt)` issues `muninn_chat(model_name, prompt)` against the connection, passing the model name through as the first argument (ADR2.1 engine-interface contract).

| | |
|--|--|
| Test | `tests/test_summaries.py::test_muninn_engine_passes_model_name_to_chat` — register a fake SQL function named `muninn_chat` on a fixture connection that records its `(model_name, prompt)` args; call the production engine's public `summarise`; assert the recorded first arg equals the model name and the prompt is forwarded verbatim |
| Implements | `src/.../database/sqlite/summaries.py` `MuninnSummaryEngine.summarise` |
| Depends on | [T2.1](./summariser-G2-T2.1.md) |
| Mocks | `muninn_chat` — the sqlite-muninn system boundary, stubbed as a registered SQL function on the test connection (boundary mock, permitted) |
