# G3: Subagent message-kind prefixing

> **[« Tokenometrics index](./tokenometrics.md)**  ·  Gap 3 of 8
>
> **Depends on:** [G1](./tokenometrics-G1.md)  ·  **Blocks:** [G6](./tokenometrics-G6.md), [G8](./tokenometrics-G8.md)
>
> **Nav:** [« G2](./tokenometrics-G2.md)  ·  [G4 »](./tokenometrics-G4.md)

**Current:** `message_kind()` is subagent-blind; 1,335 subagent user prompts are mislabeled `human`. All subagent-file events carry `is_sidechain=1`.

**Gap:** Prefix the derived kind with `subagent-` when the event belongs to a subagent context.

**Output(s):**
- `pricing.py`: `message_kind(event_type, is_meta, content, is_subagent=False)` → `f"subagent-{base}"` when `is_subagent`.
- `cache.py:_parse_event`/`_parse_file`: pass `is_subagent = is_sidechain or file_type in ("subagent","agent_root")`.
- `tests/` coverage in `test_response_dedup.py` or a small `test_msg_kind_subagent.py`.

## ADR: Subagent detection signal
**Decision:** `is_sidechain == 1` OR `source_files.file_type ∈ {subagent, agent_root}` (union).
**Rationale:** `is_sidechain` is per-event and reliable in the data; the file-type union is a belt-and-braces guard against any sidechain event whose flag is missing.

## ADR: Frontend filter representation of subagent kinds
| Option | Pros | Cons |
|--------|------|------|
| Subagent dimension (toggle: All / Main / Subagent) × 9 base kinds | 10 options stay readable; composable | Filter logic composes two params |
| Enumerate 18 kinds in `MSG_KIND_OPTIONS` | No filter-logic change | Doubles the dropdown; noisy |

**Decision:** Subagent dimension — a `?scope=main|subagent` param orthogonal to the existing `?msg=<base kind>`. The dropdown keeps the 9 base kinds; a separate scope toggle composes with it.
**Rationale:** Keeps the kind dropdown readable and the URL state legible (the project already favors clean orthogonal URL params per CLAUDE.md). The base kind is recovered by stripping the `subagent-` prefix when matching, so `?msg=tool_use` matches both main and subagent tool calls unless `?scope=` narrows it.

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); the full Test/Implementation outlines live in the per-ticket files linked below.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T3.1](./tokenometrics-G3-T3.1.md) | A caller gets a subagent-prefixed kind for subagent events | none |
| [T3.2](./tokenometrics-G3-T3.2.md) | An operator sees no bare 'human' kinds in subagent transcripts | [T1.1](./tokenometrics-G1-T1.1.md), [T3.1](./tokenometrics-G3-T3.1.md) |
| [T3.3](./tokenometrics-G3-T3.3.md) | Main-thread human prompts remain unprefixed | [T3.2](./tokenometrics-G3-T3.2.md) |

