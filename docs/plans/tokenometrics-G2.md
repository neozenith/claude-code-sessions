# G2: Context-window utilization annotations

> **[« Tokenometrics index](./tokenometrics.md)**  ·  Gap 2 of 8
>
> **Depends on:** [G1](./tokenometrics-G1.md)  ·  **Blocks:** [G6](./tokenometrics-G6.md), [G8](./tokenometrics-G8.md)
>
> **Nav:** [« G1](./tokenometrics-G1.md)  ·  [G3 »](./tokenometrics-G3.md)

**Current:** No notion of context occupancy or per-model window anywhere.

**Gap:** Add a curated `model_id → window` map and annotate each event with live occupancy and the normalized ratio (the "smart zone" signal). Occupancy is read from the event's own usage, so subagent events measure against their own context automatically.

**Output(s):**
- `src/claude_code_sessions/database/sqlite/pricing.py` (Python): `CONTEXT_WINDOWS` map + `context_window(model_id)` + `context_ratio(tokens, window)` + `SMART_ZONE_*` constants + `context_zone(tokens, window)`.
- `src/claude_code_sessions/database/sqlite/schema.py`: add `events.context_tokens INTEGER DEFAULT 0`, `context_window INTEGER`, `context_ratio REAL`.
- `cache.py:_parse_event`: compute occupancy + window + ratio.
- `frontend/src/lib/context-zone.ts` (TS): mirror of `SMART_ZONE_*` + `contextZone()` for bar colors / histogram bands.
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
# context_tokens = input + cache_read + cache_creation (assistant only); ratio = tokens/window or None

# Smart-zone bands (evidence: RULER 50% / NoLiMa 32K / Databricks 64K) — see ADR.
SMART_ZONE_CAUTION_PCT, SMART_ZONE_DANGER_PCT = 0.50, 0.70
SMART_ZONE_CAUTION_ABS, SMART_ZONE_DANGER_ABS = 32_768, 65_536
def context_zone(tokens: int, window: int | None) -> str | None:
    if not window: return None
    pct = tokens / window
    if pct >= SMART_ZONE_DANGER_PCT or tokens >= SMART_ZONE_DANGER_ABS:   return "danger"
    if pct >= SMART_ZONE_CAUTION_PCT or tokens >= SMART_ZONE_CAUTION_ABS: return "caution"
    return "smart"
```

## ADR: Meaning of "accumulated token count"
| Option | Pros | Cons |
|--------|------|------|
| Live context occupancy | Bounded by window; meaningful ratio; matches "smart zone" | Not a monotonic odometer |
| Monotonic running sum | Throughput odometer | Far exceeds window; ratio meaningless |

**Decision:** Live context occupancy (`input + cache_read + cache_creation`).
**Rationale:** User confirmed; it is the accurate "how full is the window now" measure and the only one for which a budget ratio is meaningful.

## ADR: Context-window budget basis
**Decision:** Curated per-model `CONTEXT_WINDOWS` map (table above), researched against vendor docs and corroborated by observed occupancy. Unknown/`<synthetic>`/`model.gguf` → `None` (ratio undefined).
**Rationale:** User asked for a researched, curated mapping. 1M is GA (not beta) on opus-4-6/4-7/4-8 + sonnet-4-6, so the window is a pure function of model_id — no per-session heuristic needed.

## ADR: Smart-zone band thresholds
Resolved by literature search (all citations verified via WebFetch).

| Band | Rule (whichever hit first) | Evidence |
|------|----------------------------|----------|
| **Smart / green** | `< 50%` of window **and** `< 32,768` tokens | RULER: effective context ≈ 50% of advertised for strong models. |
| **Caution / amber** | `>= 50%` **or** `>= 32,768` tokens | NoLiMa: at 32K, 11 models drop below 50% of their short-context baseline (GPT-4o 99.3%→69.7%). RULER effective-length edge ≈ 50%. |
| **Danger / red** | `>= 70%` **or** `>= 65,536` tokens | Databricks: RAG accuracy onset 16k–64k (model-dependent); Chroma: degradation grows unreliable with length (gradual, not a cliff). |

**Decision:** Percentage bands **with an absolute-token override**: `zone = worse_of(percentage_band, absolute_band)`. Caution = 50% **or** 32K; Danger = 70% **or** 64K.
**Rationale:** A pure percentage overstates safety on 1M-window models (50% = 500K, which NoLiMa/Databricks contradict); a pure absolute cap understates room on 32k/200k models. RULER anchors the 50% figure; NoLiMa anchors the 32K absolute; the absolute override is what makes the metric honest across 32k / 200k / 1M models. Thresholds live once in `pricing.py` (`SMART_ZONE_*` constants) and are mirrored in a frontend const so backend measures (G6) and UI bands (G7) agree.

**Citations (verified):**
- RULER — effective ≈ 50% of advertised window: https://github.com/NVIDIA/RULER
- NoLiMa — half-baseline by 32K, independent of window: https://arxiv.org/abs/2502.05167
- Databricks — per-model RAG onset 16k–64k: https://www.databricks.com/blog/long-context-rag-performance-llms
- Chroma "Context Rot" — gradual, non-uniform degradation across 18 frontier models: https://www.trychroma.com/research/context-rot

## Tickets

Each ticket is a standalone TDD vertical slice (one test → one implementation); the full Test/Implementation outlines live in the per-ticket files linked below.

| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T2.1](./tokenometrics-G2-T2.1.md) | A caller can resolve a 1M-window model's context window | none |
| [T2.2](./tokenometrics-G2-T2.2.md) | A caller gets 200k for standard models and None for unknown | [T2.1](./tokenometrics-G2-T2.1.md) |
| [T2.3](./tokenometrics-G2-T2.3.md) | Window lookup is not fooled by substring collisions | [T2.1](./tokenometrics-G2-T2.1.md) |
| [T2.4](./tokenometrics-G2-T2.4.md) | A caller gets the right zone from percentage bands | [T2.1](./tokenometrics-G2-T2.1.md) |
| [T2.5](./tokenometrics-G2-T2.5.md) | The absolute-token override supersedes percentage on 1M windows | [T2.4](./tokenometrics-G2-T2.4.md) |
| [T2.6](./tokenometrics-G2-T2.6.md) | An operator sees per-event occupancy and ratio after ingestion | [T1.1](./tokenometrics-G1-T1.1.md), [T2.1](./tokenometrics-G2-T2.1.md) |

