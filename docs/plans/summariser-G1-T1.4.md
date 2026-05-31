# T1.4: A dashed segment resolves via the authoritative path, not id-split

> - **Gap:** [G1: Variable-depth project hierarchy resolution](./summariser-G1.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T1.3](./summariser-G1-T1.3.md)

- [x] **Done**

For `project_id == "-Users-testuser-play-claude-code-sessions"` whose authoritative `projectPath` is `/Users/testuser/play/claude-code-sessions`, `ancestor_scopes(...)` returns `["", "play", "play/claude-code-sessions"]` — the dashed segment stays one segment, proving derivation from `project_path` not from splitting the dash-encoded id.

| | |
|--|--|
| Test | `tests/test_project_hierarchy.py::test_dashed_segment_uses_authoritative_path_not_id_split` — fixture `sessions-index.json` with `projectPath: /Users/testuser/play/claude-code-sessions`; assert the dashed segment is one scope, not three |
| Implements | `src/claude_code_sessions/project_resolver.py` `scope_path_of`, `ancestor_scopes` |
| Depends on | [T1.3](./summariser-G1-T1.3.md) |
