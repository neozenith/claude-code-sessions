import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatNumber, formatProjectName } from '@/lib/formatters'
import { CHART_COLORS, COST_COLOR } from '@/lib/chart-colors'
import type { SummaryData, UsageData, TopProjectWeekly } from '@/lib/api-client'

export default function Dashboard() {
  const { filters, buildApiQuery } = useFilters()
  const { colors, mergeLayout } = usePlotlyTheme()
  const { data: summary, loading: summaryLoading } = useApi<SummaryData[]>(`/summary${buildApiQuery()}`)
  const { data: monthly, loading: monthlyLoading } = useApi<UsageData[]>(`/usage/monthly${buildApiQuery()}`)
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

  // Filter monthly data by project if selected
  const filteredMonthly = useMemo(() => {
    if (!monthly) return []
    if (!filters.project) return monthly
    return monthly.filter((row) => row.project_id === filters.project)
  }, [monthly, filters.project])

  // Aggregate monthly costs and token usage by model
  const { monthlyCosts, tokensByModel, models, sortedMonths } = useMemo(() => {
    const costs: Record<string, number> = {}
    const byModel: Record<string, Record<string, number>> = {}
    const uniqueModels = new Set<string>()

    filteredMonthly.forEach((row) => {
      const month = row.time_bucket
      const model = row.model_id || 'unknown'

      costs[month] = (costs[month] || 0) + Number(row.total_cost_usd)

      uniqueModels.add(model)
      if (!byModel[model]) byModel[model] = {}
      byModel[model][month] = (byModel[model][month] || 0) +
        Number(row.total_input_tokens) + Number(row.total_output_tokens)
    })

    return {
      monthlyCosts: costs,
      tokensByModel: byModel,
      models: Array.from(uniqueModels).sort(),
      sortedMonths: Object.keys(costs).sort(),
    }
  }, [filteredMonthly])

  // Early return after all hooks
  if (summaryLoading || monthlyLoading || topProjectsLoading) {
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

      {/* Monthly Costs + Token Usage Combo Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Monthly Costs &amp; Token Usage by Model</CardTitle>
        </CardHeader>
        <CardContent>
          <Plot
            data={[
              // Stacked bar traces for token usage per model (primary y-axis)
              ...models.map((model, idx) => ({
                x: sortedMonths,
                y: sortedMonths.map((m) => tokensByModel[model]?.[m] || 0),
                type: 'bar' as const,
                name: model.replace('claude-', ''),
                marker: { color: CHART_COLORS[idx % CHART_COLORS.length] },
                text: sortedMonths.map((m) => formatNumber(tokensByModel[model]?.[m] || 0)),
                textposition: 'inside' as const,
                textfont: { size: 10 },
                hovertemplate: '%{x}<br>%{fullData.name}<br>%{y:,} tokens<extra></extra>',
              })),
              // Area chart for monthly cost (secondary y-axis, layered on top)
              {
                x: sortedMonths,
                y: sortedMonths.map((m) => monthlyCosts[m]),
                type: 'scatter' as const,
                mode: 'text+lines' as const,
                name: 'Cost (USD)',
                fill: 'tozeroy' as const,
                fillcolor: 'rgba(16, 185, 129, 0.15)',
                line: { color: COST_COLOR, width: 2.5 },
                text: sortedMonths.map((m) => `$${monthlyCosts[m].toFixed(0)}`),
                textposition: 'top center' as const,
                textfont: { color: COST_COLOR, size: 11, weight: 600 },
                yaxis: 'y2' as const,
                hovertemplate: '%{x}<br>$%{y:.2f}<extra></extra>',
              },
            ]}
            layout={mergeLayout({
              autosize: true,
              margin: { l: 70, r: 140, t: 30, b: 50 },
              xaxis: { title: { text: 'Month' } },
              yaxis: { title: { text: 'Total Tokens' }, tickformat: ',.0s' },
              yaxis2: {
                title: { text: 'Cost (USD)' },
                overlaying: 'y',
                side: 'right',
                tickprefix: '$',
                color: colors.text,
                gridcolor: 'transparent',
              },
              showlegend: true,
              legend: { x: 1.12, y: 1, orientation: 'v' as const, xanchor: 'left' as const },
              barmode: 'stack',
            })}
            useResizeHandler
            style={{ width: '100%', height: '400px' }}
          />
        </CardContent>
      </Card>

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
                  margin: { l: 50, r: 30, t: 30, b: 80 },
                  xaxis: {
                    title: { text: 'Week Starting' },
                    tickangle: -45,
                  },
                  yaxis: { title: { text: 'Cost (USD)' } },
                  showlegend: true,
                  legend: {
                    orientation: 'h',
                    y: -0.2,
                    x: 0.5,
                    xanchor: 'center',
                  },
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
