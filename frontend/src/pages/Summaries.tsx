import { useSearchParams } from 'react-router-dom'

import { useApi } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import ScopeBreadcrumb from '@/components/ScopeBreadcrumb'
import type { ScopeChild, SummaryResponse, SummaryVariant } from '@/lib/api-client'

/**
 * Summaries explorer (G8).
 *
 * Split into a thin container (`Summaries`, which fetches) and a presentational
 * `SummariesView` (props-injected, URL-state via `useSearchParams`). The view's
 * rendering logic — lens cards when summarised, empty state when not, variant
 * selectors — is unit-tested with vitest (ADR8.2); the container's fetch wiring
 * is data-independent shell exercised by the e2e smoke.
 */

const LENSES = [
  { key: 'task_summary', title: 'Task & ubiquitous language', testid: 'lens-task' },
  { key: 'patterns', title: 'Architectural patterns', testid: 'lens-patterns' },
  { key: 'decisions_values', title: 'Decisions & values', testid: 'lens-decisions' },
] as const

const GRAINS = ['day', 'week', 'month'] as const
const DEFAULT_GRAIN = 'day'

interface SummariesViewProps {
  summary: SummaryResponse | null
  childScopes: ScopeChild[]
  variants: SummaryVariant[]
  loading: boolean
}

/** Presentational explorer view — pure render + page-local URL state, no fetching. */
export function SummariesView({ summary, childScopes, variants, loading }: SummariesViewProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const path = searchParams.get('path') ?? ''
  const grain = searchParams.get('grain') ?? DEFAULT_GRAIN
  const strategy = searchParams.get('strategy') ?? ''
  const model = searchParams.get('model') ?? ''

  const setParam = (key: string, value: string, defaultValue = '') => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value === defaultValue) {
        next.delete(key)
      } else {
        next.set(key, value)
      }
      return next
    })
  }

  const lenses = summary?.status === 'summarised' ? summary.lenses : null
  const notSummarised = !loading && !lenses

  const strategies = Array.from(new Set(variants.map((v) => v.strategy)))
  const models = Array.from(new Set(variants.map((v) => v.model)))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Summaries</h1>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">Grain:</span>
            <select
              data-testid="grain-select"
              value={grain}
              onChange={(e) => setParam('grain', e.target.value, DEFAULT_GRAIN)}
              className="rounded border bg-background px-2 py-1"
            >
              {GRAINS.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </label>
          {strategies.length > 0 ? (
            <label className="flex items-center gap-2">
              <span className="text-muted-foreground">Strategy:</span>
              <select
                data-testid="strategy-select"
                value={strategy}
                onChange={(e) => setParam('strategy', e.target.value)}
                className="rounded border bg-background px-2 py-1"
              >
                <option value="">(any)</option>
                {strategies.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {models.length > 0 ? (
            <label className="flex items-center gap-2">
              <span className="text-muted-foreground">Model:</span>
              <select
                data-testid="model-select"
                value={model}
                onChange={(e) => setParam('model', e.target.value)}
                className="rounded border bg-background px-2 py-1"
              >
                <option value="">(any)</option>
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      </div>

      <ScopeBreadcrumb scopePath={path} childScopes={childScopes} />

      {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}

      {lenses ? (
        <div className="grid gap-4 md:grid-cols-3">
          {LENSES.map((lens) => (
            <Card key={lens.key}>
              <CardHeader>
                <CardTitle className="text-base">{lens.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p data-testid={lens.testid} className="whitespace-pre-wrap text-sm">
                  {lenses[lens.key]}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}

      {notSummarised ? (
        <Card data-testid="summary-empty">
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              This scope has no summary yet for the selected strategy/model. Run the summariser to
              populate it.
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

/** Container — reads page-local URL params, fetches, and feeds the presentational view. */
export default function Summaries() {
  const [searchParams] = useSearchParams()
  const path = searchParams.get('path') ?? ''
  const grain = searchParams.get('grain') ?? DEFAULT_GRAIN
  const bucket = searchParams.get('bucket') ?? ''
  const strategy = searchParams.get('strategy') ?? ''
  const model = searchParams.get('model') ?? ''

  const scopeQuery =
    `/summaries/scope?path=${encodeURIComponent(path)}&grain=${grain}&bucket=${encodeURIComponent(bucket)}` +
    (strategy ? `&strategy=${encodeURIComponent(strategy)}` : '') +
    (model ? `&model=${encodeURIComponent(model)}` : '')
  const { data: summary, loading } = useApi<SummaryResponse>(scopeQuery)
  const { data: children } = useApi<ScopeChild[]>(
    `/summaries/scope/children?path=${encodeURIComponent(path)}`,
  )
  const { data: variants } = useApi<SummaryVariant[]>('/summaries/variants')

  return (
    <SummariesView
      summary={summary}
      childScopes={children ?? []}
      variants={variants ?? []}
      loading={loading}
    />
  )
}
