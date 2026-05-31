# T1.3: A depth-2 project yields a four-level ancestor chain

> - **Gap:** [G1: Variable-depth project hierarchy resolution](./summariser-G1.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T1.2](./summariser-G1-T1.2.md)
> - **Next:** [T1.4](./summariser-G1-T1.4.md)

- [x] **Done**

`ancestor_scopes(resolver, "-Users-testuser-clients-acme-app")` returns `["", "clients", "clients/acme", "clients/acme/app"]` — the variable-depth rule produces one scope per path segment for a deeper branch.

| | |
|--|--|
| Test | `tests/test_project_hierarchy.py::test_ancestor_scopes_depth2_clients_chain` — projects dir contains `-Users-testuser-clients-acme-app/sessions-index.json` with `projectPath: /Users/testuser/clients/acme/app`; assert the four-level chain |
| Implements | `src/claude_code_sessions/project_resolver.py` `ancestor_scopes` |
| Depends on | [T1.2](./summariser-G1-T1.2.md) |
