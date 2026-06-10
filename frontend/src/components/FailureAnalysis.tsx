import { Link } from 'react-router-dom'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { FailureAnalysis as FailureAnalysisData } from '@/lib/api-client'

/**
 * FailureAnalysis (CR5 distillation) — rolls the parallel failure stream up into the
 * fixed taxonomy so systematic modes (e.g. "truncated_json") are visible and
 * actionable, instead of a pile of one-off exception strings. The per-category sample
 * excerpt tail is the diagnostic (a truncated output ends mid-structure); the sample
 * session links drill into SessionDetail.
 *
 * Per ADR8.2 the data rendering is unit-tested; the container just fetches.
 */

const CATEGORY_LABELS: Record<string, string> = {
  truncated_json: 'Truncated JSON (output cap)',
  malformed_json: 'Malformed JSON',
  missing_lens_key: 'Missing lens key',
  non_array_lens: 'Non-array lens value',
  empty_or_refusal: 'Empty / refusal',
  other: 'Other (uncategorised)',
}

export default function FailureAnalysis({ data }: { data: FailureAnalysisData | null }) {
  if (!data) return null

  return (
    <Card data-testid="failure-analysis">
      <CardHeader>
        <CardTitle className="text-base">
          Failure analysis
          <span data-testid="failure-total" className="ml-2 text-sm font-normal text-muted-foreground">
            {data.total === 0
              ? 'no extraction failures in this slice 🎉'
              : `${data.total} failed ${data.total === 1 ? 'session' : 'sessions'} — by mode`}
          </span>
        </CardTitle>
      </CardHeader>
      {data.total > 0 ? (
        <CardContent className="space-y-3">
          {data.categories.map((cat) => (
            <details
              key={cat.category}
              data-testid={`failure-category-${cat.category}`}
              className="rounded border bg-muted/30 p-3 text-sm"
            >
              <summary className="flex cursor-pointer select-none items-center justify-between gap-2">
                <span className="font-medium">
                  {CATEGORY_LABELS[cat.category] ?? cat.category}
                </span>
                <span
                  data-testid="failure-category-count"
                  className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-800 dark:bg-rose-900/60 dark:text-rose-300"
                >
                  {cat.count} ({cat.pct}%)
                </span>
              </summary>
              <div className="mt-2 space-y-2">
                <p className="text-xs text-muted-foreground">
                  e.g. <span className="font-mono">{cat.sample_reason}</span>
                </p>
                {cat.sample_excerpt_tail ? (
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-background p-2 text-xs">
                    …{cat.sample_excerpt_tail}
                  </pre>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  {cat.sample_sessions.map((s) => (
                    <Link
                      key={`${s.project_id}/${s.session_id}`}
                      data-testid="failure-sample-session"
                      to={`/sessions/${encodeURIComponent(s.project_id)}/${encodeURIComponent(s.session_id)}`}
                      className="font-mono text-xs text-blue-600 hover:underline dark:text-blue-400"
                    >
                      {s.session_id.slice(0, 8)}…
                    </Link>
                  ))}
                </div>
              </div>
            </details>
          ))}
        </CardContent>
      ) : null}
    </Card>
  )
}
