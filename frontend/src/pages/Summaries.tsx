import { useSearchParams } from 'react-router-dom'

import { useApi } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import ScopeBreadcrumb from '@/components/ScopeBreadcrumb'
import type { ScopeChild, SummaryResponse } from '@/lib/api-client'

/**
 * Summaries explorer (G8).
 *
 * Navigates the variable-depth scope trie at a chosen time grain, rendering the
 * three lenses for the current scope and a breadcrumb + child links to drill
 * up/down. All page-local state (`path`/`grain`/`bucket`) lives in the URL
 * (ADR8.1), so every view deep-links.
 */

const LENSES = [
  { key: 'task_summary', title: 'Task & ubiquitous language', testid: 'lens-task' },
  { key: 'patterns', title: 'Architectural patterns', testid: 'lens-patterns' },
  { key: 'decisions_values', title: 'Decisions & values', testid: 'lens-decisions' },
] as const

const GRAINS = ['day', 'week', 'month'] as const
const DEFAULT_GRAIN = 'day'

export default function Summaries() {
  const [searchParams, setSearchParams] = useSearchParams()
  const path = searchParams.get('path') ?? ''
  const grain = searchParams.get('grain') ?? DEFAULT_GRAIN
  const bucket = searchParams.get('bucket') ?? ''

  const scopeQuery = `/summaries/scope?path=${encodeURIComponent(path)}&grain=${grain}&bucket=${encodeURIComponent(bucket)}`
  const { data, loading, error } = useApi<SummaryResponse>(scopeQuery)
  const { data: children } = useApi<ScopeChild[]>(
    `/summaries/scope/children?path=${encodeURIComponent(path)}`,
  )

  const lenses = data?.status === 'summarised' ? data.lenses : null
  const notSummarised = !loading && !lenses

  const setGrain = (next: string) => {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev)
      if (next === DEFAULT_GRAIN) {
        params.delete('grain')
      } else {
        params.set('grain', next)
      }
      return params
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Summaries</h1>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Grain:</span>
          <select
            data-testid="grain-select"
            value={grain}
            onChange={(e) => setGrain(e.target.value)}
            className="rounded border bg-background px-2 py-1"
          >
            {GRAINS.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ScopeBreadcrumb scopePath={path} childScopes={children ?? []} />

      <div className="grid gap-4 md:grid-cols-3">
        {LENSES.map((lens) => (
          <Card key={lens.key}>
            <CardHeader>
              <CardTitle className="text-base">{lens.title}</CardTitle>
            </CardHeader>
            <CardContent>
              <p data-testid={lens.testid} className="whitespace-pre-wrap text-sm">
                {loading
                  ? 'Loading…'
                  : lenses
                    ? lenses[lens.key]
                    : 'Not yet summarised for this scope.'}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {notSummarised ? (
        <p className="text-sm text-muted-foreground" data-testid="summaries-empty">
          {error
            ? 'No summary available for this scope.'
            : 'This scope has no summary yet. Run the summariser to populate it.'}
        </p>
      ) : null}
    </div>
  )
}
