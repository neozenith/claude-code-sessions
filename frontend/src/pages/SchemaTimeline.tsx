import { useMemo } from 'react'
import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface SchemaEvent {
  event_date: string  // YYYY-MM-DD format
  version: string | null
  json_path: string
  first_seen: string  // YYYY-MM-DD format
  has_record_timestamp: boolean
  event_count: number
}

// Color palette for JSON paths
const PATH_COLORS = [
  '#3B82F6', // Blue
  '#10B981', // Emerald
  '#F59E0B', // Amber
  '#EF4444', // Red
  '#8B5CF6', // Violet
  '#EC4899', // Pink
  '#06B6D4', // Cyan
  '#84CC16', // Lime
  '#F97316', // Orange
  '#6366F1', // Indigo
  '#14B8A6', // Teal
  '#A855F7', // Purple
  '#22C55E', // Green
  '#0EA5E9', // Sky
  '#E11D48', // Rose
  '#FACC15', // Yellow
]

export default function SchemaTimeline() {
  const { buildApiQuery } = useFilters()

  // Get schema timeline data using global filters
  const { data: events, loading } = useApi<SchemaEvent[]>(
    `/schema-timeline${buildApiQuery()}`
  )

  // Process events for plotting
  const plotData = useMemo(() => {
    if (!events || events.length === 0) return null

    // Group events by json_path
    const pathEvents = new Map<string, SchemaEvent[]>()
    events.forEach((event) => {
      const existing = pathEvents.get(event.json_path) || []
      existing.push(event)
      pathEvents.set(event.json_path, existing)
    })

    // Sort paths by first_seen (earliest first for top of chart)
    const pathOrder = [...pathEvents.keys()].sort((a, b) => {
      const aFirst = pathEvents.get(a)?.[0]?.first_seen || ''
      const bFirst = pathEvents.get(b)?.[0]?.first_seen || ''
      return new Date(aFirst).getTime() - new Date(bFirst).getTime()
    })

    // Create a map of path to y-index (reverse for plotly - 0 at bottom)
    const pathToYIndex = new Map(pathOrder.map((p, i) => [p, pathOrder.length - 1 - i]))

    // Create traces - one per path for distinct colors
    const traces = pathOrder.map((jsonPath, colorIndex) => {
      const pathData = pathEvents.get(jsonPath) || []
      const color = PATH_COLORS[colorIndex % PATH_COLORS.length]

      return {
        type: 'scatter' as const,
        mode: 'markers' as const,
        name: jsonPath,
        x: pathData.map((e) => e.event_date),
        y: pathData.map(() => pathToYIndex.get(jsonPath) ?? 0),
        marker: {
          symbol: 'circle',
          size: 10,
          color: color,
          opacity: 0.6,
          line: {
            color: 'white',
            width: 1,
          },
        },
        text: pathData.map((e) => {
          const dateSource = e.has_record_timestamp ? '' : ' (from file mtime)'
          const version = e.version || '(no version)'
          return `<b>Path:</b> ${jsonPath}<br><b>Date:</b> ${e.event_date}${dateSource}<br><b>Version:</b> ${version}<br><b>Events:</b> ${e.event_count}`
        }),
        hoverinfo: 'text' as const,
      }
    })

    // Calculate path statistics
    const pathStats = pathOrder.map((jsonPath) => {
      const pathData = pathEvents.get(jsonPath) || []
      const versions = [...new Set(pathData.map((e) => e.version).filter(Boolean))]
      const totalEvents = pathData.reduce((sum, e) => sum + e.event_count, 0)
      const daysWithRecordTimestamp = pathData.filter((e) => e.has_record_timestamp).length
      return {
        path: jsonPath,
        firstSeen: pathData[0]?.first_seen || '',
        dayCount: pathData.length,  // Number of unique days
        totalEvents,  // Total events across all days
        daysWithRecordTimestamp,
        versions,
      }
    })

    return {
      traces,
      pathOrder,
      pathStats,
    }
  }, [events])

  // Calculate version range
  const versionRange = useMemo(() => {
    if (!events || events.length === 0) return null
    const versions = [...new Set(events.map((e) => e.version).filter(Boolean))]
      .sort()
    return {
      min: versions[0] || 'Unknown',
      max: versions[versions.length - 1] || 'Unknown',
      count: versions.length,
    }
  }, [events])

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Schema Timeline</h1>

      {/* Description */}
      <Card>
        <CardContent className="py-4">
          <p className="text-muted-foreground">
            This visualization shows the evolution of JSON schema attributes in Claude Code session data over time.
            Each row represents a JSON path, and each circle represents a day where that path was observed.
            When records lack timestamps, the file modification time is used as a fallback.
            Paths are sorted by their first appearance date (earliest at top).
          </p>
        </CardContent>
      </Card>

      {loading ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">Loading schema timeline data...</p>
          </CardContent>
        </Card>
      ) : !plotData || plotData.traces.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">
              No schema data found for the selected time range
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Timeline Chart */}
          <Card>
            <CardHeader>
              <CardTitle>Schema Evolution Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <Plot
                data={plotData.traces}
                layout={{
                  autosize: true,
                  height: Math.max(500, plotData.pathOrder.length * 25 + 150),
                  margin: { l: 350, r: 50, t: 30, b: 80 },
                  xaxis: {
                    title: { text: 'Time' },
                    type: 'date',
                  },
                  yaxis: {
                    title: { text: '' },
                    tickvals: plotData.pathOrder.map((_, i) => plotData.pathOrder.length - 1 - i),
                    ticktext: plotData.pathOrder,
                    tickfont: { size: 11 },
                    automargin: true,
                  },
                  showlegend: false,
                  hovermode: 'closest',
                  paper_bgcolor: 'transparent',
                  plot_bgcolor: 'transparent',
                }}
                useResizeHandler
                style={{ width: '100%' }}
                config={{
                  displayModeBar: true,
                  responsive: true,
                }}
              />
            </CardContent>
          </Card>

          {/* Summary Stats */}
          <Card>
            <CardHeader>
              <CardTitle>Summary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Total Paths</p>
                  <p className="text-2xl font-bold">{plotData.pathOrder.length}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Data Points</p>
                  <p className="text-2xl font-bold">{events?.length.toLocaleString()}</p>
                  <p className="text-xs text-muted-foreground">path × day combinations</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Version Range</p>
                  <p className="text-lg font-medium">
                    {versionRange ? `${versionRange.min} → ${versionRange.max}` : 'N/A'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Unique Versions</p>
                  <p className="text-2xl font-bold">{versionRange?.count || 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Path Details Table */}
          <Card>
            <CardHeader>
              <CardTitle>Path Details</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 px-3 font-medium">JSON Path</th>
                      <th className="text-left py-2 px-3 font-medium">First Seen</th>
                      <th className="text-right py-2 px-3 font-medium">Days</th>
                      <th className="text-right py-2 px-3 font-medium">Events</th>
                      <th className="text-left py-2 px-3 font-medium">Versions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plotData.pathStats.map((stat, i) => (
                      <tr key={stat.path} className="border-b last:border-0 hover:bg-muted/50">
                        <td className="py-2 px-3">
                          <div className="flex items-center gap-2">
                            <div
                              className="w-3 h-3 rounded-full"
                              style={{ backgroundColor: PATH_COLORS[i % PATH_COLORS.length] }}
                            />
                            <code className="text-xs">{stat.path}</code>
                          </div>
                        </td>
                        <td className="py-2 px-3 text-muted-foreground">
                          {stat.firstSeen || '(unknown)'}
                        </td>
                        <td className="py-2 px-3 text-right">{stat.dayCount}</td>
                        <td className="py-2 px-3 text-right text-muted-foreground">
                          {stat.totalEvents.toLocaleString()}
                        </td>
                        <td className="py-2 px-3 text-muted-foreground text-xs">
                          {stat.versions.length > 0
                            ? <>
                                {stat.versions.slice(0, 3).join(', ')}
                                {stat.versions.length > 3 && ` +${stat.versions.length - 3} more`}
                              </>
                            : '(none)'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
