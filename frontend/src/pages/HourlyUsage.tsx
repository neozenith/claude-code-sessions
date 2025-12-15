import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface HourlyData {
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

  // Transform data for polar charts (Day of Week x Hour of Day)
  const polarData = useMemo(() => {
    if (!hourly || hourly.length === 0) {
      return null
    }

    // Create matrices for averaging by day-of-week and hour-of-day
    const createPolarMatrix = (metric: keyof HourlyData) => {
      // Initialize accumulator: [day-of-week][hour-of-day]
      const sums: number[][] = Array(7).fill(0).map(() => Array(24).fill(0))
      const counts: number[][] = Array(7).fill(0).map(() => Array(24).fill(0))

      hourly.forEach((d) => {
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

      return { theta, r, values, dow: Array(7 * 24).fill(0).map((_, i) => Math.floor(i / 24)) }
    }

    return {
      cost: createPolarMatrix('total_cost_usd'),
      totalTokens: createPolarMatrix('total_tokens'),
      inputTokens: createPolarMatrix('input_tokens'),
      outputTokens: createPolarMatrix('output_tokens'),
      sessions: createPolarMatrix('session_count'),
      events: createPolarMatrix('event_count'),
    }
  }, [hourly])

  // Transform data into heatmap format
  const heatmapData = useMemo(() => {
    if (!hourly || hourly.length === 0) {
      return null
    }

    // Get unique dates and sort them (oldest to newest for left-to-right display)
    const dates = [...new Set(hourly.map((d) => d.time_bucket))].sort()
    const hours = Array.from({ length: 24 }, (_, i) => i)

    // Create 2D arrays for each metric (24 hours x N days)
    const createMatrix = (metric: keyof HourlyData) => {
      const matrix: number[][] = []
      for (let hour = 0; hour < 24; hour++) {
        const row: number[] = []
        for (const date of dates) {
          const dataPoint = hourly.find(
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
  }, [hourly])

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
      <h1 className="text-3xl font-bold">Hourly Usage Patterns - Last 14 Days</h1>

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

      {/* Polar Charts - Day of Week x Hour of Day */}
      {polarData && (
        <>
          <h2 className="text-2xl font-bold mt-12">Average Usage by Day of Week and Hour</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Polar charts showing average metrics. Angular segments = Day of Week, Concentric rings = Hour of Day (0-23).
          </p>

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

                      // Find max value for normalization
                      const maxValue = Math.max(...polarData.cost.values)

                      // Create colors based on actual values
                      const colors = actualValues.map(val => {
                        const intensity = maxValue > 0 ? val / maxValue : 0
                        return `rgba(16, 185, 129, ${intensity})`
                      })

                      return {
                        type: 'barpolar',
                        r: Array(7).fill(1), // Always render with height 1 to maintain spacing
                        theta: dayNames,
                        name: `${hour}:00`,
                        marker: {
                          color: actualValues,
                          colorscale: [[0, 'rgba(16, 185, 129, 0)'], [1, 'rgba(16, 185, 129, 1)']],
                          cmin: 0,
                          cmax: Math.max(...polarData.cost.values),
                          showscale: hour === 23, // Only show colorbar on last trace
                          colorbar: {
                            title: 'Avg Cost<br>(USD)',
                            x: 1.1,
                            len: 0.7,
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
                  layout={{
                    polar: {
                      barmode: 'stack',
                      radialaxis: {
                        title: 'Avg Cost (USD)',
                        gridcolor: 'rgba(200, 200, 200, 0.3)',
                      },
                      angularaxis: {
                        direction: 'clockwise',
                      },
                      bargap: 0,
                    },
                    showlegend: false,
                  }}
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

                      // Find max value for normalization
                      const maxValue = Math.max(...polarData.totalTokens.values)

                      // Create colors based on actual values
                      const colors = actualValues.map(val => {
                        const intensity = maxValue > 0 ? val / maxValue : 0
                        return `rgba(59, 130, 246, ${intensity})`
                      })

                      return {
                        type: 'barpolar',
                        r: Array(7).fill(1), // Always render with height 1 to maintain spacing
                        theta: dayNames,
                        name: `${hour}:00`,
                        marker: {
                          color: actualValues,
                          colorscale: [[0, 'rgba(59, 130, 246, 0)'], [1, 'rgba(59, 130, 246, 1)']],
                          cmin: 0,
                          cmax: Math.max(...polarData.totalTokens.values),
                          showscale: hour === 23, // Only show colorbar on last trace
                          colorbar: {
                            title: 'Avg Tokens',
                            x: 1.1,
                            len: 0.7,
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
                  layout={{
                    polar: {
                      barmode: 'stack',
                      radialaxis: {
                        title: 'Avg Tokens',
                        gridcolor: 'rgba(200, 200, 200, 0.3)',
                      },
                      angularaxis: {
                        direction: 'clockwise',
                      },
                      bargap: 0,
                    },
                    showlegend: false,
                  }}
                  useResizeHandler
                  style={{ width: '100%', height: '500px' }}
                />
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
