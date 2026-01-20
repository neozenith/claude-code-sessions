# Universal Filters Implementation Spec

## Goal
Implement shared filter components (time range and project filters) across all dashboard sections with:
1. URL parameter synchronization
2. Theme-aware visualizations (light/dark mode support)
3. Persistent filters across navigation

## Current Status (Progress as of implementation)

### Already Complete
- [x] `useFilters.ts` hook - URL-synced state for `days` and `project` params
- [x] `Layout.tsx` - Global filter dropdowns in header
- [x] All pages use `useFilters()` and `buildApiQuery()` for API calls
- [x] URL parameter persistence via `buildNavTo()` in NavLinks
- [x] `usePlotlyTheme.ts` hook - Theme-aware Plotly layouts
- [x] `DailyUsage.tsx` - Updated with theme support
- [x] `WeeklyUsage.tsx` - Updated with theme support
- [x] `MonthlyUsage.tsx` - Updated with theme support
- [x] `HourlyUsage.tsx` - Updated with theme support

### Completed
- [x] `HourOfDay.tsx` - Updated with theme support
- [x] `Dashboard.tsx` - Updated with theme support
- [x] `Projects.tsx` - Updated with theme support
- [x] `Timeline.tsx` - Updated with theme support
- [x] Fixed "All Time" filter (backend endpoint now supports `days=0` or no days param)
- [x] Added "Last 24 hours" and "Last 3 days" time range options
- [x] Run tests, typecheck, lint and format - all passing
- [x] Tested with Playwright MCP:
  - Time range filter works on all pages ✓
  - Project filter works on all pages ✓
  - URL parameters update and persist ✓
  - Theme switching works on all charts ✓
  - Charts look correct in light and dark mode ✓

## Key Files

### Hooks
- `frontend/src/hooks/useFilters.ts` - Filter state and URL sync
- `frontend/src/hooks/usePlotlyTheme.ts` - Theme-aware Plotly config
- `frontend/src/hooks/useApi.ts` - API data fetching

### Context
- `frontend/src/contexts/ThemeContext.tsx` - Light/dark theme context

### Layout
- `frontend/src/components/Layout.tsx` - Contains global filter dropdowns

### Pages (all in `frontend/src/pages/`)
- `Dashboard.tsx`
- `DailyUsage.tsx`
- `WeeklyUsage.tsx`
- `MonthlyUsage.tsx`
- `HourlyUsage.tsx`
- `HourOfDay.tsx`
- `Projects.tsx`
- `Timeline.tsx`
- `SchemaTimeline.tsx`

## Implementation Pattern

### Adding Theme Support to a Page

1. Import the hook:
```tsx
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
```

2. Use in component:
```tsx
const { colors, mergeLayout, isDark } = usePlotlyTheme()
```

3. Update Plot layouts:
```tsx
<Plot
  data={...}
  layout={mergeLayout({
    autosize: true,
    margin: { l: 50, r: 30, t: 30, b: 50 },
    xaxis: { title: { text: 'Date' } },
    yaxis: { title: { text: 'Cost (USD)' } },
  })}
/>
```

4. Use `colors.text` for text elements:
```tsx
textfont: { color: colors.text }
```

5. For heatmaps, use `isDark` for colorscale base:
```tsx
const baseColor = isDark ? '#1f2937' : 'white'
const colorscale = [[0, baseColor], [1, '#10B981']]
```

## Testing Commands

```bash
# Start servers (agentic ports)
make agentic-dev-backend   # Port 8101
make agentic-dev-frontend  # Port 5274

# Quality checks
make test        # Run tests
make typecheck   # TypeScript + mypy
make lint        # ESLint + ruff
make format      # Auto-format

# Sync data
make sync-projects  # rsync from ~/.claude/projects/
```

## Verification Checklist

For each dashboard page:
- [ ] Time range filter changes data displayed
- [ ] Project filter changes data displayed
- [ ] URL updates when filters change (`?days=7&project=xxx`)
- [ ] Filters persist when navigating between pages
- [ ] Charts render correctly in light mode
- [ ] Charts render correctly in dark mode
- [ ] Text is readable in both themes
- [ ] Heatmap background adapts to theme
