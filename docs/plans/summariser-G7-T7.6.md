# T7.6: A consumer drills the scope trie one level via children listing

> - **Gap:** [G7: Summaries query layer & API](./summariser-G7.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T7.5](./summariser-G7-T7.5.md)
> - **Next:** [T7.7](./summariser-G7-T7.7.md)

- [x] **Done**

`GET /api/summaries/scope/children?path=&days=&project=` returns `200` with the immediate child scopes of `scope_path` (next trie level only), honoring global `days`/`project` filters.

| | |
|--|--|
| Test | `tests/test_summaries_api.py::test_scope_children_returns_next_trie_level` — seed a parent scope with descendants at varying depths, call via `TestClient`, assert only immediate children returned; a second case asserts a `project`/`days` filter narrows the set |
| Implements | `src/.../database/sqlite/backend.py` `list_scope_children`; `src/.../main.py` `GET /api/summaries/scope/children` |
| Depends on | [T7.2](./summariser-G7-T7.2.md), [T1.2](./summariser-G1-T1.2.md) |
