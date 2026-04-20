import { useMemo } from 'react'
import Plot from '@/lib/plotly'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { TopCallsRow } from '@/components/CallsCharts'
import { CostTokenCombo } from '@/components/CostTokenCombo'
import { formatNumber, formatProjectName } from '@/lib/formatters'
import { CHART_COLORS } from '@/lib/chart-colors'
import type { SummaryData, TopProjectWeekly } from '@/lib/api-client'

export default function Dashboard() {
  const { buildApiQuery } = useFilters()
  const { mergeLayout } = usePlotlyTheme()
  const { data: summary, loading: summaryLoading } = useApi<SummaryData[]>(`/summary${buildApiQuery()}`)
  const { data: topProjectsData, loading: topProjectsLoading } = useApi<TopProjectWeekly[]>(
    `/usage/top-projects-weekly${buildApiQuery()}`
  )

  // Process top projects data (must be before early return - Rules of Hooks)
  const topProjectsAnalysis = useMemo(() => {
    if (!topProjectsData || topProjectsData.length === 0) {
      return { projects: [], weeks: [], projectColors: {}, projectData: {} }
    }

    // Get unique projects and weeks
    const projects = [...new Set(topProjectsData.map((d) => d.project_id))].sort()
    const weeks = [...new Set(topProjectsData.map((d) => d.time_bucket))].sort()

    // Define colors for projects using shared color palette
    const projectColors: Record<string, string> = {}
    projects.forEach((proj, i) => {
      projectColors[proj] = CHART_COLORS[i % CHART_COLORS.length]
    })

    // Organize data by project
    const projectData: Record<
      string,
      {
        weeks: string[]
        costs: number[]
        tokens: number[]
        sessions: number[]
        totalCost: number
        totalTokens: number
        totalSessions: number
        tokensPerSession: number
        sessionsPerDay: number
      }
    > = {}

    projects.forEach((proj) => {
      const projRows = topProjectsData.filter((d) => d.project_id === proj)
      const totalCost = projRows.reduce((sum, d) => sum + d.cost_usd, 0)
      const totalTokens = projRows.reduce((sum, d) => sum + d.total_tokens, 0)
      const totalSessions = projRows.reduce((sum, d) => sum + d.session_count, 0)

      // Calculate sessions per day (8 weeks = 56 days)
      const numberOfDays = weeks.length * 7

      projectData[proj] = {
        weeks: projRows.map((d) => d.time_bucket).sort(),
        costs: projRows.sort((a, b) => a.time_bucket.localeCompare(b.time_bucket)).map((d) => d.cost_usd),
        tokens: projRows.sort((a, b) => a.time_bucket.localeCompare(b.time_bucket)).map((d) => d.total_tokens),
        sessions: projRows.sort((a, b) => a.time_bucket.localeCompare(b.time_bucket)).map((d) => d.session_count),
        totalCost,
        totalTokens,
        totalSessions,
        tokensPerSession: totalTokens / totalSessions,
        sessionsPerDay: totalSessions / numberOfDays,
      }
    })

    return { projects, weeks, projectColors, projectData }
  }, [topProjectsData])


  // Early return after all hooks
  if (summaryLoading || topProjectsLoading) {
    return <div className="text-center py-8">Loading...</div>
  }

  const summaryData = summary?.[0]

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Dashboard</h1>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Cost</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-green-600">${summaryData?.grand_total_cost_usd?.toFixed(2) || '0.00'}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Projects</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-blue-600">{summaryData?.total_projects || 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Input Tokens</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-purple-600">
              {((summaryData?.total_input_tokens || 0) / 1000000).toFixed(2)}M
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Output Tokens</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-orange-600">
              {((summaryData?.total_output_tokens || 0) / 1000000).toFixed(2)}M
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Top call dimensions — quick-glance ranking of skills, sub-agents,
          and CLI commands. Lives right under the summary KPI cards so the
          Dashboard opens with a one-screen "what's going on" view. */}
      <TopCallsRow />

      {/* Hero: monthly costs + per-model diverging token bars, zero-aligned.
          Implementation lives in CostTokenCombo — the same component is
          reused on the Daily / Weekly / Monthly pages. */}
      <CostTokenCombo
        granularity="monthly"
        xAxisLabel="Month"
        title="Monthly Costs & Token Usage by Model"
      />

      {/* Top 3 Projects - Last 8 Weeks */}
      {topProjectsAnalysis.projects.length > 0 && (
        <>
          <h2 className="text-2xl font-bold mt-8">Top 3 Projects - Last 8 Weeks</h2>

          {/* Project Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {topProjectsAnalysis.projects.map((proj) => {
              const data = topProjectsAnalysis.projectData[proj]
              return (
                <Card key={proj} style={{ borderLeft: `4px solid ${topProjectsAnalysis.projectColors[proj]}` }}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">{formatProjectName(proj)}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div>
                      <p className="text-xs text-muted-foreground">Total Cost</p>
                      <p className="text-2xl font-bold" style={{ color: topProjectsAnalysis.projectColors[proj] }}>
                        ${data.totalCost.toFixed(2)}
                      </p>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div>
                        <p className="text-muted-foreground">Tokens</p>
                        <p className="font-semibold">{formatNumber(data.totalTokens)}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Sessions</p>
                        <p className="font-semibold">{data.totalSessions}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">$/Session</p>
                        <p className="font-semibold">${(data.totalCost / data.totalSessions).toFixed(2)}</p>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                      <div>
                        <p className="text-muted-foreground">Tokens/Session</p>
                        <p className="font-semibold">{formatNumber(data.tokensPerSession)}</p>
                      </div>
                      <div>
                        <p className="text-muted-foreground">Sessions/Day</p>
                        <p className="font-semibold">{data.sessionsPerDay.toFixed(1)}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>

          {/* Stacked Bar Chart - Weekly Costs by Project */}
          <Card>
            <CardHeader>
              <CardTitle>Weekly Costs by Project</CardTitle>
            </CardHeader>
            <CardContent>
              <Plot
                data={topProjectsAnalysis.projects.map((proj) => {
                  const data = topProjectsAnalysis.projectData[proj]
                  return {
                    x: data.weeks,
                    y: data.costs,
                    type: 'bar' as const,
                    name: formatProjectName(proj),
                    marker: { color: topProjectsAnalysis.projectColors[proj] },
                    hovertemplate: '%{x}<br>%{fullData.name}<br>$%{y:.2f}<extra></extra>',
                  }
                })}
                layout={mergeLayout({
                  autosize: true,
                  barmode: 'group',
                  margin: { l: 50, r: 200, t: 30, b: 80 },
                  xaxis: {
                    title: { text: 'Week Starting' },
                    tickangle: -45,
                  },
                  yaxis: { title: { text: 'Cost (USD)' } },
                  showlegend: true,
                })}
                useResizeHandler
                style={{ width: '100%', height: '450px' }}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
