# T1.1: A depth-1 project resolves its home-relative scope path

> - **Gap:** [G1: Variable-depth project hierarchy resolution](./summariser-G1.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T1.2](./summariser-G1-T1.2.md)

- [x] **Done**

`scope_path_of(resolver, "-Users-testuser-play-foo")` returns `"play/foo"` — the `/`-joined home-relative path drawn from the project's authoritative `ProjectInfo.project_path` (`/Users/testuser/play/foo`), home being `/Users/testuser`. _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_project_hierarchy.py::test_scope_path_of_depth1_project` — build a `ProjectResolver` over a `tmp_path` projects dir containing `-Users-testuser-play-foo/sessions-index.json` with `projectPath: /Users/testuser/play/foo`; assert `scope_path_of(...) == "play/foo"` |
| Implements | `src/claude_code_sessions/project_resolver.py` `scope_path_of` |
| Depends on | — |
