import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '@/hooks/useApi'
import { useFilters } from '@/hooks/useFilters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatProjectName, formatCurrency } from '@/lib/formatters'
import type { SessionListItem } from '@/lib/api-client'
import { ExternalLink, FolderOpen, Coins, MessageSquare, FileText } from 'lucide-react'

interface ProjectSummary {
  project_id: string
  session_count: number
  event_count: number
  subagent_count: number
  total_cost: number
  last_active: string | null
}

export default function SessionsList() {
  const { buildApiQuery, filterSearchString } = useFilters()
  const { data: sessions, loading, error } = useApi<SessionListItem[]>(`/sessions${buildApiQuery()}`)

  // Aggregate sessions by project
  const projectSummaries = useMemo(() => {
    if (!sessions) return []

    const projectMap = new Map<string, ProjectSummary>()

    sessions.forEach((session) => {
      const existing = projectMap.get(session.project_id)
      const lastActive = session.last_timestamp

      if (existing) {
        existing.session_count += 1
        existing.event_count += Number(session.event_count) || 0
        existing.subagent_count += Number(session.subagent_count) || 0
        existing.total_cost += Number(session.total_cost_usd) || 0
        // Keep the most recent timestamp
        if (lastActive && (!existing.last_active || lastActive > existing.last_active)) {
          existing.last_active = lastActive
        }
      } else {
        projectMap.set(session.project_id, {
          project_id: session.project_id,
          session_count: 1,
          event_count: Number(session.event_count) || 0,
          subagent_count: Number(session.subagent_count) || 0,
          total_cost: Number(session.total_cost_usd) || 0,
          last_active: lastActive || null,
        })
      }
    })

    // Sort by most recent activity
    return Array.from(projectMap.values()).sort((a, b) => {
      if (!a.last_active) return 1
      if (!b.last_active) return -1
      return b.last_active.localeCompare(a.last_active)
    })
  }, [sessions])

  // Calculate overall stats
  const overallStats = useMemo(() => {
    if (!projectSummaries.length)
      return { totalProjects: 0, totalSessions: 0, totalCost: 0, totalEvents: 0 }
    return {
      totalProjects: projectSummaries.length,
      totalSessions: projectSummaries.reduce((acc, p) => acc + p.session_count, 0),
      totalCost: projectSummaries.reduce((acc, p) => acc + p.total_cost, 0),
      totalEvents: projectSummaries.reduce((acc, p) => acc + p.event_count, 0),
    }
  }, [projectSummaries])

  if (loading) return <div className="text-center py-8">Loading sessions...</div>
  if (error) return <div className="text-center py-8 text-red-500">Error: {error}</div>

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Sessions</h1>

      {/* Overall Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <FolderOpen className="h-8 w-8 text-primary" />
              <div>
                <p className="text-sm text-muted-foreground">Projects</p>
                <p className="text-2xl font-bold">{overallStats.totalProjects}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <MessageSquare className="h-8 w-8 text-primary" />
              <div>
                <p className="text-sm text-muted-foreground">Total Sessions</p>
                <p className="text-2xl font-bold">{overallStats.totalSessions.toLocaleString()}</p>
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
                <p className="text-2xl font-bold">{overallStats.totalEvents.toLocaleString()}</p>
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
                <p className="text-2xl font-bold">{formatCurrency(overallStats.totalCost)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Project Cards */}
      {projectSummaries.length === 0 ? (
        <Card>
          <CardContent className="py-12">
            <p className="text-center text-muted-foreground">
              No sessions found for the selected filters
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projectSummaries.map((project) => (
            <Link
              key={project.project_id}
              to={`/sessions/${encodeURIComponent(project.project_id)}${filterSearchString}`}
              className="block group"
            >
              <Card className="h-full transition-colors hover:border-primary/50 hover:bg-muted/30">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center justify-between text-lg">
                    <span className="truncate group-hover:text-primary transition-colors">
                      {formatProjectName(project.project_id)}
                    </span>
                    <ExternalLink className="h-4 w-4 text-muted-foreground group-hover:text-primary flex-shrink-0 ml-2" />
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Sessions</p>
                      <p className="font-semibold">{project.session_count.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Events</p>
                      <p className="font-semibold">{project.event_count.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Subagents</p>
                      <p className="font-semibold">
                        {project.subagent_count > 0 ? (
                          <span className="text-blue-600 dark:text-blue-400">
                            {project.subagent_count.toLocaleString()}
                          </span>
                        ) : (
                          '-'
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Cost</p>
                      <p className="font-semibold font-mono">{formatCurrency(project.total_cost)}</p>
                    </div>
                  </div>
                  {project.last_active && (
                    <p className="text-xs text-muted-foreground mt-3">
                      Last active: {new Date(project.last_active).toLocaleString()}
                    </p>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
