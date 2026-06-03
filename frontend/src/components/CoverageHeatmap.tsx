import type { Data } from 'plotly.js'

import Plot from '@/lib/plotly'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { buildHeatmapMatrices } from '@/lib/claims'
import type { CoveragePivot } from '@/lib/api-client'

/**
 * CoverageHeatmap (CR5) — done-vs-pending pivot over (scope × bucket).
 *
 * Fed by `/api/claims/coverage-pivot?model=&grain=`. The heatmap's color
 * encodes the tri-state extraction status per cell (pending=0, failed=1,
 * done=2); hover surfaces sessions / claims / failures. Densification of the
 * sparse `cells` list into the z/text matrices lives in the pure
 * `buildHeatmapMatrices` helper (lib/claims.ts) so it's unit-testable without
 * Plotly.
 */

interface CoverageHeatmapProps {
  pivot: CoveragePivot | null
}

export default function CoverageHeatmap({ pivot }: CoverageHeatmapProps) {
  const { mergeLayout } = usePlotlyTheme()

  if (!pivot || pivot.scopes.length === 0 || pivot.buckets.length === 0) {
    return null
  }

  const { z, text } = buildHeatmapMatrices(pivot)

  // react-plotly's `Data` types `text` as string | string[], but Plotly's
  // heatmap accepts a 2-D `text` matrix for per-cell hovertext. Build the
  // trace and cast through `Data` so the 2-D shape is accepted.
  const heatmapTrace = {
    type: 'heatmap',
    x: pivot.buckets,
    y: pivot.scopes,
    z,
    text,
    hoverinfo: 'text',
    xgap: 2,
    ygap: 2,
    // pending → failed → done. Slate / rose / emerald to match the
    // CacheSummarisation legend swatches.
    colorscale: [
      [0, '#94a3b8'],
      [0.5, '#f43f5e'],
      [1, '#10b981'],
    ],
    zmin: 0,
    zmax: 2,
    colorbar: {
      tickmode: 'array',
      tickvals: [0, 1, 2],
      ticktext: ['pending', 'failed', 'done'],
    },
  } as unknown as Data

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Coverage heatmap</CardTitle>
      </CardHeader>
      <CardContent>
        <div data-testid="coverage-heatmap">
          <Plot
            data={[heatmapTrace]}
            layout={mergeLayout({
              autosize: true,
              margin: { l: 160, r: 60, t: 30, b: 80 },
              xaxis: { title: { text: 'Bucket' }, tickangle: -45, automargin: true },
              yaxis: { title: { text: 'Scope' }, automargin: true },
              showlegend: false,
            })}
            useResizeHandler
            style={{ width: '100%', height: '400px' }}
          />
        </div>
      </CardContent>
    </Card>
  )
}
