import { useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatProjectName, formatSessionId, formatCurrency } from '@/lib/formatters'
import type { SessionListItem } from '@/lib/api-client'
import { ExternalLink, Clock, ChevronLeft, FileText, MessageSquare, Coins } from 'lucide-react'

// Helper to format filepath for display - shows just the filename
function formatFilepath(filepath: string): string {
  if (!filepath) return '-'
  const parts = filepath.split('/')
  return parts[parts.length - 1] || filepath
}

export default function ProjectSessions() {
  const { projectId } = useParams<{ projectId: string }>()
  const { buildApiQuery, filterSearchString } = useFilters()

  // Fetch sessions filtered to this project
  const apiQuery = buildApiQuery({ project: projectId ?? null })
  const { data: sessions, loading, error } = useApi<SessionListItem[]>(`/sessions${apiQuery}`)

  // Filter to only this project's sessions (in case API returns others)
  const projectSessions = useMemo(() => {
    if (!sessions) return []
    return sessions.filter((s) => s.project_id === projectId)
  }, [sessions, projectId])

  // Calculate summary stats
  const summaryStats = useMemo(() => {
    if (!projectSessions.length) return { totalSessions: 0, totalCost: 0, totalEvents: 0 }
    return {
      totalSessions: projectSessions.length,
      totalCost: projectSessions.reduce((acc, s) => acc + (Number(s.total_cost_usd) || 0), 0),
      totalEvents: projectSessions.reduce((acc, s) => acc + (Number(s.event_count) || 0), 0),
    }
  }, [projectSessions])

  if (!projectId) {
    return <div className="text-center py-8 text-red-500">Missing project ID</div>
  }

  if (loading) return <div className="text-center py-8">Loading sessions...</div>
  if (error) return <div className="text-center py-8 text-red-500">Error: {error}</div>

  return (
    <div className="space-y-6">
      {/* Header with breadcrumb */}
      <div className="flex items-center gap-4">
        <Link
          to={`/sessions${filterSearchString}`}
          className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          Back to Projects
        </Link>
      </div>

      <div>
        <h1 className="text-3xl font-bold">{formatProjectName(projectId)}</h1>
        <p className="text-muted-foreground mt-1 font-mono text-sm">{projectId}</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <MessageSquare className="h-8 w-8 text-primary" />
              <div>
                <p className="text-sm text-muted-foreground">Total Sessions</p>
                <p className="text-2xl font-bold">{summaryStats.totalSessions.toLocaleString()}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <Coins className="h-8 w-8 text-primary" />
              <div>
                <p className="text-sm text-muted-foreground">Total Cost</p>
                <p className="text-2xl font-bold">{formatCurrency(summaryStats.totalCost)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <FileText className="h-8 w-8 text-primary" />
              <div>
                <p className="text-sm text-muted-foreground">Total Events</p>
                <p className="text-2xl font-bold">{summaryStats.totalEvents.toLocaleString()}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Sessions Table */}
      {projectSessions.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">
              No sessions found for this project in the selected time range
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-4 font-medium">Session ID</th>
                    <th className="text-left py-3 px-4 font-medium">
                      <FileText className="inline h-4 w-4 mr-1" />
                      File
                    </th>
                    <th className="text-left py-3 px-4 font-medium">
                      <Clock className="inline h-4 w-4 mr-1" />
                      Last Active
                    </th>
                    <th className="text-right py-3 px-4 font-medium">Events</th>
                    <th className="text-right py-3 px-4 font-medium">Subagents</th>
                    <th className="text-right py-3 px-4 font-medium">Cost</th>
                    <th className="text-right py-3 px-4 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {projectSessions.map((session) => (
                    <tr
                      key={session.session_id}
                      className="border-b last:border-0 hover:bg-muted/50 transition-colors"
                    >
                      <td className="py-3 px-4 font-mono text-sm">
                        {formatSessionId(session.session_id, 24)}
                      </td>
                      <td
                        className="py-3 px-4 text-sm text-muted-foreground"
                        title={session.filepath}
                      >
                        {formatFilepath(session.filepath)}
                      </td>
                      <td className="py-3 px-4 text-sm text-muted-foreground">
                        {session.last_timestamp
                          ? new Date(session.last_timestamp).toLocaleString()
                          : 'N/A'}
                      </td>
                      <td className="py-3 px-4 text-right">{session.event_count.toLocaleString()}</td>
                      <td className="py-3 px-4 text-right">
                        {session.subagent_count > 0 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                            {session.subagent_count}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right font-mono">
                        {formatCurrency(Number(session.total_cost_usd) || 0)}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <Link
                          to={`/sessions/${encodeURIComponent(session.project_id)}/${encodeURIComponent(session.session_id)}${filterSearchString}`}
                          className="inline-flex items-center gap-1 px-3 py-1 text-sm text-primary hover:text-primary/80 hover:underline"
                        >
                          View <ExternalLink className="h-3 w-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
