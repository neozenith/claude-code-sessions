import { useMemo, useState } from 'react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Coverage, CoverageProject } from '@/lib/api-client'

/**
 * CacheSummarisation (CR5) — claim-extraction coverage panel.
 *
 * Overall stacked bar (summarised / failed / pending) plus a per-project table
 * with a Domain column, sortable columns, and a domain-hierarchy filter. Pure
 * presentational input (props-injected coverage); sort + filter are local UI state.
 */

interface CacheSummarisationProps {
  coverage: Coverage | null
}

/** Width-percent of a part relative to a total (0 when total is 0). */
const pct = (part: number, total: number): number => (total > 0 ? (part / total) * 100 : 0)

type SortKey = keyof Pick<
  CoverageProject,
  'project_id' | 'domain' | 'total' | 'summarised' | 'failed' | 'pending' | 'pct_complete'
>
type SortDir = 'asc' | 'desc'

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: 'domain', label: 'Domain', numeric: false },
  { key: 'project_id', label: 'Project', numeric: false },
  { key: 'summarised', label: 'Summarised', numeric: true },
  { key: 'failed', label: 'Failed', numeric: true },
  { key: 'pending', label: 'Pending', numeric: true },
  { key: 'pct_complete', label: '% complete', numeric: true },
]

const compare = (a: CoverageProject, b: CoverageProject, key: SortKey): number => {
  const x = a[key]
  const y = b[key]
  if (typeof x === 'number' && typeof y === 'number') return x - y
  return String(x).localeCompare(String(y))
}

export default function CacheSummarisation({ coverage }: CacheSummarisationProps) {
  const [sortKey, setSortKey] = useState<SortKey>('pending')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  // Rows are already scoped by the page-level filter (the explorer passes the current
  // scope to /api/claims/coverage); the table only sorts what it's given.
  const projects = useMemo(() => coverage?.projects ?? [], [coverage])
  const rows = useMemo(() => {
    const sorted = [...projects].sort((a, b) => compare(a, b, sortKey))
    return sortDir === 'desc' ? sorted.reverse() : sorted
  }, [projects, sortKey, sortDir])

  if (!coverage) return null
  const { overall, model } = coverage

  const onSort = (key: SortKey): void => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'project_id' || key === 'domain' ? 'asc' : 'desc')
    }
  }
  const arrow = (key: SortKey): string => (key === sortKey ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '')

  return (
    <Card data-testid="cache-summarisation">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Cache summarisation</CardTitle>
          <span className="text-sm text-muted-foreground">
            <span className="font-mono">{model}</span>
            <span className="mx-2">·</span>
            <span data-testid="coverage-overall-pct" className="font-semibold text-foreground">
              {overall.pct_complete.toFixed(1)}% complete
            </span>
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Overall stacked bar: summarised / failed / pending. */}
        <div className="space-y-1">
          <div
            data-testid="coverage-stacked-bar"
            className="flex h-3 w-full overflow-hidden rounded-full bg-muted"
          >
            <div
              className="bg-emerald-500"
              style={{ width: `${pct(overall.summarised, overall.total)}%` }}
              title={`${overall.summarised} summarised`}
            />
            <div
              className="bg-rose-500"
              style={{ width: `${pct(overall.failed, overall.total)}%` }}
              title={`${overall.failed} failed`}
            />
            <div
              className="bg-slate-400"
              style={{ width: `${pct(overall.pending, overall.total)}%` }}
              title={`${overall.pending} pending`}
            />
          </div>
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              {overall.summarised.toLocaleString()} summarised
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-rose-500" />
              {overall.failed.toLocaleString()} failed
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-slate-400" />
              {overall.pending.toLocaleString()} pending
            </span>
            <span className="ml-auto">{overall.total.toLocaleString()} total</span>
          </div>
        </div>

        {/* Per-project table (sortable). Filtered by the page-level scope, not here. */}
        {rows.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="coverage-project-table">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  {COLUMNS.map((col) => (
                    <th
                      key={col.key}
                      data-testid={`sort-col-${col.key}`}
                      onClick={() => onSort(col.key)}
                      className={`cursor-pointer py-1 pr-4 font-medium select-none hover:text-foreground ${
                        col.numeric ? 'text-right' : ''
                      }`}
                    >
                      {col.label}
                      {arrow(col.key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.project_id} className="border-b last:border-0">
                    <td className="py-1 pr-4">{p.domain}</td>
                    <td className="py-1 pr-4 font-mono text-xs">{p.project_id}</td>
                    <td className="py-1 pr-4 text-right">{p.summarised.toLocaleString()}</td>
                    <td className="py-1 pr-4 text-right">{p.failed.toLocaleString()}</td>
                    <td className="py-1 pr-4 text-right">{p.pending.toLocaleString()}</td>
                    <td className="py-1 text-right">{p.pct_complete.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
