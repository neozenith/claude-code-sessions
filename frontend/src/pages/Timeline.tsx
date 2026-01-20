import { useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import Plot from 'react-plotly.js'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface TimelineEvent {
  project_id: string
  session_id: string
  event_seq: number
  model_id: string
  event_type: string
  message_content: string
  timestamp_utc: string
  timestamp_local: string
  first_event_time: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  cache_5m_tokens: number
  total_tokens: number
  cumulative_output_tokens: number
}

// Event type styling - color AND marker shape for maximum visibility
const EVENT_TYPE_STYLES: Record<string, { symbol: string; color: string; name: string }> = {
  user: { symbol: 'square', color: '#3B82F6', name: 'User' }, // Blue square
  assistant: { symbol: 'circle', color: '#10B981', name: 'Assistant' }, // Green circle
  tool_use: { symbol: 'diamond', color: '#F59E0B', name: 'Tool Use' }, // Orange diamond
  tool_result: { symbol: 'star', color: '#8B5CF6', name: 'Tool Result' }, // Purple star
  system: { symbol: 'hexagon', color: '#EF4444', name: 'System' }, // Red hexagon
}

// Default style for unknown event types
const DEFAULT_EVENT_STYLE = { symbol: 'circle', color: '#6B7280', name: 'Other' }

export default function Timeline() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { filters } = useFilters()
  const { mergeLayout, colors } = usePlotlyTheme()

  // Read hide agents from URL params (specific to this page)
  const hideAgentSessions = searchParams.get('hideAgents') === 'true'

  // Update URL params (for page-specific params like hideAgents)
  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      setSearchParams((prev) => {
        const newParams = new URLSearchParams(prev)
        Object.entries(updates).forEach(([key, value]) => {
          if (value === null || value === '') {
            newParams.delete(key)
          } else {
            newParams.set(key, value)
          }
        })
        return newParams
      })
    },
    [setSearchParams]
  )

  // Build API query for timeline events using global filters
  const daysParam = filters.days && filters.days > 0 ? `?days=${filters.days}` : ''

  // Get timeline events for selected project with time filter
  const { data: events, loading: eventsLoading } = useApi<TimelineEvent[]>(
    filters.project ? `/timeline/events/${encodeURIComponent(filters.project)}${daysParam}` : null
  )

  // Filter events based on agent session toggle
  const filteredEvents = useMemo(() => {
    if (!events) return null
    if (!hideAgentSessions) return events
    return events.filter((e) => !e.session_id.startsWith('agent-'))
  }, [events, hideAgentSessions])

  // Process events for plotting
  const plotData = useMemo(() => {
    if (!filteredEvents || filteredEvents.length === 0) return null

    // Get unique sessions ordered by first event time
    const sessionOrder = [...new Set(filteredEvents.map((e) => e.session_id))]
    const sessionToYIndex = new Map(sessionOrder.map((s, i) => [s, i]))

    // Get unique event types
    const eventTypes = [...new Set(filteredEvents.map((e) => e.event_type))]

    // Calculate max cumulative tokens for size scaling
    const maxCumulativeTokens = Math.max(...filteredEvents.map((e) => e.cumulative_output_tokens), 1)

    // Create traces grouped by event type (for different markers and colors)
    const traces = eventTypes.map((eventType) => {
      const typeEvents = filteredEvents.filter((e) => e.event_type === eventType)
      const style = EVENT_TYPE_STYLES[eventType] || DEFAULT_EVENT_STYLE

      return {
        type: 'scatter' as const,
        mode: 'markers' as const,
        name: style.name,
        x: typeEvents.map((e) => e.timestamp_local),
        y: typeEvents.map((e) => sessionToYIndex.get(e.session_id) ?? 0),
        marker: {
          symbol: style.symbol,
          size: typeEvents.map((e) =>
            Math.max(12, Math.min(35, (e.cumulative_output_tokens / maxCumulativeTokens) * 30 + 8))
          ),
          color: style.color,
          opacity: 0.6,
          line: {
            color: 'white',
            width: 2,
          },
        },
        // Use <br> for line breaks in hover text
        text: typeEvents.map((e) => {
          // Truncate and escape message content for hover display
          const contentPreview = e.message_content
            ? e.message_content.substring(0, 200).replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
            : '(no content)'
          const hasMore = e.message_content && e.message_content.length > 200

          return (
            `<b>Session:</b> ${e.session_id.substring(0, 20)}...<br>` +
            `<b>Event #${e.event_seq}</b><br>` +
            `<b>Type:</b> ${e.event_type}<br>` +
            `<b>Model:</b> ${e.model_id || 'N/A'}<br>` +
            `<b>Time:</b> ${new Date(e.timestamp_local).toLocaleString()}<br>` +
            `<br>` +
            `<b>Message:</b><br>${contentPreview}${hasMore ? '...' : ''}<br>` +
            `<br>` +
            `<b>Input:</b> ${e.input_tokens.toLocaleString()} tokens<br>` +
            `<b>Output:</b> ${e.output_tokens.toLocaleString()} tokens<br>` +
            `<b>Cache Read:</b> ${e.cache_read_tokens.toLocaleString()} tokens<br>` +
            `<b>Cumulative Output:</b> ${e.cumulative_output_tokens.toLocaleString()} tokens`
          )
        }),
        hoverinfo: 'text' as const,
      }
    })

    return {
      traces,
      sessionOrder,
      sessionLabels: sessionOrder.map((s) => s.substring(0, 16) + '...'),
    }
  }, [filteredEvents])

  // Count agent sessions for display
  const agentSessionCount = useMemo(() => {
    if (!events) return 0
    const agentSessions = new Set(events.filter((e) => e.session_id.startsWith('agent-')).map((e) => e.session_id))
    return agentSessions.size
  }, [events])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-3xl font-bold">Session Timeline</h1>

        {/* Agent Sessions Filter (page-specific toggle) */}
        {filters.project && agentSessionCount > 0 && (
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={hideAgentSessions}
              onChange={(e) => updateParams({ hideAgents: e.target.checked ? 'true' : null })}
              className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
            />
            <span>Hide agent sessions ({agentSessionCount})</span>
          </label>
        )}
      </div>

      {!filters.project ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground text-lg">
              Select a project from the header filter to view the session timeline
            </p>
          </CardContent>
        </Card>
      ) : eventsLoading ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">Loading timeline data...</p>
          </CardContent>
        </Card>
      ) : !plotData || plotData.traces.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">No events found for this project in the selected time range</p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Legend */}
          <Card>
            <CardHeader>
              <CardTitle>Legend</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-8">
                <div>
                  <p className="text-sm font-medium mb-3">Event Types:</p>
                  <div className="flex flex-wrap gap-4">
                    {Object.entries(EVENT_TYPE_STYLES).map(([type, style]) => (
                      <div key={type} className="flex items-center gap-2 text-sm">
                        <div className="w-4 h-4 rounded-sm" style={{ backgroundColor: style.color }} />
                        <span className="font-medium">{style.name}</span>
                        <span className="text-muted-foreground">({style.symbol})</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-sm font-medium mb-3">Marker Size:</p>
                  <p className="text-sm text-muted-foreground">Size represents cumulative output tokens in the session</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Timeline Chart */}
          <Card>
            <CardHeader>
              <CardTitle>Event Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <Plot
                data={plotData.traces}
                layout={mergeLayout({
                  autosize: true,
                  height: Math.max(400, plotData.sessionOrder.length * 30 + 100),
                  margin: { l: 180, r: 50, t: 30, b: 80 },
                  xaxis: {
                    title: { text: 'Time' },
                    type: 'date',
                  },
                  yaxis: {
                    title: { text: 'Session', font: { color: colors.text } },
                    tickvals: plotData.sessionOrder.map((_, i) => i),
                    ticktext: plotData.sessionLabels,
                    automargin: true,
                  },
                  showlegend: true,
                  legend: {
                    orientation: 'h',
                    yanchor: 'bottom',
                    y: 1.02,
                    xanchor: 'right',
                    x: 1,
                  },
                  hovermode: 'closest',
                })}
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
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Total Sessions</p>
                  <p className="text-2xl font-bold">{plotData.sessionOrder.length}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Total Events</p>
                  <p className="text-2xl font-bold">{filteredEvents?.length.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Event Types</p>
                  <p className="text-2xl font-bold">{plotData.traces.length}</p>
                </div>
                {hideAgentSessions && agentSessionCount > 0 && (
                  <div>
                    <p className="text-sm text-muted-foreground">Hidden Agent Sessions</p>
                    <p className="text-2xl font-bold text-muted-foreground">{agentSessionCount}</p>
                  </div>
                )}
                <div>
                  <p className="text-sm text-muted-foreground">Time Range</p>
                  <p className="text-lg font-medium">
                    {filteredEvents && filteredEvents.length > 0
                      ? `${new Date(filteredEvents[0].timestamp_local).toLocaleDateString()} - ${new Date(filteredEvents[filteredEvents.length - 1].timestamp_local).toLocaleDateString()}`
                      : 'N/A'}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
