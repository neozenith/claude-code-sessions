# Tokenometrics: Performance, Idle Time & Context-Window Analytics

<!-- VERIFICATION: Claude 4.6/4.7/4.8 + Sonnet 4.6 window figures postdate the model knowledge cutoff and are sourced from live vendor docs; independently corroborated by observed occupancy (opus-4-7 reached ~1M, sonnet/opus-4-5/haiku stayed <200k — see Current State). No LINK_NOT_VERIFIED markers remain. NOTE: zone-labeling (smart/caution/danger) was dropped per the G2 ADR "Quantitative ratio only"; context utilization is exposed as the raw context_ratio. -->

---

<details>
<summary><b>Table of Contents</b></summary>
<!--TOC-->

- [Tokenometrics: Performance, Idle Time & Context-Window Analytics](#tokenometrics-performance-idle-time--context-window-analytics)
  - [Execution Plan](#execution-plan)
    - [Loop Runner Prompt](#loop-runner-prompt)
    - [Progress](#progress)
    - [Done Criteria](#done-criteria)
  - [Overview](#overview)
  - [Current State](#current-state)
  - [Desired State](#desired-state)
  - [Gap Analysis](#gap-analysis)
    - [Gap Map](#gap-map)
    - [Dependencies](#dependencies)
    - [Gaps (detailed specs)](#gaps-detailed-specs)
  - [Success Measures](#success-measures)
    - [Project Quality Bar (CI Gates)](#project-quality-bar-ci-gates)
    - [Domain-Specific Measures](#domain-specific-measures)
  - [Negative Measures](#negative-measures)
    - [Quality Bar Violations](#quality-bar-violations)
    - [Domain-Specific Failures](#domain-specific-failures)

<!--TOC-->
</details>

---

## Execution Plan

### Loop Runner Prompt

```
/loop Read the gap analysis spec at docs/plans/tokenometrics.md.

1. Read `.claude/skills/plan-gap/resources/tdd/tdd.md` and apply its red-green-refactor workflow.
2. Find the next ticket whose status is `[ ]` and whose `Depends on` are all `[x]`.
   If none exists, write "spec complete" and exit the loop.
3. RED — write the test described in the ticket's `Test outline`. Run the test
   suite. Confirm the new test fails.
4. GREEN — write the minimum code described in `Implementation outline`. Run the
   test suite. Confirm the new test passes and no existing tests regressed.
5. REFACTOR (optional) — apply the ticket's `Refactor candidates` while staying
   green. Re-run the test suite after each refactor step.
6. Mark the ticket's status checkbox `[x]` in docs/plans/tokenometrics.md.
7. Update the Progress table in the Execution Plan section.
8. Commit the changes with message `T<N>.<M>: <ticket title>`.
9. Return — the loop will fire again for the next eligible ticket.

If you encounter an ambiguity that the spec does not resolve, STOP the loop:
add an `<!-- UNRESOLVED -->` ADR placeholder under the relevant `G<N>`,
write a short status note explaining what blocked progress, and exit.
The user must re-enter Phase 2 refinement to resolve the ADR before the
loop can resume.
```

> **Note for the runner:** G1's schema change bumps `SCHEMA_VERSION` to `"14"`. After the G1 tickets land, a full reingest is required before G4–G8 integration tickets will see populated columns (delete `~/.claude/cache/introspect_sessions.db` or let `ensure_cache` DROP+recreate). Backend ticket tests should build a tiny fixture cache rather than depend on the 2 GB production DB.

### Progress

| Gap | Tickets total | `[x]` done | `[ ]` todo | Next eligible | Blocked on |
|-----|---------------|-----------|-----------|---------------|------------|
| [G1](./tokenometrics-G1.md) | 4 | 4 | 0 | — _(done)_ | — |
| [G2](./tokenometrics-G2.md) | 6 | 4 | 2 | [T2.4](./tokenometrics-G2-T2.4.md) | — |
| [G3](./tokenometrics-G3.md) | 3 | 0 | 3 | [T3.1](./tokenometrics-G3-T3.1.md) | — |
| [G4](./tokenometrics-G4.md) | 2 | 0 | 2 | [T4.1](./tokenometrics-G4-T4.1.md) | — |
| [G5](./tokenometrics-G5.md) | 4 | 0 | 4 | — | [T4.1](./tokenometrics-G4-T4.1.md) |
| [G6](./tokenometrics-G6.md) | 3 | 0 | 3 | — | [T1.1](./tokenometrics-G1-T1.1.md), [T2.6](./tokenometrics-G2-T2.6.md), [T3.2](./tokenometrics-G3-T3.2.md), [T5.1](./tokenometrics-G5-T5.1.md) |
| [G7](./tokenometrics-G7.md) | 4 | 1 | 3 | — | [T3.1](./tokenometrics-G3-T3.1.md), [T6.1](./tokenometrics-G6-T6.1.md), [T6.2](./tokenometrics-G6-T6.2.md) |
| [G8](./tokenometrics-G8.md) | 1 | 0 | 1 | — | [T1.1](./tokenometrics-G1-T1.1.md), [T2.6](./tokenometrics-G2-T2.6.md), [T3.2](./tokenometrics-G3-T3.2.md), [T4.1](./tokenometrics-G4-T4.1.md) |

**Dropped tickets** (counted as `[x]`, no work required): **T2.5** — the smart/caution/danger zone classifier and its absolute-token override were removed per the G2 ADR "Quantitative ratio only"; **T7.1** — the frontend zone classifier is likewise unnecessary. Context utilization is exposed as the raw `context_ratio` everywhere.

"Next eligible" = lowest-numbered `[ ]` ticket whose `Depends on` are all `[x]`. The leaf tracer bullets (no deps) are **[T1.1](./tokenometrics-G1-T1.1.md), [T2.1](./tokenometrics-G2-T2.1.md), [T3.1](./tokenometrics-G3-T3.1.md)** — any is a valid starting point; [T1.1](./tokenometrics-G1-T1.1.md) is recommended first since the most gaps transitively depend on it.

### Done Criteria

- [ ] Every ticket in every `G<N>` is marked `[x]`
- [ ] Every Success Measure (Project Quality Bar + Domain-Specific) passes when executed (commands listed in the Success Measures table)
- [ ] No `<!-- UNRESOLVED -->` ADR markers remain
- [ ] No `<!-- LINK_NOT_VERIFIED -->`, `<!-- ASSUMPTION -->`, or `<!-- PAYWALLED -->` markers requiring user resolution

## Overview

This initiative derives new analytics from Claude Code session JSONL logs, surfaced through the existing FastAPI + SQLite + React dashboard:

1. **Tokens/sec (TPS)** — model *performance*: a response's output tokens ÷ that response's own generation duration.
2. **Idle / active time** — the call-and-response delay between the assistant yielding the turn and the human's next prompt, plus the inverse "active/working" time, plus a flag for "responded implausibly fast to have read the output."
3. **Context-window utilization ratio (normalized)** — how full the model's context window is at each response, normalized per model (200k / 1M / 32k locals), exposed as a raw quantitative ratio (no categorical zone labeling).
4. **Accurate per-event accumulation** — annotate each event with its live context occupancy and the ratio of the model's window budget it represents.
5. **Subagent labeling** — prefix every `msg_kind` with `subagent-` when the event belongs to a subagent context.

Investigating the real cache (`~/.claude/cache/introspect_sessions.db`, 2 GB) surfaced a **prerequisite correctness bug**: the cache over-counts every token measure ~2.4× because each model response is logged as many content-block events that all repeat the same request-level usage, and the rollups `SUM()` them without deduping. Fixing this is the foundation the new metrics build on.

**Gaps identified:**

- **[G1: Response-level token accounting](./tokenometrics-G1.md)** — dedupe per `requestId`; zero duplicated usage so all existing totals/costs become accurate.
- **[G2: Context-window utilization annotations](./tokenometrics-G2.md)** — curated `model_id → window` map; per-event `context_tokens` / `context_window` / `context_ratio`.
- **[G3: Subagent message-kind prefixing](./tokenometrics-G3.md)** — `subagent-<kind>` when the event is in a subagent context.
- **[G4: Response performance (TPS)](./tokenometrics-G4.md)** — per-response `response_duration_ms` + derived tokens/sec on response heads.
- **[G5: Turn timing (idle / active)](./tokenometrics-G5.md)** — call-and-response decomposition + "too-fast reply" flag, session rollups.
- **[G6: Query layer & API endpoints](./tokenometrics-G6.md)** — expose new fields; `get_session_metrics` + `get_performance_summary`.
- **[G7: Frontend surfacing](./tokenometrics-G7.md)** — SessionDetail occupancy/TPS/idle, new Performance page, sessions-list columns, subagent filter.
- **[G8: Introspect-script parity](./tokenometrics-G8.md)** — mirror all ingestion changes in the standalone introspect script that shares the schema.

```mermaid
flowchart LR
    G1["G1 Response<br/>dedup"] --> G2["G2 Context<br/>annotations"]
    G1 --> G3["G3 Subagent<br/>prefix"]
    G1 --> G4["G4 TPS"]
    G4 --> G5["G5 Idle/<br/>active"]
    G1 --> G6
    G2 --> G6["G6 Query +<br/>API"]
    G3 --> G6
    G5 --> G6
    G6 --> G7["G7 Frontend"]
    G1 -.parity.-> G8["G8 Introspect<br/>script"]
    G2 -.parity.-> G8
    G3 -.parity.-> G8
    G4 -.parity.-> G8
    G5 -.parity.-> G8
    classDef gap fill:#2563eb,color:#fff;
    classDef parity fill:#7c3aed,color:#fff;
    class G1,G2,G3,G4,G5,G6,G7 gap
    class G8 parity
```

## Current State

The dashboard ingests `~/.claude/projects/**/*.jsonl` into a cached SQLite index. Ingestion is a wave pipeline (`database/sqlite/wave_pipeline.py`) driving a `ParallelIngester` (`parallel_ingester.py`): worker threads parse files (`CacheManager._parse_file` → `_parse_event`, `cache.py:254`/`:445`) and a single writer thread inserts rows (`_write_parsed`, `cache.py:298`). Costs/classification live in `database/sqlite/pricing.py`. Rollups (`rebuild_aggregates`, `cache.py:695`) and the `agg` star-schema feed the API (`database/sqlite/backend.py`, contract in `database/protocol.py`, routes in `main.py`). The React app (`frontend/src/`) reads typed endpoints via `lib/api-client.ts`.

**Key facts established by investigating the real data:**

- A single model response (one `requestId`) is logged as **N content-block events** (1 thinking + 1 text + many tool_use). **Every block repeats the same** `output_tokens` / `input_tokens` / `cache_read_input_tokens` / `cache_creation_input_tokens`. Verified on the largest session file: naive per-event `SUM(output_tokens)` = **8,439,850** vs requestId-deduped = **3,462,111** (≈2.44× inflation). `rebuild_aggregates` (`cache.py:719-720`) and the `agg` table sum per event with no dedup, so **all dashboard token + cost totals are inflated**.
- For an assistant event, `input_tokens + cache_read_tokens + cache_creation_tokens` **is** the live context-window occupancy (the full prompt sent), constant across a requestId's blocks. No occupancy field, ratio, or per-model window exists anywhere today.
- Observed max occupancy per model: `opus-4-7` 999,948 and `opus-4-6` 970,536 (1M windows), while `sonnet-4-5/4-6`, `opus-4-5`, `haiku-4-5` all stay under ~200k — empirical corroboration that the window is a per-model constant.
- `msg_kind` is derived by `message_kind(event_type, is_meta, content)` (`pricing.py:64`) into 9 kinds with no subagent awareness. **1,335 events** living in subagent / `agent_root` files are currently classed `human` (plus 16 `user_text`) — the mislabel bug. All such events carry `is_sidechain=1`.
- There is **no per-assistant `durationMs`** in the JSONL (only on hook/system events), so response duration must be derived from event timestamps.

```mermaid
flowchart TD
    JSONL["JSONL lines<br/>(N blocks per response,<br/>usage duplicated)"] --> PE["_parse_event<br/>cache.py:445"]
    PE --> PF["_parse_file<br/>ordered list"]
    PF --> PI["ParallelIngester<br/>writer thread"]
    PI --> EV[("events table<br/>per-block rows,<br/>duplicated usage")]
    EV --> RB["rebuild_aggregates<br/>SUM() no dedup"]
    RB --> SESS[("sessions / agg<br/>INFLATED ~2.4x")]
    SESS --> API["backend.py / main.py"]
    API --> FE["React dashboard<br/>(inflated costs,<br/>no TPS/idle/context)"]
    classDef problem fill:#b91c1c,color:#fff;
    class EV,SESS problem
```

## Desired State

A response-aware ingestion pass corrects the counts and annotates each event, new query methods expose the metrics, and the frontend surfaces them.

- Ingestion gains a per-file post-pass `_annotate_responses` that groups assistant events by `requestId`, marks one **head** per response, **zeroes the duplicated usage on non-heads** (so every existing `SUM()` is correct with no query rewrites), and stamps `response_duration_ms` on the head.
- Each event carries `context_tokens`, `context_window` (from a curated map), and `context_ratio`. Subagent events carry `subagent-<kind>` msg_kinds.
- New `sessions` rollups (`avg_tps`, `total_idle_ms`, `total_active_ms`, `peak_context_ratio`, …) and two new endpoints: per-session turn metrics and a cross-session performance summary.
- Frontend: per-event context-occupancy bar + TPS + idle markers in SessionDetail, a new **Performance** page (TPS by model, context-utilization ratio histogram, idle/active split), sessions-list columns, and a subagent dimension on the message-kind filter.

```mermaid
flowchart TD
    JSONL["JSONL lines"] --> PE["_parse_event<br/>+ request_id, stop_reason,<br/>context_tokens/window/ratio,<br/>subagent- prefix"]
    PE --> PF["_parse_file"]
    PF --> AR["_annotate_responses<br/>group by requestId →<br/>mark head, zero dups,<br/>response_duration_ms"]
    AR --> PI["ParallelIngester writer"]
    PI --> EV[("events table<br/>+7 columns,<br/>accurate per-head usage")]
    EV --> RB["rebuild_aggregates<br/>+ _compute_session_timing<br/>(LEAD window)"]
    RB --> SESS[("sessions / agg<br/>ACCURATE + timing rollups")]
    SESS --> API["backend.py / main.py<br/>+ /metrics + /performance"]
    API --> FE["SessionDetail (occupancy/TPS/idle)<br/>+ Performance page<br/>+ sessions columns"]
    classDef good fill:#166534,color:#fff;
    classDef process fill:#7c3aed,color:#fff;
    class EV,SESS good
    class AR process
```

## Gap Analysis

### Gap Map

```mermaid
flowchart TD
    subgraph Current
        C1["Duplicated per-block<br/>usage, inflated SUMs"]
        C2["No context occupancy<br/>or window concept"]
        C3["msg_kind subagent-blind<br/>(1,335 mislabeled)"]
        C4["No response duration<br/>/ TPS"]
        C5["No idle/active timing"]
        C6["Endpoints lack new fields"]
        C7["UI: inflated costs,<br/>no perf views"]
        C8["Introspect script shares<br/>schema, own parse copy"]
    end
    subgraph Gaps
        GA1["G1 dedup +<br/>zero non-heads"]
        GA2["G2 context map +<br/>ratio columns"]
        GA3["G3 subagent- prefix"]
        GA4["G4 response_duration_ms<br/>+ TPS"]
        GA5["G5 LEAD timing +<br/>too-fast flag"]
        GA6["G6 queries + 2 endpoints"]
        GA7["G7 frontend"]
        GA8["G8 parity"]
    end
    subgraph Desired
        D1["Accurate totals/costs"]
        D2["Per-event context ratio"]
        D3["Correct human vs subagent"]
        D4["Per-response TPS"]
        D5["Call-and-response analytics"]
        D6["Typed metrics API"]
        D7["Performance dashboard"]
        D8["Both ingesters agree"]
    end
    C1 --> GA1 --> D1
    C2 --> GA2 --> D2
    C3 --> GA3 --> D3
    C4 --> GA4 --> D4
    C5 --> GA5 --> D5
    C6 --> GA6 --> D6
    C7 --> GA7 --> D7
    C8 --> GA8 --> D8
    classDef cur fill:#b91c1c,color:#fff;
    classDef gap fill:#2563eb,color:#fff;
    classDef des fill:#166534,color:#fff;
    class C1,C2,C3,C4,C5,C6,C7,C8 cur
    class GA1,GA2,GA3,GA4,GA5,GA6,GA7,GA8 gap
    class D1,D2,D3,D4,D5,D6,D7,D8 des
```

*Detail-density diagram (24 nodes — one current→gap→desired triple per gap; high preset). Gap-to-gap ordering is intentionally omitted here and shown in the Dependencies diagram below.*

### Dependencies

```mermaid
flowchart LR
    G1 --> G2
    G1 --> G3
    G1 --> G4
    G4 --> G5
    G1 --> G6
    G2 --> G6
    G3 --> G6
    G5 --> G6
    G6 --> G7
    G1 -.parity.-> G8
    G2 -.parity.-> G8
    G3 -.parity.-> G8
    G4 -.parity.-> G8
    G5 -.parity.-> G8
    classDef gap fill:#2563eb,color:#fff;
    classDef parity fill:#7c3aed,color:#fff;
    class G1,G2,G3,G4,G5,G6,G7 gap
    class G8 parity
```

**Recommended implementation order:** G1 (foundation: schema bump + dedup + reingest) → G2, G3, G4 in parallel (all ride the same ingestion change) → G5 (needs G4's duration/heads) → G6 (queries over the new columns) → G7 (frontend) → G8 (introspect-script parity, mirrors G1–G5). G1's schema-version bump forces a single full reingest of the 2 GB corpus that G2–G5 piggyback on, so they should land together before the reingest.

---

### Gaps (detailed specs)

Each gap is split into its own spec file with full **Current / Gap / Output(s) / References / ADRs / Tickets**. Dependency ordering is shown in the [Dependencies](#dependencies) diagram above; each spec header also links to the gaps it depends on and blocks.

| Gap | Spec | Tickets | Summary |
|-----|------|:-------:|---------|
| G1 | [Response-level token accounting](./tokenometrics-G1.md) | 4 | Dedupe per `requestId`; zero duplicated usage so all existing totals/costs become accurate. |
| G2 | [Context-window utilization annotations](./tokenometrics-G2.md) | 6 | Curated `model_id → window` map; per-event occupancy + normalized context ratio (raw quantitative, no zone labels). |
| G3 | [Subagent message-kind prefixing](./tokenometrics-G3.md) | 3 | `subagent-<kind>` prefix whenever the event belongs to a subagent context. |
| G4 | [Response performance (TPS)](./tokenometrics-G4.md) | 2 | Per-response `response_duration_ms` + derived tokens/sec on response heads. |
| G5 | [Turn timing (idle / active)](./tokenometrics-G5.md) | 4 | Idle/active call-and-response decomposition + a too-fast-reply flag. |
| G6 | [Query layer & API endpoints](./tokenometrics-G6.md) | 3 | Expose the new fields; add `get_session_metrics` + `get_performance_summary` endpoints. |
| G7 | [Frontend surfacing](./tokenometrics-G7.md) | 4 | SessionDetail occupancy/TPS/idle, a Performance page, sessions-list columns, subagent filter. |
| G8 | [Introspect-script parity](./tokenometrics-G8.md) | 1 | Mirror every ingestion change in the standalone introspect script that shares the schema. |

## Success Measures

### Project Quality Bar (CI Gates)

| Gate | Command | Threshold | Applies to |
|------|---------|-----------|------------|
| Types (Py) | `make typecheck` (mypy strict) | 0 errors | all `src/` + `tests/` changes |
| Types (TS) | `tsc` (via `make typecheck`) | 0 errors | all `frontend/src/` changes |
| Lint | `make lint` (ruff + eslint) | 0 errors | all changes |
| Format | `make format` (ruff) | clean | all Python |
| Backend tests | `make test-backend` (pytest) | pass | G1–G6, G8 |
| Frontend unit | `make test-frontend` (vitest) | pass | G7 |
| E2E | `make test-frontend-e2e` (playwright) | pass | G7 |
| Full gate | `make ci` | green | the whole initiative |

### Domain-Specific Measures

- **[G1](./tokenometrics-G1.md):** For the known sample file, post-reingest `SUM(output_tokens)` over a session equals the requestId-deduped value (≈8.44M → 3.46M); exactly one `is_response_head=1` per `requestId`.
- **[G2](./tokenometrics-G2.md):** `context_window('claude-opus-4-7')==1_000_000`, `('claude-sonnet-4-5-...')==200_000`, `('qwen2.5-coder-7b-instruct')==32_768`, `('<synthetic>')` is `None`; `context_ratio(tokens, window)` returns the raw fraction `tokens/window` ∈ (0,1] for known windows and `None` for an unknown window. No categorical zone labeling exists (dropped per the G2 ADR "Quantitative ratio only").
- **[G3](./tokenometrics-G3.md):** Zero events in subagent/`agent_root` files retain a bare `human`/`user_text` kind; all are `subagent-*`.
- **[G4](./tokenometrics-G4.md):** `tps` is `None` when `response_duration_ms` is 0/NULL, else `output_tokens/(ms/1000)`; never negative.
- **[G5](./tokenometrics-G5.md):** `total_active_ms + total_idle_ms` reconciles to the session wall-clock within tolerance; `too_fast` set only when idle < output/READ_TOKENS_PER_SEC.
- **[G6](./tokenometrics-G6.md):** `/api/performance` and `/api/sessions/{p}/{s}/metrics` return typed payloads honoring `days`/`project`.
- **[G7](./tokenometrics-G7.md):** SessionDetail shows occupancy bar + TPS + idle markers; Performance page renders all charts; subagent filter works via `?msg=`.
- **[G8](./tokenometrics-G8.md):** Backend and introspect script produce byte-identical event rows for a shared fixture at `SCHEMA_VERSION 14`.

## Negative Measures

### Quality Bar Violations

- **Graceful degradation** (forbidden by global rules + MEMORY.md): wrapping the context-window lookup or duration parse in try/except that silently substitutes 0/None instead of failing loud on a genuinely unexpected shape. Missing window for a *known* model must be a test failure, not a shrug.
- **`python -c` / ad-hoc invocations** (forbidden): verification must use `sqlite3` CLI or proper script files, never `uv run python -c`.
- **Schema migration via ALTER** (per MEMORY.md): new columns must arrive via `SCHEMA_VERSION` bump + DROP/recreate, not `ALTER TABLE` (which `CREATE TABLE IF NOT EXISTS` would no-op).
- **Drifting the two pricing/parse copies** (G8): editing `pricing.py`/`cache.py` without mirroring `introspect_sessions.py` reintroduces divergence.

### Domain-Specific Failures

- **Silent re-inflation:** a later query that joins back to non-head rows, or a new `SUM()` that forgets dedup is already applied, re-double-counts — looks fine, totals wrong.
- **Head misassignment:** picking the wrong block as head (e.g., first vs last) so `stop_reason`/duration are missing on the canonical row while totals still look plausible.
- **Window key collisions:** substring map matches `opus-4-5` inside a hypothetical `opus-4-50`, or `sonnet-4-5` matching before `sonnet-4-6` — wrong budget, plausible-looking ratio. (Mitigation: longest-key-first / anchored matching + test.)
- **Idle attribution leakage:** counting subagent or `tool_result` gaps as human idle, inflating idle time with machine latency.
- **Cross-context occupancy mixing:** attributing a subagent response's occupancy to the main window's ratio (must stay per-event).
- **Too-fast false positives:** flagging a short reply to a short response as "didn't read it," eroding trust in the signal.

