import { useMemo } from 'react'
import Plot from '@/lib/plotly'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { usePlotlyTheme } from '@/hooks/usePlotlyTheme'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatNumber } from '@/lib/formatters'
import { COST_COLOR, MODEL_INPUT_COLORS, MODEL_OUTPUT_COLORS } from '@/lib/chart-colors'
import type { UsageData } from '@/lib/api-client'

/**
 * Hero combo chart — per-bucket diverging token bars by model with a cost
 * area overlay on a zero-aligned secondary axis.
 *
 * Three visual layers:
 *   1. Output tokens stacked ABOVE zero, one trace per model (saturated
 *      colors from ``MODEL_OUTPUT_COLORS``).
 *   2. Input tokens stacked BELOW zero (plotted as negative y), one trace
 *      per model (``MODEL_INPUT_COLORS``), ``legendgroup`` paired with its
 *      output counterpart so a legend click toggles both halves.
 *   3. Total cost per bucket as a green area on a secondary y-axis whose
 *      zero line is aligned with the tokens zero line — the dual-axis
 *      alignment is computed from the data each render (see ``comboRanges``).
 *
 * Granularity is a prop: the component fetches ``/usage/{granularity}`` and
 * renders against whatever buckets come back, so the same component powers
 * the Dashboard (monthly) and the Daily/Weekly/Monthly pages.
 */
export interface CostTokenComboProps {
  granularity: 'daily' | 'weekly' | 'monthly'
  /** Axis-label text for the x-axis (e.g. "Date", "Week starting"). */
  xAxisLabel: string
  /** Card title displayed above the chart. */
  title: string
}

export const CostTokenCombo = ({ granularity, xAxisLabel, title }: CostTokenComboProps) => {
  const { filters, buildApiQuery } = useFilters()
  const { colors, mergeLayout } = usePlotlyTheme()
  const { data, loading, error } = useApi<UsageData[]>(
    `/usage/${granularity}${buildApiQuery()}`
  )

  // Project filter is applied client-side (matches the pattern used by the
  // existing DailyUsage / WeeklyUsage / MonthlyUsage pages).
  const filteredData = useMemo(() => {
    if (!data) return []
    if (!filters.project) return data
    return data.filter((row) => row.project_id === filters.project)
  }, [data, filters.project])

  // Aggregate cost + per-model input/output tokens per bucket.
  const { costs, tokensByModel, models, sortedBuckets } = useMemo(() => {
    const costsMap: Record<string, number> = {}
    const byModel: Record<string, Record<string, { input: number; output: number }>> = {}
    const uniqueModels = new Set<string>()

    filteredData.forEach((row) => {
      const bucket = row.time_bucket
      const model = row.model_id || 'unknown'

      costsMap[bucket] = (costsMap[bucket] || 0) + Number(row.total_cost_usd)

      uniqueModels.add(model)
      if (!byModel[model]) byModel[model] = {}
      if (!byModel[model][bucket]) byModel[model][bucket] = { input: 0, output: 0 }
      byModel[model][bucket].input += Number(row.total_input_tokens)
      byModel[model][bucket].output += Number(row.total_output_tokens)
    })

    return {
      costs: costsMap,
      tokensByModel: byModel,
      models: Array.from(uniqueModels).sort(),
      sortedBuckets: Object.keys(costsMap).sort(),
    }
  }, [filteredData])

  // Compute zero-aligned ranges for the dual y-axes.
  //
  // The tokens axis stacks output above zero and input below zero, so its
  // visible range spans [-maxInputStack, +maxOutputStack]. The cost axis
  // auto-scales separately, which leaves its zero line misaligned from
  // the tokens zero — visually a dual-axis chart with two horizontal
  // reference points, which is hard to read.
  //
  // Fix: set both axis ranges explicitly so the fractional position of
  // zero is identical on both. If tokens go from -N to +P, cost must go
  // from -(maxCost · N / P) to +maxCost to preserve that ratio.
  const comboRanges = useMemo(() => {
    const stackTotals = sortedBuckets.map((b) => {
      let posSum = 0
      let negSum = 0
      for (const model of models) {
        posSum += tokensByModel[model]?.[b]?.output ?? 0
        negSum += tokensByModel[model]?.[b]?.input ?? 0
      }
      return { posSum, negSum }
    })
    const topTokens = Math.max(0, ...stackTotals.map((t) => t.posSum))
    const bottomTokens = -Math.max(0, ...stackTotals.map((t) => t.negSum))
    const maxCost = Math.max(0, ...sortedBuckets.map((b) => costs[b] ?? 0))

    // Bail out of alignment for degenerate data (no output tokens, or no
    // cost). Plotly's auto-scale is a fine fallback.
    if (topTokens <= 0 || maxCost <= 0) return null

    // 5% padding applied symmetrically so the zero-alignment ratio is
    // preserved while bars don't touch the plot frame.
    const pad = 1.05
    const yTop = topTokens * pad
    const yBottom = bottomTokens * pad
    const y2Top = maxCost * pad
    const y2Bottom = (yBottom / yTop) * y2Top

    return {
      yRange: [yBottom, yTop] as [number, number],
      y2Range: [y2Bottom, y2Top] as [number, number],
    }
  }, [sortedBuckets, models, tokensByModel, costs])

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-16 text-muted-foreground">Loading…</div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-16 text-red-500">Error: {error}</div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <Plot
          data={[
            // Output tokens — positive y, stacked ABOVE the zero line.
            // Output lives on top because it's the cost-driver (5× the
            // per-token price of input) so the visually dominant half
            // agrees with the money story the cost overlay tells.
            ...models.map((model, idx) => {
              const maxOutput = Math.max(
                ...sortedBuckets.map((b) => tokensByModel[model]?.[b]?.output ?? 0)
              )
              return {
                x: sortedBuckets,
                y: sortedBuckets.map((b) => tokensByModel[model]?.[b]?.output ?? 0),
                type: 'bar' as const,
                name: `${(model ?? 'unknown').replace('claude-', '')} (output)`,
                marker: { color: MODEL_OUTPUT_COLORS[idx % MODEL_OUTPUT_COLORS.length] },
                text: sortedBuckets.map((b) => {
                  const v = tokensByModel[model]?.[b]?.output ?? 0
                  // Suppress labels on tiny segments (<5% of this
                  // model's peak) to keep the stack readable.
                  return v > maxOutput * 0.05 ? formatNumber(v) : ''
                }),
                textposition: 'inside' as const,
                textfont: { size: 10 },
                cliponaxis: false,
                hovertemplate:
                  '%{x}<br>%{fullData.name}<br>%{y:,} tokens<extra></extra>',
                legendgroup: model ?? 'unknown',
              }
            }),
            // Input tokens — plotted as NEGATIVE y so bars extend below
            // zero. `barmode: 'relative'` on the layout makes Plotly
            // stack positives upward and negatives downward.
            ...models.map((model, idx) => {
              const maxInput = Math.max(
                ...sortedBuckets.map((b) => tokensByModel[model]?.[b]?.input ?? 0)
              )
              return {
                x: sortedBuckets,
                y: sortedBuckets.map((b) => -(tokensByModel[model]?.[b]?.input ?? 0)),
                type: 'bar' as const,
                name: `${(model ?? 'unknown').replace('claude-', '')} (input)`,
                marker: { color: MODEL_INPUT_COLORS[idx % MODEL_INPUT_COLORS.length] },
                text: sortedBuckets.map((b) => {
                  const v = tokensByModel[model]?.[b]?.input ?? 0
                  return v > maxInput * 0.05 ? formatNumber(v) : ''
                }),
                textposition: 'inside' as const,
                textfont: { size: 10 },
                cliponaxis: false,
                // customdata carries the unsigned value so the tooltip
                // reads naturally ("500k tokens", not "-500k tokens").
                customdata: sortedBuckets.map(
                  (b) => tokensByModel[model]?.[b]?.input ?? 0
                ),
                hovertemplate:
                  '%{x}<br>%{fullData.name}<br>%{customdata:,} tokens<extra></extra>',
                legendgroup: model ?? 'unknown',
              }
            }),
            // Cost area overlay on the secondary axis — green fill with
            // the per-bucket total labelled above each point.
            {
              x: sortedBuckets,
              y: sortedBuckets.map((b) => costs[b]),
              type: 'scatter' as const,
              mode: 'text+lines' as const,
              name: 'Cost (USD)',
              fill: 'tozeroy' as const,
              fillcolor: 'rgba(16, 185, 129, 0.15)',
              line: { color: COST_COLOR, width: 2.5 },
              text: sortedBuckets.map((b) => `$${costs[b].toFixed(0)}`),
              textposition: 'top center' as const,
              textfont: { color: COST_COLOR, size: 11, weight: 600 },
              yaxis: 'y2' as const,
              hovertemplate: '%{x}<br>$%{y:.2f}<extra></extra>',
            },
          ]}
          layout={mergeLayout({
            autosize: true,
            margin: { l: 70, r: 140, t: 30, b: 50 },
            // `relative` barmode is the diverging-stack mode: positive
            // y values stack upward, negatives stack downward.
            barmode: 'relative',
            xaxis: { title: { text: xAxisLabel } },
            yaxis: {
              title: { text: 'Tokens (output ▲ / input ▼)' },
              tickformat: ',d',
              ...(comboRanges ? { range: comboRanges.yRange } : {}),
            },
            yaxis2: {
              title: { text: 'Cost (USD)' },
              overlaying: 'y',
              side: 'right',
              tickprefix: '$',
              color: colors.text,
              gridcolor: 'transparent',
              ...(comboRanges ? { range: comboRanges.y2Range } : {}),
            },
            showlegend: true,
          })}
          useResizeHandler
          style={{ width: '100%', height: '500px' }}
        />
      </CardContent>
    </Card>
  )
}
