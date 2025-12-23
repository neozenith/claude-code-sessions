import { useState, useMemo } from 'react'
import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface HourlyData {
  project_id: string
  time_bucket: string
  hour_of_day: number
  total_cost_usd: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  session_count: number
  event_count: number
}

export default function HourlyUsage() {
  const { data: hourly, loading } = useApi<HourlyData[]>('/usage/hourly')
  const [selectedProject, setSelectedProject] = useState<string>('all')

  // Get unique projects
  const projects = useMemo(() => {
    if (!hourly) return []
    const uniqueProjects = [...new Set(hourly.map((d) => d.project_id))].sort()
    return uniqueProjects
  }, [hourly])

  // Format project name for display
  const formatProjectName = (name: string) => {
    return name.replace(/-Users-joshpeak-/, '').replace(/-/g, '/')
  }

  // Filter data by selected project
  const filteredHourly = useMemo(() => {
    if (!hourly) return []
    if (selectedProject === 'all') return hourly
    return hourly.filter((d) => d.project_id === selectedProject)
  }, [hourly, selectedProject])

  // Transform data into heatmap format
  const heatmapData = useMemo(() => {
    if (!filteredHourly || filteredHourly.length === 0) {
      return null
    }

    // Get unique dates and sort them (oldest to newest for left-to-right display)
    const dates = [...new Set(filteredHourly.map((d) => d.time_bucket))].sort()
    const hours = Array.from({ length: 24 }, (_, i) => i)

    // Create 2D arrays for each metric (24 hours x N days)
    const createMatrix = (metric: keyof HourlyData) => {
      const matrix: number[][] = []
      for (let hour = 0; hour < 24; hour++) {
        const row: number[] = []
        for (const date of dates) {
          const dataPoint = filteredHourly.find(
            (d) => d.time_bucket === date && d.hour_of_day === hour
          )
          row.push(dataPoint ? Number(dataPoint[metric]) : 0)
        }
        matrix.push(row)
      }
      return matrix
    }

    return {
      dates,
      hours,
      cost: createMatrix('total_cost_usd'),
      totalTokens: createMatrix('total_tokens'),
      inputTokens: createMatrix('input_tokens'),
      outputTokens: createMatrix('output_tokens'),
      sessions: createMatrix('session_count'),
      events: createMatrix('event_count'),
    }
  }, [filteredHourly])

  if (loading) {
    return <div className="text-center py-8">Loading...</div>
  }

  if (!heatmapData) {
    return <div className="text-center py-8">No hourly data available</div>
  }

  const commonLayout = {
    autosize: true,
    margin: { l: 60, r: 20, t: 40, b: 80 },
    xaxis: {
      title: 'Date',
      tickangle: -45,
      side: 'bottom' as const,
    },
    yaxis: {
      title: 'Hour of Day',
      autorange: 'reversed' as const,
      tickvals: [0, 3, 6, 9, 12, 15, 18, 21, 23],
    },
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Hourly Usage Patterns - Last 14 Days</h1>

        {/* Project Filter */}
        <select
          value={selectedProject}
          onChange={(e) => setSelectedProject(e.target.value)}
          className="px-3 py-2 border rounded-lg bg-white text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="all">All Projects</option>
          {projects.map((project) => (
            <option key={project} value={project}>
              {formatProjectName(project)}
            </option>
          ))}
        </select>
      </div>

      {/* Total Cost Heatmap */}
      <Card>
        <CardHeader>
          <CardTitle>Cost by Hour (USD)</CardTitle>
        </CardHeader>
        <CardContent>
          <Plot
            data={[
              {
                z: heatmapData.cost,
                x: heatmapData.dates,
                y: heatmapData.hours,
                type: 'heatmap',
                colorscale: [
                  [0, 'white'],
                  [0.01, '#e8f5e9'],
                  [0.05, '#c8e6c9'],
                  [0.1, '#a5d6a7'],
                  [0.2, '#81c784'],
                  [0.4, '#66bb6a'],
                  [0.6, '#4caf50'],
                  [0.8, '#43a047'],
                  [1, '#10B981'],
                ],
                hovertemplate: 'Date: %{x}<br>Hour: %{y}<br>Cost: $%{z:.2f}<extra></extra>',
              },
            ]}
            layout={commonLayout}
            useResizeHandler
            style={{ width: '100%', height: '500px' }}
          />
        </CardContent>
      </Card>

      {/* Total Tokens Heatmap */}
      <Card>
        <CardHeader>
          <CardTitle>Total Tokens by Hour</CardTitle>
        </CardHeader>
        <CardContent>
          <Plot
            data={[
              {
                z: heatmapData.totalTokens,
                x: heatmapData.dates,
                y: heatmapData.hours,
                type: 'heatmap',
                colorscale: [
                  [0, 'white'],
                  [0.01, '#e3f2fd'],
                  [0.05, '#bbdefb'],
                  [0.1, '#90caf9'],
                  [0.2, '#64b5f6'],
                  [0.4, '#42a5f5'],
                  [0.6, '#2196f3'],
                  [0.8, '#1e88e5'],
                  [1, '#3B82F6'],
                ],
                hovertemplate: 'Date: %{x}<br>Hour: %{y}<br>Tokens: %{z:,.0f}<extra></extra>',
              },
            ]}
            layout={commonLayout}
            useResizeHandler
            style={{ width: '100%', height: '500px' }}
          />
        </CardContent>
      </Card>

      {/* Input vs Output Tokens Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Input Tokens Heatmap */}
        <Card>
          <CardHeader>
            <CardTitle>Input Tokens by Hour</CardTitle>
          </CardHeader>
          <CardContent>
            <Plot
              data={[
                {
                  z: heatmapData.inputTokens,
                  x: heatmapData.dates,
                  y: heatmapData.hours,
                  type: 'heatmap',
                  colorscale: [
                    [0, 'white'],
                    [0.01, '#f3e5f5'],
                    [0.05, '#e1bee7'],
                    [0.1, '#ce93d8'],
                    [0.2, '#ba68c8'],
                    [0.4, '#ab47bc'],
                    [0.6, '#9c27b0'],
                    [0.8, '#8e24aa'],
                    [1, '#8B5CF6'],
                  ],
                  hovertemplate: 'Date: %{x}<br>Hour: %{y}<br>Input: %{z:,.0f}<extra></extra>',
                },
              ]}
              layout={commonLayout}
              useResizeHandler
              style={{ width: '100%', height: '500px' }}
            />
          </CardContent>
        </Card>

        {/* Output Tokens Heatmap */}
        <Card>
          <CardHeader>
            <CardTitle>Output Tokens by Hour</CardTitle>
          </CardHeader>
          <CardContent>
            <Plot
              data={[
                {
                  z: heatmapData.outputTokens,
                  x: heatmapData.dates,
                  y: heatmapData.hours,
                  type: 'heatmap',
                  colorscale: [
                    [0, 'white'],
                    [0.01, '#fff3e0'],
                    [0.05, '#ffe0b2'],
                    [0.1, '#ffcc80'],
                    [0.2, '#ffb74d'],
                    [0.4, '#ffa726'],
                    [0.6, '#ff9800'],
                    [0.8, '#fb8c00'],
                    [1, '#F59E0B'],
                  ],
                  hovertemplate: 'Date: %{x}<br>Hour: %{y}<br>Output: %{z:,.0f}<extra></extra>',
                },
              ]}
              layout={commonLayout}
              useResizeHandler
              style={{ width: '100%', height: '500px' }}
            />
          </CardContent>
        </Card>
      </div>

      {/* Sessions and Events Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Sessions Heatmap */}
        <Card>
          <CardHeader>
            <CardTitle>Active Sessions by Hour</CardTitle>
          </CardHeader>
          <CardContent>
            <Plot
              data={[
                {
                  z: heatmapData.sessions,
                  x: heatmapData.dates,
                  y: heatmapData.hours,
                  type: 'heatmap',
                  colorscale: [
                    [0, 'white'],
                    [0.01, '#ffebee'],
                    [0.05, '#ffcdd2'],
                    [0.1, '#ef9a9a'],
                    [0.2, '#e57373'],
                    [0.4, '#ef5350'],
                    [0.6, '#f44336'],
                    [0.8, '#e53935'],
                    [1, '#EF4444'],
                  ],
                  hovertemplate: 'Date: %{x}<br>Hour: %{y}<br>Sessions: %{z}<extra></extra>',
                },
              ]}
              layout={commonLayout}
              useResizeHandler
              style={{ width: '100%', height: '500px' }}
            />
          </CardContent>
        </Card>

        {/* Events Heatmap */}
        <Card>
          <CardHeader>
            <CardTitle>Events by Hour</CardTitle>
          </CardHeader>
          <CardContent>
            <Plot
              data={[
                {
                  z: heatmapData.events,
                  x: heatmapData.dates,
                  y: heatmapData.hours,
                  type: 'heatmap',
                  colorscale: [
                    [0, 'white'],
                    [0.01, '#e0f7fa'],
                    [0.05, '#b2ebf2'],
                    [0.1, '#80deea'],
                    [0.2, '#4dd0e1'],
                    [0.4, '#26c6da'],
                    [0.6, '#00bcd4'],
                    [0.8, '#00acc1'],
                    [1, '#06B6D4'],
                  ],
                  hovertemplate: 'Date: %{x}<br>Hour: %{y}<br>Events: %{z}<extra></extra>',
                },
              ]}
              layout={commonLayout}
              useResizeHandler
              style={{ width: '100%', height: '500px' }}
            />
          </CardContent>
        </Card>
      </div>

    </div>
  )
}
