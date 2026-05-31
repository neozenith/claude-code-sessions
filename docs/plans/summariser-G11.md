# G11: Introspect-script parity

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** [G10](./summariser-G10.md) — mirrors the collapsed G1–G3 pipeline that exists only post-gate
> - **Blocks:** none
> - **Prev:** [G10](./summariser-G10.md)

Mirrors every schema and summarisation change into the standalone introspect script so both ingesters write byte-identical summary rows and report the same `SCHEMA_VERSION`. Conditional on the [G10](./summariser-G10.md) gate returning PROCEED — it mirrors the *collapsed* single-strategy pipeline, not the three benchmark variants.

## Context
`.claude/skills/introspect/scripts/introspect_sessions.py` is a PEP-723 standalone tool that cannot import from `src/`; it hardcodes `SCHEMA_VERSION` and its own pricing/parse copies, kept in parity by manual review (tokenometrics G8 precedent — the same shared cache file, the same migration sentinel pattern).
Whatever G1–G3 add to schema + summarisation must be reproduced here, targeting the **single production merge strategy + model** chosen at the [G10](./summariser-G10.md) decision gate (not all three benchmark variants).

## Outputs
| File | Change |
|------|--------|
| `.claude/skills/introspect/scripts/introspect_sessions.py` (py) | Mirror the `session_summaries` + `rollup_summaries` schema, the `domain_of` logic, and the `muninn_chat` summarisation/roll-up passes for the winning strategy; bump its `SCHEMA_VERSION` to match. |
| `tests/` (py) | Parity test: both ingesters produce identical summary rows for a shared fixture and report the same `SCHEMA_VERSION`. |

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T11.1](./summariser-G11-T11.1.md) | Both ingesters report the same SCHEMA_VERSION _(tracer)_ | [T10.8](./summariser-G10-T10.8.md) |
| [T11.2](./summariser-G11-T11.2.md) | Both ingesters produce identical session_summaries rows for a shared fixture | [T11.1](./summariser-G11-T11.1.md), [T2.1](./summariser-G2-T2.1.md) |
| [T11.3](./summariser-G11-T11.3.md) | Both ingesters produce identical rollup_summaries rows (production strategy) | [T11.2](./summariser-G11-T11.2.md), [T3.1](./summariser-G3-T3.1.md) |
| [T11.4](./summariser-G11-T11.4.md) | Both ingesters derive the same scope_path/ancestor set | [T11.3](./summariser-G11-T11.3.md), [T1.2](./summariser-G1-T1.2.md) |
