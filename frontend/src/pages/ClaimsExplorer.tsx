import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import ScopeBreadcrumb from '@/components/ScopeBreadcrumb'
import CacheSummarisation from '@/components/CacheSummarisation'
import CoverageHeatmap from '@/components/CoverageHeatmap'
import ReindexButton from '@/components/ReindexButton'
import { DEFAULT_SORT, sortClaims } from '@/lib/claims'
import type { SortDir, SortField, SortSpec } from '@/lib/claims'
import type {
  ClaimBucket,
  ClaimLenses,
  ClaimModelDetail,
  ClaimRollup,
  Coverage,
  CoveragePivot,
  ProjectScope,
  ScopeChild,
} from '@/lib/api-client'

/**
 * Claims Explorer (CR5) — extractive set-union claim roll-ups over the scope
 * trie.
 *
 * Split into a thin container (`ClaimsExplorer`, which fetches) and a
 * presentational `ClaimsExplorerView` (props-injected, URL-state via
 * `useSearchParams`). Per ADR8.2, the view's data rendering — ranked claims,
 * counts, the not_summarised empty state — is unit-tested with vitest; the
 * container's fetch wiring is the data-independent shell exercised by e2e.
 *
 * URL state: `?model=&path=&grain=&bucket=` (grain default `month`, path
 * default `''` = root); defaults are omitted for clean URLs (ADR8.1).
 */

const LENSES = [
  { key: 'tasks', title: 'Tasks', testid: 'claims-lens-tasks' },
  { key: 'patterns', title: 'Patterns', testid: 'claims-lens-patterns' },
  { key: 'decisions_values', title: 'Decisions & Values', testid: 'claims-lens-decisions' },
  { key: 'learnings', title: 'Learnings', testid: 'claims-lens-learnings' },
] as const satisfies readonly { key: keyof ClaimLenses; title: string; testid: string }[]

const GRAINS = ['day', 'week', 'month'] as const
export const DEFAULT_GRAIN = 'month'

interface ClaimsExplorerViewProps {
  rollup: ClaimRollup | null
  buckets: ClaimBucket[]
  models: ClaimModelDetail[]
  childScopes: ScopeChild[]
  coverage: Coverage | null
  pivot: CoveragePivot | null
  loading: boolean
  /** Effective scope shown — the global Project pin when set, else the ?path= crumb. */
  scopePath: string
  /** True when the global Project filter hard-pins the scope (breadcrumb locked). */
  pinned: boolean
  /** Active Last-N-days window (0 = All time) — drives the windowed aggregate label. */
  days: number
}

/** Presentational explorer view — pure render + page-local URL state, no fetching. */
export function ClaimsExplorerView({
  rollup,
  buckets,
  models,
  childScopes,
  coverage,
  pivot,
  loading,
  scopePath,
  pinned,
  days,
}: ClaimsExplorerViewProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const grain = searchParams.get('grain') ?? DEFAULT_GRAIN
  const bucket = searchParams.get('bucket') ?? ''
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

  // Per-lens sort spec. Page-local interaction state (not URL state) — it's a
  // pure reordering of already-fetched claims, not a deep-linkable view.
  const setLensSort = (lensKey: keyof ClaimLenses, field: SortField) => {
    setSort((prev) => {
      const cur = prev[lensKey] ?? DEFAULT_SORT
      // Clicking the active field flips direction; switching field resets to
      // a sensible default (count→desc, claim→asc).
      const next: SortSpec =
        cur.field === field
          ? { field, dir: cur.dir === 'asc' ? 'desc' : 'asc' }
          : { field, dir: field === 'count' ? 'desc' : 'asc' }
      return { ...prev, [lensKey]: next }
    })
  }
  // Page-local interaction state (not URL state) — a pure reordering of
  // already-fetched claims, not a deep-linkable view. Keyed by lens.
  const [sort, setSort] = useState<Partial<Record<keyof ClaimLenses, SortSpec>>>({})

  // Keep the breadcrumb on /claims (it defaults to in-place ?path=, which is
  // already this route — but be explicit so other params are preserved).
  const breadcrumbLinkTo = (scope: string): string => {
    const next = new URLSearchParams(searchParams)
    if (scope) next.set('path', scope)
    else next.delete('path')
    const qs = next.toString()
    return `/claims${qs ? `?${qs}` : ''}`
  }

  const lenses = rollup?.status === 'summarised' ? rollup.lenses : null
  const failureCount = rollup?.status === 'summarised' ? rollup.failure_count : 0
  const failedSessions = rollup?.status === 'summarised' ? rollup.failed_sessions : []
  const notSummarised = !loading && !lenses

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold">Claims Explorer</h1>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {models.length > 0 ? (
            <label className="flex items-center gap-2">
              <span className="text-muted-foreground">Model:</span>
              <select
                data-testid="claims-model-select"
                value={model}
                onChange={(e) => setParam('model', e.target.value)}
                className="rounded border bg-background px-2 py-1"
              >
                <option value="">(default)</option>
                {models.map((m) => (
                  <option key={m.model} value={m.model}>
                    {m.has_claims ? m.model : `${m.model} (no data)`}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">Grain:</span>
            <select
              data-testid="claims-grain-select"
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
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">Bucket:</span>
            <select
              data-testid="claims-bucket-select"
              value={bucket}
              onChange={(e) => setParam('bucket', e.target.value)}
              className="rounded border bg-background px-2 py-1"
            >
              <option value="">(all in window)</option>
              {buckets.map((b) => (
                <option key={b.bucket} value={b.bucket}>
                  {b.bucket} ({b.n_claims})
                </option>
              ))}
            </select>
          </label>
          <ReindexButton path={scopePath} grain={grain} model={model} />
        </div>
      </div>

      {/* What slice is on screen — the windowed aggregate vs a drilled-down bucket. */}
      <p data-testid="claims-window-note" className="text-sm text-muted-foreground">
        {bucket ? (
          <>
            Showing the <span className="font-medium text-foreground">{bucket}</span> {grain} bucket
            (drill-down).
          </>
        ) : (
          <>
            Showing <span className="font-medium text-foreground">all {grain} claims</span> set-unioned
            across{' '}
            <span className="font-medium text-foreground">
              {days > 0 ? `the last ${days} days` : 'all time'}
            </span>
            , ranked by how many sessions raised each.
          </>
        )}
      </p>

      <ScopeBreadcrumb
        scopePath={scopePath}
        childScopes={pinned ? [] : childScopes}
        linkTo={breadcrumbLinkTo}
        disabled={pinned}
      />

      {/* Failures badge — links/lists the sessions that failed extraction. */}
      {failureCount > 0 ? (
        <details data-testid="claims-failures" className="rounded border bg-muted/40 p-3 text-sm">
          <summary className="cursor-pointer select-none">
            <span
              data-testid="claims-failure-badge"
              className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-800 dark:bg-rose-900/60 dark:text-rose-300"
            >
              {failureCount} extraction {failureCount === 1 ? 'failure' : 'failures'}
            </span>
          </summary>
          <ul className="mt-2 flex flex-wrap gap-2">
            {failedSessions.map((sid) => (
              <li key={sid}>
                <Link
                  data-testid="claims-failed-session"
                  to={`/sessions?session=${encodeURIComponent(sid)}`}
                  className="font-mono text-xs text-blue-600 hover:underline dark:text-blue-400"
                >
                  {sid.slice(0, 8)}…
                </Link>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}

      {lenses ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {LENSES.map((lens) => {
            const lensSort = sort[lens.key] ?? DEFAULT_SORT
            const sorted = sortClaims(lenses[lens.key], lensSort)
            return (
              <Card key={lens.key} data-testid={lens.testid}>
                <CardHeader>
                  <div className="flex items-center justify-between gap-2">
                    <CardTitle className="text-base">{lens.title}</CardTitle>
                    <div className="flex items-center gap-1 text-xs">
                      <SortHeader
                        testid={`sort-${lens.key}-count`}
                        label="count"
                        active={lensSort.field === 'count'}
                        dir={lensSort.dir}
                        onClick={() => setLensSort(lens.key, 'count')}
                      />
                      <SortHeader
                        testid={`sort-${lens.key}-claim`}
                        label="text"
                        active={lensSort.field === 'claim'}
                        dir={lensSort.dir}
                        onClick={() => setLensSort(lens.key, 'claim')}
                      />
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {sorted.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No claims.</p>
                  ) : (
                    <ul className="space-y-3">
                      {sorted.map((claim, i) => (
                        <li key={`${lens.key}-${i}`} data-testid="claim-item" className="text-sm">
                          <div className="flex items-start gap-2">
                            <span
                              data-testid="claim-count"
                              className="mt-0.5 shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-xs font-semibold text-muted-foreground"
                            >
                              ({claim.count}×)
                            </span>
                            <span className="whitespace-pre-wrap">{claim.claim}</span>
                          </div>
                          {claim.sessions.length > 0 ? (
                            <div className="ml-9 mt-1 flex flex-wrap gap-2">
                              {claim.sessions.map((sid) => (
                                <Link
                                  key={sid}
                                  data-testid="claim-session-link"
                                  to={`/sessions?session=${encodeURIComponent(sid)}`}
                                  className="font-mono text-xs text-blue-600 hover:underline dark:text-blue-400"
                                  title={`Find session ${sid}`}
                                >
                                  {sid.slice(0, 8)}…
                                </Link>
                              ))}
                            </div>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : null}

      {notSummarised ? (
        <Card data-testid="claims-empty">
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              This scope has no extracted claims yet for the selected grain/bucket/model. Run the
              claim extractor to populate it.
            </p>
          </CardContent>
        </Card>
      ) : null}

      <CoverageHeatmap pivot={pivot} />

      <CacheSummarisation coverage={coverage} />
    </div>
  )
}

/** A clickable sort-column header with an active-direction arrow. */
function SortHeader({
  testid,
  label,
  active,
  dir,
  onClick,
}: {
  testid: string
  label: string
  active: boolean
  dir: SortDir
  onClick: () => void
}) {
  return (
    <button
      type="button"
      data-testid={testid}
      onClick={onClick}
      aria-pressed={active}
      className={`rounded px-1.5 py-0.5 ${
        active ? 'bg-muted font-semibold text-foreground' : 'text-muted-foreground hover:bg-muted/60'
      }`}
    >
      {label}
      {active ? <span className="ml-0.5">{dir === 'asc' ? '↑' : '↓'}</span> : null}
    </button>
  )
}

/** Container — reads page-local URL params + the global filters, fetches, and feeds
 * the presentational view.
 *
 * The two global filters (`useFilters`) fold into the explorer per the consolidation:
 *  - `days` becomes the **window** for the default "all claims at this grain" aggregate
 *    (and narrows the bucket selector + heatmap columns + coverage), matching the
 *    app-wide grain⊥days convention;
 *  - `project` **hard-pins** the scope: it resolves to the project's leaf scope_path,
 *    overrides `?path=`, and locks the breadcrumb (cleared to regain the hierarchy).
 */
export default function ClaimsExplorer() {
  const [searchParams] = useSearchParams()
  const { filters } = useFilters()
  const grain = searchParams.get('grain') ?? DEFAULT_GRAIN
  const bucket = searchParams.get('bucket') ?? ''
  const model = searchParams.get('model') ?? ''
  const urlPath = searchParams.get('path') ?? ''

  // Hard-pin: resolve the global Project (a project_id) to its scope_path and lock
  // the explorer there. While the mapping loads, fall back to the URL crumb.
  const pinned = !!filters.project
  const { data: projectScope } = useApi<ProjectScope>(
    filters.project
      ? `/claims/scope/of-project?project_id=${encodeURIComponent(filters.project)}`
      : null,
  )
  const path = pinned ? (projectScope?.scope_path ?? urlPath) : urlPath

  const days = filters.days ?? 30
  const daysQs = days > 0 ? `&days=${days}` : ''
  const modelQs = model ? `&model=${encodeURIComponent(model)}` : ''
  const scopeQs = encodeURIComponent(path)

  const rollupQuery =
    `/claims/scope?path=${scopeQs}&grain=${grain}` +
    `&bucket=${encodeURIComponent(bucket)}${modelQs}${daysQs}`
  const { data: rollup, loading } = useApi<ClaimRollup>(rollupQuery)

  const { data: buckets } = useApi<ClaimBucket[]>(
    `/claims/buckets?path=${scopeQs}&grain=${grain}${modelQs}${daysQs}`,
  )
  const { data: models } = useApi<ClaimModelDetail[]>('/claims/models/detail')
  const { data: children } = useApi<ScopeChild[]>(`/claims/scope/children?path=${scopeQs}`)
  // Coverage table is filtered by the page-level scope (the breadcrumb `path`/pin) and
  // model, and windowed by the global days filter — top-of-page filters drive it.
  const { data: coverage } = useApi<Coverage>(
    `/claims/coverage?scope=${scopeQs}${modelQs}${daysQs}`,
  )
  // Heatmap is also scoped by the page-level `path` and windowed by days.
  const { data: pivot } = useApi<CoveragePivot>(
    `/claims/coverage-pivot?grain=${grain}&scope=${scopeQs}${modelQs}${daysQs}`,
  )

  return (
    <ClaimsExplorerView
      rollup={rollup}
      buckets={buckets ?? []}
      models={models ?? []}
      childScopes={children ?? []}
      coverage={coverage}
      pivot={pivot}
      loading={loading}
      scopePath={path}
      pinned={pinned}
      days={days}
    />
  )
}
