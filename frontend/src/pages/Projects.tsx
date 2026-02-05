import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatProjectName } from '@/lib/formatters'
import { generateHslColors } from '@/lib/chart-colors'
import type { HourlyData } from '@/lib/api-client'

interface ProjectData {
  project_id: string
  total_cost_usd: number
  session_count: number
  event_count: number
  total_tokens: number
}

export default function Projects() {
  const { buildApiQuery } = useFilters()
  const { mergeLayout } = usePlotlyTheme()
  const { data: hourlyData, loading, error } = useApi<HourlyData[]>(`/usage/hourly${buildApiQuery()}`)

  // Aggregate hourly data by project
  const sortedProjects = useMemo(() => {
    if (!hourlyData) return []

    const projectMap = new Map<string, ProjectData>()

    hourlyData.forEach((d) => {
      const existing = projectMap.get(d.project_id)
      if (existing) {
        existing.total_cost_usd += Number(d.total_cost_usd) || 0
        existing.session_count += Number(d.session_count) || 0
        existing.event_count += Number(d.event_count) || 0
        existing.total_tokens += Number(d.total_tokens) || 0
      } else {
        projectMap.set(d.project_id, {
          project_id: d.project_id,
          total_cost_usd: Number(d.total_cost_usd) || 0,
          session_count: Number(d.session_count) || 0,
          event_count: Number(d.event_count) || 0,
          total_tokens: Number(d.total_tokens) || 0,
        })
      }
    })

    // Sort by cost (most expensive first)
    return Array.from(projectMap.values()).sort((a, b) => b.total_cost_usd - a.total_cost_usd)
  }, [hourlyData])

  if (loading) return <div className="text-center py-8">Loading...</div>
  if (error) return <div className="text-center py-8 text-red-500">Error: {error}</div>

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Projects</h1>

      {/* Projects Bar Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Cost by Project</CardTitle>
        </CardHeader>
        <CardContent>
          <Plot
            data={[
              {
                // Reverse for chart: Plotly renders horizontal bars bottom-to-top
                x: [...sortedProjects].reverse().map((p) => Number(p.total_cost_usd)),
                y: [...sortedProjects].reverse().map((p) => formatProjectName(p.project_id)),
                type: 'bar' as const,
                orientation: 'h' as const,
                marker: {
                  color: generateHslColors(sortedProjects.length).reverse(),
                },
              },
            ]}
            layout={mergeLayout({
              autosize: true,
              margin: { l: 200, r: 30, t: 30, b: 50 },
              xaxis: { title: { text: 'Cost (USD)' } },
              yaxis: { automargin: true },
            })}
            useResizeHandler
            style={{ width: '100%', height: `${Math.max(400, sortedProjects.length * 40)}px` }}
          />
        </CardContent>
      </Card>

      {/* Projects Table */}
      <Card>
        <CardHeader>
          <CardTitle>Project Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-3 px-4 font-medium">Project</th>
                  <th className="text-right py-3 px-4 font-medium">Cost (USD)</th>
                  <th className="text-right py-3 px-4 font-medium">Sessions</th>
                  <th className="text-right py-3 px-4 font-medium">Events</th>
                  <th className="text-right py-3 px-4 font-medium">Tokens</th>
                </tr>
              </thead>
              <tbody>
                {sortedProjects.map((project) => (
                  <tr key={project.project_id} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="py-3 px-4">{formatProjectName(project.project_id)}</td>
                    <td className="py-3 px-4 text-right font-mono">${Number(project.total_cost_usd).toFixed(2)}</td>
                    <td className="py-3 px-4 text-right">{project.session_count.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right">{project.event_count.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right">{project.total_tokens.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
