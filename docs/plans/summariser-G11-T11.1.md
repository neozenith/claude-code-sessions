# T11.1: Both ingesters report the same SCHEMA_VERSION

> - **Gap:** [G11: Introspect-script parity](./summariser-G11.md)
> - **Index:** [summariser.md](./summariser.md)
> - **Next:** [T11.2](./summariser-G11-T11.2.md)

- [ ] **Done**

The standalone introspect script's `SCHEMA_VERSION` equals `backend schema.SCHEMA_VERSION` after the post-G1–G3 bump (to `"19"`), keeping the migration sentinel in lockstep. _(tracer bullet)_

| | |
|--|--|
| Test | `tests/test_introspect_parity.py::test_schema_version_matches_after_summaries` — assert `introspect.SCHEMA_VERSION == backend_schema.SCHEMA_VERSION` and that it advanced past the pre-summariser `"17"` |
| Implements | `.claude/skills/introspect/scripts/introspect_sessions.py` `SCHEMA_VERSION` (bump to match) |
| Depends on | [T10.8](./summariser-G10-T10.8.md) |
