# Tokenometrics doc style

Precise and concise: cut any token that doesn't change what the reader *does*; use Markdown structure, not bold labels.

> Sources: [Diátaxis](https://diataxis.fr/reference/) · [Google](https://developers.google.com/style/tables) & [Microsoft](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice) style guides · [Nygard ADR](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) / [MADR](https://adr.github.io/madr/) · [Gherkin](https://cucumber.io/docs/bdd/better-gherkin/) · [SemBr](https://sembr.org/) · [WebAIM headings](https://webaim.org/techniques/headings/) · [GFM](https://github.github.com/gfm/).

## Rules (all tiers)

1. **Front-load.** First line states the outcome; readers scan F-pattern and may not scroll.
2. **Headings are verb-led sentence fragments**, sentence case, no end punctuation.
3. **No bold-pseudo-headings.** A `**Label:**` line becomes a real heading, a table column, or is deleted — bold isn't navigable structure (WCAG 1.3.1).
4. **Container by shape.** ≥3-property records → table; sequences/sets → list; one idea → prose. Keep table cells short (no nested lists).
5. **Cut filler and constants.** No *currently* / *you can*; drop any field identical on every item (e.g. `Cycle: RED → GREEN`, `Mocks: none`). State a field only when it varies.
6. **Separate genres.** *Why* = short prose; *what* = austere table; *steps* = the loop. Don't blend the three in one paragraph.
7. **One observable behavior per ticket**, declarative `<actor> <outcome>`.
8. **Settled ADRs keep Decision + Why**; compress rejected options to one line; no Pros/Cons table.
9. **Semantic line breaks in prose only** (one clause per line — clean agent diffs); tables and lists stay single-line.
10. **Self-contained, labeled chunks.** The test of a sentence: delete it — does the build change? If not, cut it.

---

## Tier 1 — Index (`tokenometrics.md`)

Genre: navigation + framing. Keep the diagrams and the rolled-up tables; everything else is a pointer.

- Sections: Execution Plan · Overview · Current State · Desired State · Gap Analysis (Gap Map + Dependencies + Gaps table) · Success Measures · Negative Measures.
- Overview lists the gaps as links + one-line outcomes. No per-gap detail lives here.
- Progress, Gaps, and Success/Negative measures are tables; gap/ticket IDs are links.
- Diagrams obey the mermaid contrast + complexity gates.

---

## Tier 2 — Gap (`tokenometrics-G<n>.md`)

Genre: explanation (why) + reference (what) + pointer (tickets).

```markdown
# G<n> · <Title>

> [« index](./tokenometrics.md) · **depends** [G..] · **blocks** [G..] · prev [G..] · next [G..]

<1–2 sentences: what closing this gap delivers.>

## Context
<Current state and the binding constraint, 1–3 sentences, semantic line breaks.>

## Outputs
| File | Change |
|------|--------|
| `path` (lang) | <what changes> |

## Key logic            ← optional; include only when a snippet de-risks the work
```python
…
```

## Decision · <title>   ← one per settled ADR
We will <decision, full sentence>.
*Why:* <1–2 sentences.> *Rejected:* <option (reason); …>

## Tickets
| Ticket | Behavior | Depends on |
|--------|----------|------------|
| [T<n>.1](./tokenometrics-G<n>-T<n>.1.md) | <behavior> | — |
```

Cut from the old format: the `**Current:** / **Gap:**` labels (fold into the lead + Context), the ADR Pros/Cons tables, and any Output line that just restates a ticket.

---

## Tier 3 — Ticket (`tokenometrics-G<n>-T<x.y>.md`)

Genre: austere reference. One behavior, one test, the implementation target, dependencies.

```markdown
# T<x.y> · <actor> <observable outcome>

> [« G<n> <title>](./tokenometrics-G<n>.md) · [index](./tokenometrics.md) · prev [T..](./..) · next [T..](./..)

- [ ] **Done**

<One sentence stating the precise, assertion-worthy contract — exact endpoint/args/return or the concrete fact the test checks.> <"Tracer bullet." — only on T<n>.1>

| | |
|--|--|
| Test | `path::test_name` — <assertion against the public interface> |
| Implements | `file` <symbol> · `file` |
| Depends on | [T..](./..) · … — or — |
| Mocks | <only if not `none`> |
| Refactor | <only if present> |
```

Cut from the old format: `**Cycle:** RED → GREEN` (every ticket is RGR — it's in the loop prompt), `**Mocks:** none` (state mocks only when non-empty), the `**Behavior:**` label (the title *is* the behavior; the lead sentence adds precision), and the 3-level Test/Implementation bullet nest (collapse to table rows).
