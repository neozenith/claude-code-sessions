import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { HourlyData } from '@/lib/api-client'

export default function HourOfDay() {
  const { filters, buildApiQuery } = useFilters()
  const { mergeLayout, colors } = usePlotlyTheme()
  const { data: hourly, loading } = useApi<HourlyData[]>(`/usage/hourly${buildApiQuery()}`)

  // Filter data by selected project (client-side)
  const filteredHourly = useMemo(() => {
    if (!hourly) return []
    if (!filters.project) return hourly
    return hourly.filter((d) => d.project_id === filters.project)
  }, [hourly, filters.project])

  // Transform data for polar charts (Day of Week x Hour of Day)
  const polarData = useMemo(() => {
    if (!filteredHourly || filteredHourly.length === 0) {
      return null
    }

    // Create matrices for averaging by day-of-week and hour-of-day
    const createPolarMatrix = (metric: keyof HourlyData) => {
      // Initialize accumulator: [day-of-week][hour-of-day]
      const sums: number[][] = Array(7)
        .fill(0)
        .map(() => Array(24).fill(0))
      const counts: number[][] = Array(7)
        .fill(0)
        .map(() => Array(24).fill(0))

      filteredHourly.forEach((d) => {
        const date = new Date(d.time_bucket)
        const dow = date.getDay() // 0 = Sunday, 6 = Saturday
        const hour = d.hour_of_day
        const value = Number(d[metric]) || 0

        if (value > 0) {
          sums[dow][hour] += value
          counts[dow][hour] += 1
        }
      })

      // Calculate averages and flatten for polar plotting
      const theta: number[] = [] // Day of week (in degrees)
      const r: number[] = [] // Hour of day (radius)
      const values: number[] = [] // Metric values

      // Map day of week to clockwise order starting with Monday at 0° (12 o'clock)
      // JS getDay(): 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
      // New order: Mon=0°, Tue=51.43°, Wed=102.86°, Thu=154.29°, Fri=205.71°, Sat=257.14°, Sun=308.57°
      const dowToAngle = (dow: number) => {
        // Map dow to position: [Sun, Mon, Tue, Wed, Thu, Fri, Sat]
        const angleMap = [308.57, 0, 51.43, 102.86, 154.29, 205.71, 257.14]
        return angleMap[dow]
      }

      for (let dow = 0; dow < 7; dow++) {
        for (let hour = 0; hour < 24; hour++) {
          const angle = dowToAngle(dow)
          if (counts[dow][hour] > 0) {
            theta.push(angle)
            r.push(hour)
            values.push(sums[dow][hour] / counts[dow][hour]) // Average
          } else {
            theta.push(angle)
            r.push(hour)
            values.push(0)
          }
        }
      }

      return {
        theta,
        r,
        values,
        dow: Array(7 * 24)
          .fill(0)
          .map((_, i) => Math.floor(i / 24)),
      }
    }

    return {
      cost: createPolarMatrix('total_cost_usd'),
      totalTokens: createPolarMatrix('total_tokens'),
      inputTokens: createPolarMatrix('input_tokens'),
      outputTokens: createPolarMatrix('output_tokens'),
      sessions: createPolarMatrix('session_count'),
      events: createPolarMatrix('event_count'),
    }
  }, [filteredHourly])

  if (loading) {
    return <div className="text-center py-8">Loading...</div>
  }

  if (!polarData) {
    return <div className="text-center py-8">No hourly data available</div>
  }

  // Theme-aware grid color
  const gridColor = colors.gridColor

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Hour of Day Analysis</h1>

      <p className="text-sm text-muted-foreground">
        Polar charts showing average metrics by day of week and hour of day. Angular segments = Day of Week, Concentric
        rings = Hour of Day (0-23).
      </p>

      {/* Polar Charts - Day of Week x Hour of Day */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Cost Polar Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Average Cost by Day of Week & Hour</CardTitle>
          </CardHeader>
          <CardContent>
            <Plot
              data={Array.from({ length: 24 }, (_, hour) => {
                // For each hour, create a trace across all days of week
                const dayAngles = [0, 51.43, 102.86, 154.29, 205.71, 257.14, 308.57]
                const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

                // Get actual values for color/opacity
                const actualValues = dayAngles.map((angle) => {
                  const idx = polarData.cost.theta.findIndex((t, i) => {
                    const thetaMatch = Math.abs(t - angle) < 0.1
                    const rMatch = polarData.cost.r[i] === hour
                    return thetaMatch && rMatch
                  })
                  return idx !== -1 ? polarData.cost.values[idx] : 0
                })

                const maxValue = Math.max(...polarData.cost.values)

                return {
                  type: 'barpolar' as const,
                  r: Array(7).fill(1), // Always render with height 1 to maintain spacing
                  theta: dayNames,
                  name: `${hour}:00`,
                  marker: {
                    color: actualValues,
                    colorscale: [
                      [0, 'rgba(16, 185, 129, 0)'],
                      [1, 'rgba(16, 185, 129, 1)'],
                    ],
                    cmin: 0,
                    cmax: maxValue,
                    showscale: hour === 23, // Only show colorbar on last trace
                    colorbar: {
                      title: 'Avg Cost<br>(USD)',
                      x: 1.1,
                      len: 0.7,
                      tickfont: { color: colors.text },
                      titlefont: { color: colors.text },
                    },
                    line: {
                      color: 'rgba(255, 255, 255, 0.3)',
                      width: 0.5,
                    },
                  },
                  customdata: actualValues,
                  hovertemplate: `Hour ${hour}:00<br>%{theta}<br>Avg Cost: $%{customdata:.2f}<extra></extra>`,
                  showlegend: false,
                }
              })}
              layout={mergeLayout({
                barmode: 'stack',
                bargap: 0,
                polar: {
                  radialaxis: {
                    title: { text: 'Avg Cost (USD)', font: { color: colors.text } },
                    gridcolor: gridColor,
                    color: colors.text,
                  },
                  angularaxis: {
                    direction: 'clockwise',
                    color: colors.text,
                  },
                  bgcolor: 'transparent',
                },
                showlegend: false,
              })}
              useResizeHandler
              style={{ width: '100%', height: '500px' }}
            />
          </CardContent>
        </Card>

        {/* Total Tokens Polar Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Average Tokens by Day of Week & Hour</CardTitle>
          </CardHeader>
          <CardContent>
            <Plot
              data={Array.from({ length: 24 }, (_, hour) => {
                // For each hour, create a trace across all days of week
                const dayAngles = [0, 51.43, 102.86, 154.29, 205.71, 257.14, 308.57]
                const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

                // Get actual values for color/opacity
                const actualValues = dayAngles.map((angle) => {
                  const idx = polarData.totalTokens.theta.findIndex((t, i) => {
                    const thetaMatch = Math.abs(t - angle) < 0.1
                    const rMatch = polarData.totalTokens.r[i] === hour
                    return thetaMatch && rMatch
                  })
                  return idx !== -1 ? polarData.totalTokens.values[idx] : 0
                })

                const maxValue = Math.max(...polarData.totalTokens.values)

                return {
                  type: 'barpolar' as const,
                  r: Array(7).fill(1), // Always render with height 1 to maintain spacing
                  theta: dayNames,
                  name: `${hour}:00`,
                  marker: {
                    color: actualValues,
                    colorscale: [
                      [0, 'rgba(59, 130, 246, 0)'],
                      [1, 'rgba(59, 130, 246, 1)'],
                    ],
                    cmin: 0,
                    cmax: maxValue,
                    showscale: hour === 23, // Only show colorbar on last trace
                    colorbar: {
                      title: { text: 'Avg Tokens' },
                      x: 1.1,
                      len: 0.7,
                      tickfont: { color: colors.text },
                      titlefont: { color: colors.text },
                    },
                    line: {
                      color: 'rgba(255, 255, 255, 0.3)',
                      width: 0.5,
                    },
                  },
                  customdata: actualValues,
                  hovertemplate: `Hour ${hour}:00<br>%{theta}<br>Avg Tokens: %{customdata:,.0f}<extra></extra>`,
                  showlegend: false,
                }
              })}
              layout={mergeLayout({
                barmode: 'stack',
                bargap: 0,
                polar: {
                  radialaxis: {
                    title: { text: 'Avg Tokens', font: { color: colors.text } },
                    gridcolor: gridColor,
                    color: colors.text,
                  },
                  angularaxis: {
                    direction: 'clockwise',
                    color: colors.text,
                  },
                  bgcolor: 'transparent',
                },
                showlegend: false,
              })}
              useResizeHandler
              style={{ width: '100%', height: '500px' }}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
