# T1.2: A depth-1 project yields its root-first ancestor chain

> - **Gap:** [G1: Variable-depth project hierarchy resolution](./summariser-G1.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T1.1](./summariser-G1-T1.1.md)
> - **Next:** [T1.3](./summariser-G1-T1.3.md)

- [ ] **Done**

`ancestor_scopes(resolver, "-Users-testuser-play-foo")` returns `["", "play", "play/foo"]` — every successive home-relative prefix, root (`""`) first, project last, inclusive.

| | |
|--|--|
| Test | `tests/test_project_hierarchy.py::test_ancestor_scopes_depth1_chain` — same fixture as T1.1; assert `ancestor_scopes(...) == ["", "play", "play/foo"]` |
| Implements | `src/claude_code_sessions/project_resolver.py` `ancestor_scopes` |
| Depends on | [T1.1](./summariser-G1-T1.1.md) |
