# G2: Context-window utilization annotations

> **[« Tokenometrics index](./tokenometrics.md)**  ·  Gap 2 of 8
>
> **Depends on:** [G1](./tokenometrics-G1.md)  ·  **Blocks:** [G6](./tokenometrics-G6.md), [G8](./tokenometrics-G8.md)
>
> **Nav:** [« G1](./tokenometrics-G1.md)  ·  [G3 »](./tokenometrics-G3.md)

**Current:** No notion of context occupancy or per-model window anywhere.

**Gap:** Add a curated `model_id → window` map and annotate each event with live occupancy and the normalized ratio (fraction of the window used). Occupancy is read from the event's own usage, so subagent events measure against their own context automatically. The ratio is exposed as a **raw quantitative value** — no categorical "smart/caution/danger" labeling (see ADR: Quantitative ratio only).

**Output(s):**
- `src/claude_code_sessions/database/sqlite/pricing.py` (Python): `CONTEXT_WINDOWS` map + `context_window(model_id)` + `context_ratio(tokens, window)`.
- `src/claude_code_sessions/database/sqlite/schema.py`: add `events.context_tokens INTEGER DEFAULT 0`, `context_window INTEGER`, `context_ratio REAL`.
- `cache.py:_parse_event`: compute occupancy + window + ratio.
- `tests/test_context_window.py` (Python).

**References:**
```python
# pricing.py — substring match like the existing model_family().
CONTEXT_WINDOWS: dict[str, int] = {
    "opus-4-6": 1_000_000, "opus-4-7": 1_000_000, "opus-4-8": 1_000_000,
    "sonnet-4-6": 1_000_000,
    "opus-4-5": 200_000, "sonnet-4-5": 200_000, "haiku-4-5": 200_000,
    "qwen2.5-coder": 32_768,          # native default; YaRN 128k is off by default
    "devstral-small-2": 256_000,
}
def context_window(model_id: str | None) -> int | None:
    if not model_id: return None
    low = model_id.lower()
    # iterate longest-key-first so "opus-4-5" can't shadow "opus-4-50"-style ids
    for key in sorted(CONTEXT_WINDOWS, key=len, reverse=True):
        if key in low: return CONTEXT_WINDOWS[key]
    return None
# context_tokens = input + cache_read + cache_creation (assistant only)
def context_ratio(tokens: int, window: int | None) -> float | None:
    if not window: return None         # window unknown → ratio undefined
    return tokens / window             # raw fraction of the window in use
```

## ADR: Meaning of "accumulated token count"
| Option | Pros | Cons |
|--------|------|------|
| Live context occupancy | Bounded by window; meaningful ratio | Not a monotonic odometer |
| Monotonic running sum | Throughput odometer | Far exceeds window; ratio meaningless |

**Decision:** Live context occupancy (`input + cache_read + cache_creation`).
**Rationale:** User confirmed; it is the accurate "how full is the window now" measure and the only one for which a budget ratio is meaningful.

## ADR: Context-window budget basis
**Decision:** Curated per-model `CONTEXT_WINDOWS` map (table above), researched against vendor docs and corroborated by observed occupancy. Unknown/`<synthetic>`/`model.gguf` → `None` (ratio undefined).
**Rationale:** User asked for a researched, curated mapping. 1M is GA (not beta) on opus-4-6/4-7/4-8 + sonnet-4-6, so the window is a pure function of model_id — no per-session heuristic needed.

## ADR: Quantitative ratio only — no zone labeling
| Option | Pros | Cons |
|--------|------|------|
| Raw `context_ratio` (fraction of window) | Objective, quantitative, model-agnostic; no disputable thresholds | Caller must interpret "how full is too full" |
| Categorical zones (smart/caution/danger) | One-glance qualitative read | Thresholds are subjective and model-dependent; introduced an internal spec contradiction (T2.4 40k=smart vs the 32K absolute caution floor) |

**Decision:** Expose the **raw `context_ratio` only** (`tokens / window`, `None` when the window is unknown). Drop all zone/band labeling — `SMART_ZONE_*` constants, `context_zone()`, the `frontend/src/lib/context-zone.ts` mirror, and the `zone_histogram` — across every gap and ticket.
**Rationale:** User decision (Phase-2 refinement): the "smart zone" is subjective per model, whereas the percentage of context-window used is quantitative and sufficient. Removing the categorical layer also eliminates the T2.4/T2.5 threshold contradiction. Frontend surfaces (G6/G7) render the raw ratio (e.g. a proportional bar and a ratio-binned histogram) without named bands.
**Superseded:** the previous "Smart-zone band thresholds" ADR (RULER 50% / NoLiMa 32K / Databricks 64K research) is withdrawn; those citations no longer drive any code.

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); the full Test/Implementation outlines live in the per-ticket files linked below.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T2.1](./tokenometrics-G2-T2.1.md) | A caller can resolve a 1M-window model's context window | none |
| [T2.2](./tokenometrics-G2-T2.2.md) | A caller gets 200k for standard models and None for unknown | [T2.1](./tokenometrics-G2-T2.1.md) |
| [T2.3](./tokenometrics-G2-T2.3.md) | Window lookup is not fooled by substring collisions | [T2.1](./tokenometrics-G2-T2.1.md) |
| [T2.4](./tokenometrics-G2-T2.4.md) | A caller gets the context-utilization ratio (fraction of window used) | [T2.1](./tokenometrics-G2-T2.1.md) |
| [T2.5](./tokenometrics-G2-T2.5.md) | ~~The absolute-token override supersedes percentage on 1M windows~~ **Dropped** (zone labeling removed per ADR) | [T2.4](./tokenometrics-G2-T2.4.md) |
| [T2.6](./tokenometrics-G2-T2.6.md) | An operator sees per-event occupancy and ratio after ingestion | [T1.1](./tokenometrics-G1-T1.1.md), [T2.1](./tokenometrics-G2-T2.1.md) |

