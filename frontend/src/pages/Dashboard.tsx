import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface SummaryData {
  summary_level: string
  total_projects: number
  total_events: number
  total_input_tokens: number
  total_output_tokens: number
  grand_total_cost_usd: number
}

interface MonthlyData {
  project_id: string
  model_id: string
  time_bucket: string
  total_cost_usd: number
  session_count: number
  event_count: number
}

interface TopProjectWeekly {
  project_id: string
  time_bucket: string
  cost_usd: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  session_count: number
  event_count: number
  cost_per_session: number
}

// Format project name for display
const formatProjectName = (name: string) => {
  return name.replace(/-Users-joshpeak-/, '').replace(/-/g, '/')
}

// Format large numbers
const formatNumber = (num: number): string => {
  if (num >= 1_000_000) {
    return (num / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M'
  }
  if (num >= 1_000) {
    return (num / 1_000).toFixed(0) + 'k'
  }
  return num.toString()
}

export default function Dashboard() {
  const { filters, buildApiQuery } = useFilters()
  const { mergeLayout } = usePlotlyTheme()
  const { data: summary, loading: summaryLoading } = useApi<SummaryData[]>(`/summary${buildApiQuery()}`)
  const { data: monthly, loading: monthlyLoading } = useApi<MonthlyData[]>(`/usage/monthly${buildApiQuery()}`)
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

    // Define colors for projects (matching our existing color scheme)
    const chartColors = ['#10B981', '#8B5CF6', '#F59E0B']
    const projectColors: Record<string, string> = {}
    projects.forEach((proj, i) => {
      projectColors[proj] = chartColors[i % chartColors.length]
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

  // Early return after all hooks
  if (summaryLoading || monthlyLoading || topProjectsLoading) {
    return <div className="text-center py-8">Loading...</div>
  }

  const summaryData = summary?.[0]

  // Aggregate monthly costs
  const monthlyCosts: Record<string, number> = {}
  filteredMonthly.forEach((row) => {
    const month = row.time_bucket
    monthlyCosts[month] = (monthlyCosts[month] || 0) + Number(row.total_cost_usd)
  })

  const sortedMonths = Object.keys(monthlyCosts).sort()

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

      {/* Monthly Costs Table */}
      <Card>
        <CardHeader>
          <CardTitle>Monthly Costs</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">Month</th>
                  <th className="text-right py-3 px-4 font-medium">Cost (USD)</th>
                </tr>
              </thead>
              <tbody>
                {sortedMonths.map((month) => (
                  <tr key={month} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="py-3 px-4">{month}</td>
                    <td className="py-3 px-4 text-right font-mono">${monthlyCosts[month].toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
