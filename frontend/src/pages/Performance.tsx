import Plot from '@/lib/plotly'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { PerformanceSummary } from '@/lib/api-client'

/** Short model label (strip the `claude-` prefix and trailing date suffix). */
const shortModel = (modelId: string): string =>
  modelId.replace('claude-', '').replace(/-\d{6,}$/, '')

export default function Performance() {
  const { buildApiQuery } = useFilters()
  const { mergeLayout, colors } = usePlotlyTheme()
  const { data, loading } = useApi<PerformanceSummary>(`/performance${buildApiQuery()}`)

  if (loading) {
    return <div className="text-center py-8">Loading…</div>
  }

  const byModel = data?.by_model ?? []
  const histogram = data?.ratio_histogram ?? []
  const models = byModel.map((m) => shortModel(m.model_id))

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Performance</h1>
      <p className="text-sm text-muted-foreground">
        Model throughput (tokens/sec), context-window utilization, and the idle vs active split per
        turn — honoring the global day/project filters. Context utilization is the raw ratio of the
        window in use (no categorical zones).
      </p>

      {/* Tokens/sec by model */}
      <Card>
        <CardHeader>
          <CardTitle>Tokens / sec by model</CardTitle>
        </CardHeader>
        <CardContent>
          <div data-testid="perf-tps-chart">
            <Plot
              data={[
                {
                  type: 'bar' as const,
                  name: 'avg TPS',
                  x: models,
                  y: byModel.map((m) => m.avg_tps ?? 0),
                  marker: { color: '#3b82f6' },
                },
                {
                  type: 'bar' as const,
                  name: 'median TPS',
                  x: models,
                  y: byModel.map((m) => m.median_tps ?? 0),
                  marker: { color: '#10b981' },
                },
              ]}
              layout={mergeLayout({
                barmode: 'group',
                margin: { l: 60, r: 140, t: 30, b: 80 },
                xaxis: { color: colors.text },
                yaxis: { title: { text: 'tokens/sec' }, color: colors.text },
              })}
              useResizeHandler
              style={{ width: '100%', height: '360px' }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Context-window utilization histogram (raw ratio bins) */}
      <Card>
        <CardHeader>
          <CardTitle>Context-window utilization</CardTitle>
        </CardHeader>
        <CardContent>
          <div data-testid="perf-context-histogram">
            <Plot
              data={[
                {
                  type: 'bar' as const,
                  name: 'response heads',
                  x: histogram.map((b) => `${Math.round(b.bin_lo * 100)}–${Math.round(b.bin_hi * 100)}%`),
                  y: histogram.map((b) => b.count),
                  marker: { color: '#6366f1' },
                },
              ]}
              layout={mergeLayout({
                margin: { l: 60, r: 40, t: 30, b: 60 },
                showlegend: false,
                xaxis: { title: { text: 'window used' }, color: colors.text },
                yaxis: { title: { text: 'responses' }, color: colors.text },
              })}
              useResizeHandler
              style={{ width: '100%', height: '360px' }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Idle vs active time per model (seconds) */}
      <Card>
        <CardHeader>
          <CardTitle>Idle vs active time by model</CardTitle>
        </CardHeader>
        <CardContent>
          <div data-testid="perf-idle-active">
            <Plot
              data={[
                {
                  type: 'bar' as const,
                  name: 'active',
                  x: models,
                  y: byModel.map((m) => Math.round(m.total_active_ms / 1000)),
                  marker: { color: '#10b981' },
                },
                {
                  type: 'bar' as const,
                  name: 'idle',
                  x: models,
                  y: byModel.map((m) => Math.round(m.total_idle_ms / 1000)),
                  marker: { color: '#f59e0b' },
                },
              ]}
              layout={mergeLayout({
                barmode: 'stack',
                margin: { l: 60, r: 140, t: 30, b: 80 },
                xaxis: { color: colors.text },
                yaxis: { title: { text: 'seconds' }, color: colors.text },
              })}
              useResizeHandler
              style={{ width: '100%', height: '360px' }}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
