# Frontend Conventions

Project-local rules for the React/Vite/Plotly dashboard. These extend the
global TypeScript rules in `.claude/rules/typescript/`.

## Plotly chart legends — always on the RIGHT

Every chart in the dashboard places its legend **outside the plot area, on
the right, stacked vertically**. This is the default for all charts and
should only be overridden when a right-side legend genuinely doesn't fit.

### Implementation

The canonical legend style lives in the theme hook
(`src/hooks/usePlotlyTheme.ts`) and is merged into every `mergeLayout`
call automatically:

```typescript
legend: {
  font: { color: colors.text },
  x: 1.02,            // just outside the right edge of the plot
  y: 1,               // align legend top with plot top
  xanchor: 'left',    // anchor legend's LEFT edge to x=1.02
  yanchor: 'top',
  orientation: 'v',
}
```

Individual charts should **NOT** set `legend:` in their custom layout —
they inherit the default. The only required knob is the right-side
margin (see below).

### Required: right-side margin

Because the legend sits outside the plot area, every chart that has a
legend must reserve room for it with `margin.r`:

```typescript
margin: { l: 60, r: 140, t: 30, b: 50 }
//                ^^^^^
//        ≥ 140 when legend is shown
```

Guidelines for `margin.r`:
- **140px** — fits model IDs, short trace names (most charts).
- **160–200px** — needed when trace names include project paths or
  long labels (e.g. the Dashboard weekly-projects chart uses `r: 200`).
- **30–50px** — charts with `showlegend: false` can use a tight right
  margin since there's no legend to accommodate.

### When NOT to place the legend on the right

Only two legitimate reasons to override the default:

1. **`showlegend: false`** — the chart has no legend at all (e.g.
   single-series bar charts, radial plots where the categorical axis
   already names things). This is fine; just don't set `legend:` either.
2. **Genuinely too narrow** — a tiny inline chart where even 140px of
   right margin would crush the plot. Prefer resizing the chart first;
   only if that's not an option, override with a top or bottom legend.

In the second case, override explicitly in the chart's `mergeLayout`
call with a comment explaining why:

```typescript
// Chart is embedded in a narrow sidebar card; right legend would eat
// half the plot width. Placing at top instead.
legend: { x: 0, y: 1.15, orientation: 'h' as const }
```

### Why right-side over top

- **Scales with trace count.** Vertical stack handles 20+ traces without
  wrapping; a top/horizontal legend wraps to multiple rows and pushes
  the chart down unpredictably.
- **Legend entries read left-to-right.** Model IDs and project paths
  are naturally left-aligned text; stacking them vertically on the
  right reads like a small table of contents.
- **Consistent visual footprint.** Every chart has the same overall
  shape (plot area + right legend column), so the dashboard reads as a
  coherent grid instead of a jumble of differently-shaped cards.

## Other frontend conventions

(Add more as they emerge.)
