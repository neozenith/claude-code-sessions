# G3: Subagent message-kind prefixing

> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Depends on:** [G1](./tokenometrics-G1.md)
> - **Blocks:** [G6](./tokenometrics-G6.md), [G8](./tokenometrics-G8.md)
> - **Prev:** [G2](./tokenometrics-G2.md)
> - **Next:** [G4](./tokenometrics-G4.md)

Prefix the derived `msg_kind` with `subagent-` when the event belongs to a subagent context, so subagent prompts stop masquerading as `human`.

## Context

`message_kind()` is subagent-blind:
1,335 subagent user prompts are mislabeled `human`.
All subagent-file events carry `is_sidechain=1`.

## Outputs

| File | Change |
|------|--------|
| `pricing.py` | `message_kind(..., is_subagent=False)` → `f"subagent-{base}"` when set |
| `cache.py:_parse_event` / `_parse_file` | pass `is_subagent = is_sidechain or file_type in {"subagent","agent_root"}` |
| `tests/test_msg_kind_subagent.py` | prefix applied / not applied |

## ADR3.1: Detect subagents by sidechain or file type

- **Decision:** treat an event as subagent when `is_sidechain == 1` **or** `source_files.file_type ∈ {subagent, agent_root}`.
- **Why:** `is_sidechain` is per-event and reliable; the file-type union guards any sidechain event whose flag is missing.

## ADR3.2: Subagent scope is a separate filter param

- **Decision:** add a `?scope=main|subagent` param orthogonal to the existing `?msg=<base kind>`; the dropdown keeps the 9 base kinds.
- **Why:** keeps the dropdown readable and the URL legible; the base kind is recovered by stripping the `subagent-` prefix, so `?msg=tool_use` matches both scopes unless `?scope=` narrows it.
- **Rejected:** enumerating 18 kinds in the dropdown (doubles it; noisy).

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); full outlines live in the linked files.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T3.1](./tokenometrics-G3-T3.1.md) | A caller gets a subagent-prefixed kind for subagent events | — |
| [T3.2](./tokenometrics-G3-T3.2.md) | An operator sees no bare 'human' kinds in subagent transcripts | [T1.1](./tokenometrics-G1-T1.1.md), [T3.1](./tokenometrics-G3-T3.1.md) |
| [T3.3](./tokenometrics-G3-T3.3.md) | Main-thread human prompts remain unprefixed | [T3.2](./tokenometrics-G3-T3.2.md) |
