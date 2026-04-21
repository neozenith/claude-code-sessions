import { useMemo } from 'react'
import Plot from '@/lib/plotly'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatNumber } from '@/lib/formatters'
import type { CallsTimelineRow, CallType, TopCallRow } from '@/lib/api-client'

/**
 * Charts powered by the ``event_calls`` fact table.
 *
 * Two independent building blocks are exported:
 *
 *   - ``TopCallsRow``   — three horizontal-bar cards (skills / sub-agents / CLIs).
 *     Cheap, quick-glance signal; lives at the top of every usage page and
 *     in the Dashboard overview.
 *
 *   - ``CallsTimeline`` — stacked-bar chart of call counts over time, grouped
 *     by ``call_type``. Granularity-aware (daily / weekly / monthly) and
 *     lives further down each usage page beneath the existing cost charts.
 *
 * Splitting them this way lets pages compose only the pieces that fit —
 * Dashboard doesn't need the time-series breakdown, for example.
 */

// Distinct colors per call_type so stacked segments are instantly readable.
// Keys must stay in sync with CallType in api-client.ts.
const CALL_TYPE_COLORS: Record<CallType, string> = {
  tool: '#3B82F6',         // blue    — the broadest bucket
  cli: '#F59E0B',          // amber   — shell commands extracted from Bash
  subagent: '#EC4899',     // pink    — sub-agent launches
  skill: '#10B981',        // green   — skill invocations
  rule: '#8B5CF6',         // violet  — CLAUDE.md / rules triggers
  make_target: '#06B6D4',  // cyan    — Make targets extracted from `make <target>`
  uv_script: '#EF4444',    // red     — Scripts run via `uv run <script>`
  bun_script: '#F97316',   // orange  — Scripts run via `bun run <script>`
}

const CALL_TYPE_LABELS: Record<CallType, string> = {
  tool: 'Tools',
  cli: 'CLI commands',
  subagent: 'Sub-agents',
  skill: 'Skills',
  rule: 'Rules',
  make_target: 'Make targets',
  uv_script: 'uv scripts',
  bun_script: 'bun scripts',
}

// Render order for the time-series stacked bar (bottom-to-top).
//
// NOTE: ``make_target`` is intentionally NOT in this list. It's an
// augmentation of the ``cli='make'`` signal — including it here would
// double-count make invocations on the timeline. The 4th top-N card
// in ``TopCallsRow`` is where make_target shows up.
const CALL_TYPE_ORDER: readonly CallType[] = [
  'tool',
  'cli',
  'subagent',
  'skill',
  'rule',
] as const

// Unix utilities that dominate the CLI count without adding useful signal.
// Filtered out at query time on the Top CLI commands card. Keep this list
// short — the goal is to surface interesting tools, not hide everything.
// Shell-level utilities and bash builtins filtered from the Top CLI
// chart — they dominate counts without being useful signal. Keeping
// this list in one place so it's easy to tune.
const CLI_NOISE_EXCLUDE = [
  // Text / file utilities (tiny, always-available, uninteresting).
  'wc', 'head', 'tail', 'grep', 'echo', 'ls', 'cat', 'sort', 'sed',
  'tr', 'uniq', 'tee',
  // Filesystem operations.
  'find', 'mkdir', 'rm', 'cp', 'mv', 'touch',
  // Process / flow-control utilities.
  'sleep', 'ps', 'cd',
]

// Well-known Python tools that get invoked via `uv run X` but aren't
// what the "Top uv scripts" card is trying to surface. The card's goal
// is custom repo-local scripts and skill entry points that agentic
// memory or skills directed the model to run — NOT the standard
// test / lint / format toolchain that runs on every project.
const UV_SCRIPT_NOISE_EXCLUDE = [
  // Interpreters
  'python', 'python3',
  // Test runners & coverage
  'pytest', 'coverage',
  // Formatters / linters
  'ruff', 'black', 'isort', 'flake8', 'pylint', 'autopep8', 'sqlfluff',
  // Type checkers
  'mypy', 'pyright',
  // Package managers
  'pip', 'pipx',
  // Web servers
  'uvicorn', 'gunicorn',
  // Common data / platform tools
  'dbt', 'alembic',
]


// ---------------------------------------------------------------------------
// TopCallsRow — 3 horizontal-bar cards
// ---------------------------------------------------------------------------


/**
 * Four top-N horizontal-bar charts (skills, sub-agents, CLIs, make
 * targets) rendered side-by-side. Respects the page-wide ``days`` /
 * ``project`` filter via ``useFilters``, so no props are required at
 * call-sites.
 */
export const TopCallsRow = () => {
  const { colors, mergeLayout } = usePlotlyTheme()
  const { buildApiQuery } = useFilters()

  // One Top-N fetch per dimension. Each card shows the top 8 entries —
  // enough to expose the long tail without overflowing the card.
  // Running the calls in parallel is simpler than a single combined
  // endpoint.
  const topSkillQuery = buildApiQuery({ call_type: 'skill', limit: 8 })
  const topSubagentQuery = buildApiQuery({ call_type: 'subagent', limit: 8 })
  // CLIs: filter out common unix utilities that dominate counts without
  // being useful signal. The API accepts a comma-separated list.
  const topCliQuery = buildApiQuery({
    call_type: 'cli',
    limit: 8,
    exclude: CLI_NOISE_EXCLUDE.join(','),
  })
  const topMakeTargetQuery = buildApiQuery({ call_type: 'make_target', limit: 8 })
  // uv scripts: filter well-known Python tools so the card surfaces
  // custom scripts (skill entry points, repo-local `.py` files) rather
  // than the standard toolchain that runs on every project.
  const topUvScriptQuery = buildApiQuery({
    call_type: 'uv_script',
    limit: 8,
    exclude: UV_SCRIPT_NOISE_EXCLUDE.join(','),
  })
  const topBunScriptQuery = buildApiQuery({ call_type: 'bun_script', limit: 8 })

  const { data: topSkills } = useApi<TopCallRow[]>(`/calls/top${topSkillQuery}`)
  const { data: topSubagents } = useApi<TopCallRow[]>(`/calls/top${topSubagentQuery}`)
  const { data: topClis } = useApi<TopCallRow[]>(`/calls/top${topCliQuery}`)
  const { data: topMakeTargets } = useApi<TopCallRow[]>(`/calls/top${topMakeTargetQuery}`)
  const { data: topUvScripts } = useApi<TopCallRow[]>(`/calls/top${topUvScriptQuery}`)
  const { data: topBunScripts } = useApi<TopCallRow[]>(`/calls/top${topBunScriptQuery}`)

  // Six vertical-bar cards. On mobile they stack to one column; on
  // md+ they split 2 across; on lg+ 3 across (so six cards land on a
  // tidy 2×3 grid).
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <TopCallsCard
        title="Top skills"
        rows={topSkills}
        color={CALL_TYPE_COLORS.skill}
        colors={colors}
        mergeLayout={mergeLayout}
      />
      <TopCallsCard
        title="Top sub-agents"
        rows={topSubagents}
        color={CALL_TYPE_COLORS.subagent}
        colors={colors}
        mergeLayout={mergeLayout}
      />
      <TopCallsCard
        title="Top CLI commands"
        rows={topClis}
        color={CALL_TYPE_COLORS.cli}
        colors={colors}
        mergeLayout={mergeLayout}
      />
      <TopCallsCard
        title="Top make targets"
        rows={topMakeTargets}
        color={CALL_TYPE_COLORS.make_target}
        colors={colors}
        mergeLayout={mergeLayout}
      />
      <TopCallsCard
        title="Top uv scripts"
        rows={topUvScripts}
        color={CALL_TYPE_COLORS.uv_script}
        colors={colors}
        mergeLayout={mergeLayout}
      />
      <TopCallsCard
        title="Top bun scripts"
        rows={topBunScripts}
        color={CALL_TYPE_COLORS.bun_script}
        colors={colors}
        mergeLayout={mergeLayout}
      />
    </div>
  )
}


// ---------------------------------------------------------------------------
// CallsTimeline — stacked bar by call_type over time
// ---------------------------------------------------------------------------


export interface CallsTimelineProps {
  granularity: 'daily' | 'weekly' | 'monthly'
  /** Label for the x-axis (e.g. "Date", "Week starting", "Month"). */
  xAxisLabel: string
}

export const CallsTimeline = ({ granularity, xAxisLabel }: CallsTimelineProps) => {
  const { filters, buildApiQuery } = useFilters()
  const { mergeLayout } = usePlotlyTheme()

  const timelineQuery = buildApiQuery({ granularity })
  const { data: timelineData, loading: timelineLoading } = useApi<CallsTimelineRow[]>(
    `/calls/timeline${timelineQuery}`
  )

  // Pivot the long-format timeline into one series per call_type.
  const timeline = useMemo(() => {
    const byBucket = new Map<string, Partial<Record<CallType, number>>>()
    timelineData?.forEach((row) => {
      const bucket = byBucket.get(row.time_bucket) ?? {}
      bucket[row.call_type] = (bucket[row.call_type] ?? 0) + Number(row.call_count)
      byBucket.set(row.time_bucket, bucket)
    })
    const buckets = Array.from(byBucket.keys()).sort()
    const seriesByType: Partial<Record<CallType, number[]>> = {}
    CALL_TYPE_ORDER.forEach((type) => {
      seriesByType[type] = buckets.map((b) => byBucket.get(b)?.[type] ?? 0)
    })
    // Drop call_types that have zero data across the whole window — keeps
    // the legend honest (e.g. no phantom "Rules" row when nothing matched).
    const activeTypes = CALL_TYPE_ORDER.filter((type) =>
      (seriesByType[type] ?? []).some((n) => n > 0)
    )
    return { buckets, seriesByType, activeTypes }
  }, [timelineData])

  const totalCalls = useMemo(() => {
    let total = 0
    Object.values(timeline.seriesByType).forEach((arr) => {
      arr?.forEach((n) => {
        total += n
      })
    })
    return total
  }, [timeline])

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Calls by type
          {totalCalls > 0 && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              ({formatNumber(totalCalls)} total{filters.project ? ' in project' : ''})
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {timelineLoading ? (
          <div className="text-center py-8">Loading…</div>
        ) : timeline.buckets.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No call data for this window. Run a cache update if sessions
            existed before schema v7.
          </div>
        ) : (
          <Plot
            data={timeline.activeTypes.map((type) => ({
              x: timeline.buckets,
              y: timeline.seriesByType[type] ?? [],
              type: 'bar' as const,
              name: CALL_TYPE_LABELS[type],
              marker: { color: CALL_TYPE_COLORS[type] },
              hovertemplate: `%{x}<br>${CALL_TYPE_LABELS[type]}: %{y:,}<extra></extra>`,
            }))}
            layout={mergeLayout({
              autosize: true,
              barmode: 'stack',
              margin: { l: 60, r: 140, t: 30, b: 60 },
              xaxis: { title: { text: xAxisLabel }, tickangle: -45 },
              yaxis: { title: { text: 'Call count' }, tickformat: ',d' },
              showlegend: true,
            })}
            useResizeHandler
            style={{ width: '100%', height: '400px' }}
          />
        )}
      </CardContent>
    </Card>
  )
}


// ---------------------------------------------------------------------------
// Internal: single top-N card
// ---------------------------------------------------------------------------


interface TopCallsCardProps {
  title: string
  rows: TopCallRow[] | null
  color: string
  colors: ReturnType<typeof usePlotlyTheme>['colors']
  mergeLayout: ReturnType<typeof usePlotlyTheme>['mergeLayout']
}

// Inline rather than a separate file — exists only as a visual unit of
// TopCallsRow and has no standalone use.
const TopCallsCard = ({ title, rows, color, colors, mergeLayout }: TopCallsCardProps) => {
  // API returns rows in descending count order, which is the left-to-right
  // order we want for vertical bars (tallest on the left).
  const sorted = rows ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground text-sm">
            No data
          </div>
        ) : (
          <Plot
            data={[
              {
                x: sorted.map((r) => r.call_name),
                y: sorted.map((r) => r.call_count),
                type: 'bar' as const,
                marker: { color },
                text: sorted.map((r) => formatNumber(r.call_count)),
                textposition: 'outside' as const,
                textfont: { color: colors.text, size: 11 },
                cliponaxis: false,
                hovertemplate:
                  '%{x}<br>%{y:,} calls<br>%{customdata} sessions<extra></extra>',
                customdata: sorted.map((r) => r.session_count),
              },
            ]}
            layout={mergeLayout({
              autosize: true,
              // Extra bottom margin for the -45° rotated category labels
              // — 8 bars per card means labels sit closer together and
              // need more diagonal room to avoid overlapping each other.
              margin: { l: 40, r: 20, t: 20, b: 120 },
              xaxis: {
                tickangle: -45,
                automargin: true,
                // Force every tick to render; otherwise Plotly may skip
                // labels when it thinks they'll collide. We've accepted
                // the collision in exchange for showing all 8 names.
                tickmode: 'array',
                tickvals: sorted.map((r) => r.call_name),
              },
              yaxis: { title: { text: 'Calls' }, tickformat: ',d' },
              showlegend: false,
            })}
            useResizeHandler
            // Taller card than the 5-bar version so the extra bottom
            // margin doesn't squeeze the plot area. The bar region
            // itself stays roughly the same height as before.
            style={{ width: '100%', height: '300px' }}
          />
        )}
      </CardContent>
    </Card>
  )
}
