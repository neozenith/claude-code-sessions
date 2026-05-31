# T11.4: Both ingesters derive the same scope_path/ancestor set for a shared fixture

> - **Gap:** [G11: Introspect-script parity](./summariser-G11.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Prev:** [T11.3](./summariser-G11-T11.3.md)

- [ ] **Done**

The introspect script's mirrored hierarchy derivation produces the same `scope_path`/`scope_depth` values (and therefore the same roll-up node set) as the backend for fixture sessions spanning nested domains.

| | |
|--|--|
| Test | `tests/test_introspect_parity.py::test_scope_path_derivation_agrees` — ingest a fixture with nested-domain projects (e.g. `clients/acme/app`) into both caches and assert the distinct `(scope_path, scope_depth)` set from `rollup_summaries` is identical |
| Implements | `.claude/skills/introspect/scripts/introspect_sessions.py` mirrored `scope_path_of`/`ancestor_scopes` logic (matching G1) |
| Depends on | [T11.3](./summariser-G11-T11.3.md), [T1.2](./summariser-G1-T1.2.md) |
