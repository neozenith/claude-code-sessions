# G2: Per-session human-prompt summarisation

> - **Index:** [summariser.md](./summariser.md)
> - **Depends on:** none
> - **Blocks:** [G3](./summariser-G3.md), [G7](./summariser-G7.md)
> - **Prev:** [G1](./summariser-G1.md)
> - **Next:** [G3](./summariser-G3.md)

Produces, per session, a structured extraction of the developer's typed prompts across three lenses — task + ubiquitous language, architectural patterns, decisions / values — through a **model-pluggable** summarisation interface over the in-repo local chat engine. This is the atomic unit every roll-up builds on, and the unit the [G10](./summariser-G10.md) benchmark sweeps across model families/sizes.

## Context
`events.message_content` already holds human prompt text, scoped by `msg_kind='human'` (the same scope embeddings use, `embeddings.py:82`).
`sqlite-muninn` already loads a GGUF chat model and exposes `muninn_chat(model_name, prompt)`, used today for KG community naming (`kg/community_naming.py:114`; registration in `kg/runtime.py`).
No summarisation, summary table, or summary pass exists. `SCHEMA_VERSION` is `"17"` and a bump DROP+recreates the cache.

## Outputs
| File | Change |
|------|--------|
| `src/claude_code_sessions/database/sqlite/schema.py` (py) | New `session_summaries` table + `SCHEMA_VERSION` bump to `"18"`. |
| `src/claude_code_sessions/database/sqlite/summaries.py` (py, new) | `summarise_session(conn, project_id, session_id)`: gather human text, build the 3-lens prompt, call `muninn_chat`, parse structured output, upsert; content-hash guard. |
| `src/claude_code_sessions/summarise_cli.py` (py, new) | Manual runner + argparse CLI **decoupled from ingest** (`uv run -m claude_code_sessions.summarise_cli sessions --model M [--scope <scope_path>]`): iterates sessions ingested *to date*, calls `summarise_session`, content-hash-guarded. Wired to external cadence triggers, not the wave auto-update. |
| `tests/test_summaries.py` (py, new) | Fixture-cache tests for extraction shape, content-hash idempotency, fail-loud on unparseable output. |

## Key logic
```sql
CREATE TABLE session_summaries (
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    model TEXT NOT NULL,               -- summariser GGUF model_id (bakes in family + parameter size) — part of the key
    content_hash TEXT NOT NULL,        -- hash of the concatenated msg_kind='human' text
    task_summary TEXT NOT NULL,        -- what task + ubiquitous language of specific systems
    patterns TEXT NOT NULL,            -- architectural patterns used / reused
    decisions_values TEXT NOT NULL,    -- decisions / values expressed
    generated_at TEXT NOT NULL,
    human_event_count INTEGER NOT NULL,
    PRIMARY KEY (project_id, session_id, model)   -- one row per (session, model): benchmark stores many models side-by-side
);
```

## ADR2.1: Summarise with the local `muninn_chat` engine
- **Decision:** All summarisation (session extraction and roll-up merging) runs through a `SummaryEngine` interface whose sole production backend calls `sqlite-muninn`'s `muninn_chat(model_name, prompt)`; no external LLM API is introduced. The interface accepts the GGUF model name as a parameter so several models can run side-by-side.
- **Why:** Zero new dependencies, API keys, network calls, or per-token cost; reproducible with a fixed seed + temperature 0; dogfoods the in-house engine; preserves the project's deliberate 100%-local, fail-loud, rebuildable-from-source invariant.
- **Rejected:** Anthropic API (breaks the all-local invariant, adds key + cost + a network failure surface); Ollama (a redundant second local-inference runtime alongside muninn).
- **Deferred:** *Which* GGUF (model family + parameter size) is not fixed here — it is a swept variable resolved empirically by the [G10](./summariser-G10.md) benchmark. The `session_summaries.model` column records provenance so multiple models coexist during the sweep.

## ADR2.2: Summarise `msg_kind = 'human'` only
- **Decision:** The summarisation input is exactly the events with `msg_kind = 'human'` — the developer's typed prompts — excluding all `subagent-*`, assistant, tool, meta, and `user_text` events.
- **Why:** It is the cleanest signal of human intent and the same scope already embedded (`embeddings.py:82`), so the unit is consistent across features.
- **Rejected:** Including `user_text` (it mixes in pasted output/logs that dilute intent).

## ADR2.4: Summarisation is decoupled from ingest — manually triggered, eventually consistent
- **Decision:** No summarisation runs inside the wave/ingest auto-update. Session extraction (G2) and roll-ups (G3) are standalone runners invoked manually via CLI, each parameterised by `(strategy, model, hierarchy_level)`, operating on whatever is ingested to date. Results are eventually consistent: a run consumes the current tier below it and the next run picks up anything newer.
- **Why:** The user binds each tier to its own external cadence (e.g. session + leaf rollups daily, domain/root rollups weekly); coupling to ingest would forbid that and tie every summary to the last ingest moment. Decoupling also means the G10 benchmark and the cadence triggers share one call surface.
- **Rejected:** Invoking summarisation in the ingest/rebuild flow (forces one cadence, blocks ingest on LLM calls); a background thread tied to cache build (still implicitly ingest-coupled, no per-tier cadence control).

## ADR2.3: Content-hash guard, cache-resident summaries (scoped by model)
- **Decision:** Summaries live in the cache DB; `summarise_session` skips a session only when a row exists for **the same `(session, model)`** with an unchanged human-text `content_hash`, so an incremental ingest performs zero `muninn_chat` calls for untouched sessions. Re-summarising the same text under a *different* `model_id` is a cache miss (a new row), which is what lets the benchmark sweep models. A `SCHEMA_VERSION` bump DROP-recreates and recomputes once, as with every other cached artifact.
- **Why:** Consistent with the project invariant that the cache is rebuildable from source; cheap incremental updates; no extra DB lifecycle. Local inference makes the once-per-bump recompute free in dollar terms.
- **Rejected:** A sidecar DB that survives schema bumps (avoids the once-per-bump recompute but adds a second DB lifecycle and a parity burden in G11 for marginal gain).

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T2.1](./summariser-G2-T2.1.md) | A developer's typed prompts become one stored 3-lens session summary _(tracer)_ | — |
| [T2.2](./summariser-G2-T2.2.md) | Only the developer's typed prompts reach the engine | [T2.1](./summariser-G2-T2.1.md) |
| [T2.3](./summariser-G2-T2.3.md) | Re-running on unchanged prompts performs zero engine calls | [T2.1](./summariser-G2-T2.1.md) |
| [T2.4](./summariser-G2-T2.4.md) | Edited prompts trigger a fresh summary | [T2.3](./summariser-G2-T2.3.md) |
| [T2.5](./summariser-G2-T2.5.md) | A session with no typed prompts produces no summary | [T2.1](./summariser-G2-T2.1.md) |
| [T2.6](./summariser-G2-T2.6.md) | The production engine drives `muninn_chat` with the configured model name | [T2.1](./summariser-G2-T2.1.md) |
| [T2.7](./summariser-G2-T2.7.md) | A `summarise sessions` run summarises not-yet-current sessions off ingested data (manual, scope-filterable) | [T2.1](./summariser-G2-T2.1.md), [T1.2](./summariser-G1-T1.2.md) |
