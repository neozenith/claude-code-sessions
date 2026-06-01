# G2: Context-window utilization annotations

> - **Index:** [tokenometrics.md](./tokenometrics.md)
> - **Depends on:** [G1](./tokenometrics-G1.md)
> - **Blocks:** [G6](./tokenometrics-G6.md), [G8](./tokenometrics-G8.md)
> - **Prev:** [G1](./tokenometrics-G1.md)
> - **Next:** [G3](./tokenometrics-G3.md)

Annotate each event with its live context occupancy and a raw utilization ratio (fraction of the model's window used), from a curated `model_id → window` map.

## Context

No notion of context occupancy or per-model window exists today.
Occupancy is read from the event's own usage,
so subagent events measure against their own context automatically.
The ratio is a **raw quantitative value** — no smart/caution/danger labeling (see *Quantitative ratio only*).

## Outputs

| File | Change |
|------|--------|
| `database/sqlite/pricing.py` | `CONTEXT_WINDOWS` map + `context_window(model_id)` + `context_ratio(tokens, window)` |
| `database/sqlite/schema.py` | add `context_tokens INTEGER`, `context_window INTEGER`, `context_ratio REAL` |
| `cache.py:_parse_event` | compute occupancy + window + ratio |
| `tests/test_context_window.py` | window lookup + ratio |

## Key logic

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
    # longest-key-first so "opus-4-5" can't shadow "opus-4-50"-style ids
    for key in sorted(CONTEXT_WINDOWS, key=len, reverse=True):
        if key in low: return CONTEXT_WINDOWS[key]
    return None
# context_tokens = input + cache_read + cache_creation (assistant only)
def context_ratio(tokens: int, window: int | None) -> float | None:
    if not window: return None         # window unknown → ratio undefined
    return tokens / window
```

## ADR2.1: Accumulated count is live occupancy

- **Decision:** use live context occupancy (`input + cache_read + cache_creation`) as the per-event "accumulated" count.
- **Why:** it is bounded by the window — the only basis on which a utilization ratio is meaningful.
- **Rejected:** monotonic running sum (far exceeds the window; ratio meaningless).

## ADR2.2: Window from a curated per-model map

- **Decision:** resolve the window from a curated per-model `CONTEXT_WINDOWS` map; unknown / `<synthetic>` / `model.gguf` → `None` (ratio undefined).
- **Why:** 1M is GA (not beta) on opus-4-6/4-7/4-8 + sonnet-4-6, so the window is a pure function of `model_id` — no per-session heuristic needed.

## ADR2.3: Expose the raw ratio, no zone labels

- **Decision:** expose the **raw `context_ratio` only**, and drop all zone/band labeling (`SMART_ZONE_*`, `context_zone()`, the `context-zone.ts` mirror, and `zone_histogram`) across every gap and ticket.
- **Why:** the "smart zone" is subjective per model, whereas % used is quantitative and sufficient; this also removes the T2.4/T2.5 threshold contradiction. G6/G7 render the raw ratio (proportional bar, ratio-binned histogram) without named bands.
- **Rejected:** categorical zones (smart/caution/danger) — subjective, model-dependent thresholds.
- **Superseded:** the prior "Smart-zone band thresholds" ADR (RULER 50%, NoLiMa 32K, Databricks 64K) is withdrawn; those citations no longer drive code.

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); full outlines live in the linked files.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T2.1](./tokenometrics-G2-T2.1.md) | A caller can resolve a 1M-window model's context window | — |
| [T2.2](./tokenometrics-G2-T2.2.md) | A caller gets 200k for standard models and None for unknown | [T2.1](./tokenometrics-G2-T2.1.md) |
| [T2.3](./tokenometrics-G2-T2.3.md) | Window lookup is not fooled by substring collisions | [T2.1](./tokenometrics-G2-T2.1.md) |
| [T2.4](./tokenometrics-G2-T2.4.md) | A caller gets the context-utilization ratio (fraction of window used) | [T2.1](./tokenometrics-G2-T2.1.md) |
| [T2.5](./tokenometrics-G2-T2.5.md) | ~~The absolute-token override supersedes percentage on 1M windows~~ **Dropped** (zone labeling removed per ADR) | [T2.4](./tokenometrics-G2-T2.4.md) |
| [T2.6](./tokenometrics-G2-T2.6.md) | An operator sees per-event occupancy and ratio after ingestion | [T1.1](./tokenometrics-G1-T1.1.md), [T2.1](./tokenometrics-G2-T2.1.md) |
