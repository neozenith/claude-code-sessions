import { useApi } from '@/hooks/useApi'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { SummaryResponse } from '@/lib/api-client'

/**
 * Summaries explorer (G8).
 *
 * Navigates the variable-depth scope trie and renders the three lenses
 * (task / patterns / decisions) for a scope at a time grain. This tracer
 * shell reads the default (root) scope; breadcrumb drilldown, grain/bucket
 * and eval selectors land in later G8 tickets.
 */

const LENSES = [
  { key: 'task_summary', title: 'Task & ubiquitous language', testid: 'lens-task' },
  { key: 'patterns', title: 'Architectural patterns', testid: 'lens-patterns' },
  { key: 'decisions_values', title: 'Decisions & values', testid: 'lens-decisions' },
] as const

export default function Summaries() {
  // Default scope is the root (''), at day grain — the all-domains summary.
  const { data, loading } = useApi<SummaryResponse>('/summaries/scope?path=&grain=day&bucket=')

  const lenses = data?.status === 'summarised' ? data.lenses : null
  const empty = !loading && data?.status !== 'summarised'

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Summaries</h1>
      <p className="text-sm text-muted-foreground">
        A three-lens view of the developer's typed prompts, rolled up across the variable-depth
        scope hierarchy (root → domain → project → session) at a chosen time grain.
      </p>

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

      {empty ? (
        <p className="text-sm text-muted-foreground" data-testid="summaries-empty">
          This scope has no summary yet. Run the summariser to populate it.
        </p>
      ) : null}
    </div>
  )
}
