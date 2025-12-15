import { useState, useMemo } from 'react'
import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface MonthlyData {
  project_id: string
  model_id: string
  time_bucket: string
  total_cost_usd: number
  session_count: number
  event_count: number
  total_input_tokens: number
  total_output_tokens: number
}

// Format large numbers in human-friendly format (e.g., 1.2M, 592k)
function formatNumber(num: number): string {
  if (num >= 1_000_000) {
    return (num / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M'
  }
  if (num >= 1_000) {
    return (num / 1_000).toFixed(0) + 'k'
  }
  return num.toString()
}

export default function MonthlyUsage() {
  const { data, loading, error } = useApi<MonthlyData[]>('/usage/monthly')
  const [selectedProject, setSelectedProject] = useState<string>('all')

  // Get unique projects
  const projects = useMemo(() => {
    if (!data) return []
    const uniqueProjects = [...new Set(data.map((d) => d.project_id))].sort()
    return uniqueProjects
  }, [data])

  // Format project name for display
  const formatProjectName = (name: string) => {
    return name.replace(/-Users-joshpeak-/, '').replace(/-/g, '/')
  }

  // Filter and aggregate data
  const { monthlyCosts, monthlyTokens, modelCosts, sortedMonths, costsByModel, tokensByModel, models } = useMemo(() => {
    const costs: Record<string, number> = {}
    const tokens: Record<string, { input: number; output: number }> = {}
    const modelTotalCosts: Record<string, number> = {}

    // For model-grouped charts (by month)
    const costsByModel: Record<string, Record<string, number>> = {}
    const tokensByModel: Record<string, Record<string, { input: number; output: number }>> = {}
    const uniqueModels = new Set<string>()

    const filteredData = selectedProject === 'all'
      ? data
      : data?.filter((row) => row.project_id === selectedProject)

    filteredData?.forEach((row) => {
      const month = row.time_bucket
      const model = row.model_id || 'unknown'

      // Aggregate totals (existing)
      costs[month] = (costs[month] || 0) + Number(row.total_cost_usd)
      modelTotalCosts[model] = (modelTotalCosts[model] || 0) + Number(row.total_cost_usd)
      if (!tokens[month]) {
        tokens[month] = { input: 0, output: 0 }
      }
      tokens[month].input += Number(row.total_input_tokens)
      tokens[month].output += Number(row.total_output_tokens)

      // Aggregate by model and month
      uniqueModels.add(model)
      if (!costsByModel[model]) costsByModel[model] = {}
      if (!tokensByModel[model]) tokensByModel[model] = {}

      costsByModel[model][month] = (costsByModel[model][month] || 0) + Number(row.total_cost_usd)
      if (!tokensByModel[model][month]) {
        tokensByModel[model][month] = { input: 0, output: 0 }
      }
      tokensByModel[model][month].input += Number(row.total_input_tokens)
      tokensByModel[model][month].output += Number(row.total_output_tokens)
    })

    const months = Object.keys(costs).sort()
    const modelsList = Array.from(uniqueModels).sort()

    return {
      monthlyCosts: costs,
      monthlyTokens: tokens,
      modelCosts: modelTotalCosts,
      sortedMonths: months,
      costsByModel,
      tokensByModel,
      models: modelsList
    }
  }, [data, selectedProject])

  // Calculate 3-month rolling average
  const rollingAverage = useMemo(() => {
    return sortedMonths.map((_, i) => {
      const start = Math.max(0, i - 2)
      const window = sortedMonths.slice(start, i + 1)
      const sum = window.reduce((acc, month) => acc + monthlyCosts[month], 0)
      return sum / window.length
    })
  }, [sortedMonths, monthlyCosts])

  const modelNames = Object.keys(modelCosts).sort((a, b) => modelCosts[b] - modelCosts[a])

  if (loading) return <div className="text-center py-8">Loading...</div>
  if (error) return <div className="text-center py-8 text-red-500">Error: {error}</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-900">Monthly Usage</h1>

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

      {/* Monthly Cost Chart */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">Monthly Costs (USD)</h2>
        <Plot
          data={[
            {
              x: sortedMonths,
              y: sortedMonths.map((m) => monthlyCosts[m]),
              type: 'bar',
              name: 'Monthly Cost',
              marker: { color: '#10B981' },
              text: sortedMonths.map((m) => Math.round(monthlyCosts[m]).toString()),
              textposition: 'outside',
              textfont: { color: '#333' },
              hovertemplate: '%{x}<br>$%{y:.2f}<extra></extra>',
            },
            {
              x: sortedMonths,
              y: rollingAverage,
              type: 'scatter',
              mode: 'lines',
              name: '3-month Average',
              line: { color: '#DC2626', width: 2 },
            },
          ]}
          layout={{
            autosize: true,
            margin: { l: 50, r: 30, t: 30, b: 50 },
            xaxis: { title: 'Month' },
            yaxis: { title: 'Cost (USD)', tickformat: 'd' },
            showlegend: true,
            legend: { x: 0, y: 1.1, orientation: 'h' },
          }}
          useResizeHandler
          style={{ width: '100%', height: '400px' }}
        />
      </div>

      {/* Token Usage Chart - Diverging */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">Token Usage</h2>
        <Plot
          data={[
            {
              x: sortedMonths,
              y: sortedMonths.map((m) => monthlyTokens[m]?.input || 0),
              type: 'bar',
              name: 'Input Tokens',
              marker: { color: '#8B5CF6' },
              text: sortedMonths.map((m) => formatNumber(monthlyTokens[m]?.input || 0)),
              textposition: 'outside',
              textfont: { color: '#333' },
              hovertemplate: '%{x}<br>Input: %{y:,}<extra></extra>',
            },
            {
              x: sortedMonths,
              y: sortedMonths.map((m) => -(monthlyTokens[m]?.output || 0)),
              type: 'bar',
              name: 'Output Tokens',
              marker: { color: '#F59E0B' },
              text: sortedMonths.map((m) => formatNumber(monthlyTokens[m]?.output || 0)),
              textposition: 'outside',
              textfont: { color: '#333' },
              hovertemplate: '%{x}<br>Output: %{customdata:,}<extra></extra>',
              customdata: sortedMonths.map((m) => monthlyTokens[m]?.output || 0),
            },
          ]}
          layout={{
            autosize: true,
            barmode: 'overlay',
            margin: { l: 60, r: 30, t: 30, b: 50 },
            xaxis: { title: 'Month' },
            yaxis: {
              title: 'Tokens',
              tickformat: ',d',
              tickprefix: '',
            },
            showlegend: true,
            legend: { x: 0, y: 1.1, orientation: 'h' },
          }}
          useResizeHandler
          style={{ width: '100%', height: '400px' }}
        />
      </div>

      {/* Costs by Model - Grouped Bar Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Monthly Costs by Model</CardTitle>
        </CardHeader>
        <CardContent>
          <Plot
            data={models.map((model, idx) => {
              const colors = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899']
              return {
                x: sortedMonths,
                y: sortedMonths.map((m) => costsByModel[model]?.[m] || 0),
                type: 'bar',
                name: model.replace('claude-', ''),
                marker: { color: colors[idx % colors.length] },
                text: sortedMonths.map((m) => {
                  const cost = costsByModel[model]?.[m] || 0
                  return cost > 0 ? `$${cost.toFixed(0)}` : ''
                }),
                textposition: 'inside',
                textfont: { size: 10 },
                hovertemplate: '%{x}<br>%{fullData.name}<br>$%{y:.2f}<extra></extra>',
              }
            })}
            layout={{
              autosize: true,
              barmode: 'stack',
              margin: { l: 50, r: 30, t: 30, b: 100 },
              xaxis: { title: 'Month', tickangle: -45 },
              yaxis: { title: 'Cost (USD)', tickformat: '$.2f' },
              showlegend: true,
              legend: { x: 0, y: 1.15, orientation: 'h' },
            }}
            useResizeHandler
            style={{ width: '100%', height: '450px' }}
          />
        </CardContent>
      </Card>

      {/* Tokens by Model - Grouped Bar Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Monthly Tokens by Model</CardTitle>
        </CardHeader>
        <CardContent>
          <Plot
            data={[
              // Input tokens (above the line)
              ...models.map((model, idx) => {
                const inputColors = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899']
                const maxInput = Math.max(...sortedMonths.map((m) => tokensByModel[model]?.[m]?.input || 0))
                return {
                  x: sortedMonths,
                  y: sortedMonths.map((m) => tokensByModel[model]?.[m]?.input || 0),
                  type: 'bar',
                  name: model.replace('claude-', '') + ' (input)',
                  marker: { color: inputColors[idx % inputColors.length] },
                  text: sortedMonths.map((m) => {
                    const input = tokensByModel[model]?.[m]?.input || 0
                    // Only show text if value is significant (>5% of max)
                    return input > maxInput * 0.05 ? formatNumber(input) : ''
                  }),
                  textposition: 'inside',
                  textfont: { size: 11 },
                  cliponaxis: false,
                  hovertemplate: '%{x}<br>%{fullData.name}<br>%{y:,} tokens<extra></extra>',
                  legendgroup: model,
                }
              }),
              // Output tokens (below the line)
              ...models.map((model, idx) => {
                const outputColors = ['#06B6D4', '#F97316', '#84CC16', '#A78BFA', '#FB923C', '#4ADE80']
                const maxOutput = Math.max(...sortedMonths.map((m) => tokensByModel[model]?.[m]?.output || 0))
                return {
                  x: sortedMonths,
                  y: sortedMonths.map((m) => -(tokensByModel[model]?.[m]?.output || 0)),
                  type: 'bar',
                  name: model.replace('claude-', '') + ' (output)',
                  marker: { color: outputColors[idx % outputColors.length] },
                  text: sortedMonths.map((m) => {
                    const output = tokensByModel[model]?.[m]?.output || 0
                    // Only show text if value is significant (>5% of max)
                    return output > maxOutput * 0.05 ? formatNumber(output) : ''
                  }),
                  textposition: 'inside',
                  textfont: { size: 11 },
                  cliponaxis: false,
                  hovertemplate: '%{x}<br>%{fullData.name}<br>%{customdata:,} tokens<extra></extra>',
                  customdata: sortedMonths.map((m) => tokensByModel[model]?.[m]?.output || 0),
                  legendgroup: model,
                }
              }),
            ]}
            layout={{
              autosize: true,
              barmode: 'relative',
              margin: { l: 60, r: 30, t: 30, b: 100 },
              xaxis: { title: 'Month', tickangle: -45 },
              yaxis: {
                title: 'Tokens',
                tickformat: ',d',
              },
              showlegend: true,
              legend: { x: 0, y: 1.15, orientation: 'h' },
            }}
            useResizeHandler
            style={{ width: '100%', height: '450px' }}
          />
        </CardContent>
      </Card>

      {/* Model Distribution Pie Chart */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">Total Cost by Model</h2>
        <Plot
          data={[
            {
              labels: modelNames,
              values: modelNames.map((m) => modelCosts[m]),
              type: 'pie',
              hole: 0.4,
              marker: {
                colors: ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'],
              },
              hovertemplate: '%{label}<br>$%{value:.2f}<extra></extra>',
            },
          ]}
          layout={{
            autosize: true,
            margin: { l: 30, r: 30, t: 30, b: 30 },
          }}
          useResizeHandler
          style={{ width: '100%', height: '400px' }}
        />
      </div>
    </div>
  )
}
