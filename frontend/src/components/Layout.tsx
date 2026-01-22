import { NavLink } from 'react-router-dom'
import { ReactNode, useMemo } from 'react'
import {
  LayoutDashboard,
  Calendar,
  CalendarDays,
  CalendarRange,
  Clock,
  Timer,
  FolderOpen,
  Activity,
  GitBranch,
  Sun,
  Moon,
  Monitor,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useFilters, TIME_RANGE_OPTIONS } from '@/hooks/useFilters'
import { useTheme } from '@/contexts/ThemeContext'
import { useApi } from '@/hooks/useApi'

interface LayoutProps {
  children: ReactNode
}

interface Project {
  project_id: string
  total_cost_usd: number
  session_count: number
  event_count: number
}

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/hourly', label: 'Hourly', icon: Clock },
  { path: '/hour-of-day', label: 'Hour of Day', icon: Timer },
  { path: '/daily', label: 'Daily', icon: Calendar },
  { path: '/weekly', label: 'Weekly', icon: CalendarDays },
  { path: '/monthly', label: 'Monthly', icon: CalendarRange },
  { path: '/projects', label: 'Projects', icon: FolderOpen },
  { path: '/timeline', label: 'Timeline', icon: Activity },
  { path: '/schema-timeline', label: 'Schema Timeline', icon: GitBranch },
]

// Format project name for display
function formatProjectName(projectId: string): string {
  return projectId
    .replace(/^-Users-[^-]+-/, '') // Remove -Users-username- prefix
    .replace(/-/g, '/') // Replace hyphens with slashes
    .replace(/^\//, '') // Remove leading slash if any
}

export default function Layout({ children }: LayoutProps) {
  const { filters, setFilters, filterSearchString } = useFilters()
  const { theme, setTheme } = useTheme()

  // Build project list URL with time range filter
  // This makes the project dropdown update when time range changes
  const projectsUrl = useMemo(() => {
    const params = new URLSearchParams()
    if (filters.days !== null && filters.days > 0) {
      params.set('days', String(filters.days))
    }
    const queryString = params.toString()
    return queryString ? `/projects?${queryString}` : '/projects'
  }, [filters.days])

  const { data: projects } = useApi<Project[]>(projectsUrl)

  // Projects are already sorted by cost from the API
  const sortedProjects = useMemo(() => {
    return projects ?? []
  }, [projects])

  // Build NavLink to preserve query params
  const buildNavTo = (path: string) => {
    return filterSearchString ? `${path}${filterSearchString}` : path
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-64 bg-card border-r flex flex-col">
        <div className="p-4 border-b">
          <h1 className="text-xl font-bold">Claude Code</h1>
          <p className="text-sm text-muted-foreground">Session Analytics</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 overflow-y-auto">
          <ul className="space-y-2">
            {navItems.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={buildNavTo(item.path)}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center px-4 py-2 rounded-lg transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                    )
                  }
                >
                  <item.icon className="mr-3 h-4 w-4" />
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* Theme Toggle */}
        <div className="p-4 border-t">
          <p className="text-xs text-muted-foreground mb-2">Theme</p>
          <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
            <button
              onClick={() => setTheme('light')}
              className={cn(
                'flex-1 flex items-center justify-center p-2 rounded-md transition-colors',
                theme === 'light'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              title="Light mode"
            >
              <Sun className="h-4 w-4" />
            </button>
            <button
              onClick={() => setTheme('dark')}
              className={cn(
                'flex-1 flex items-center justify-center p-2 rounded-md transition-colors',
                theme === 'dark'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              title="Dark mode"
            >
              <Moon className="h-4 w-4" />
            </button>
            <button
              onClick={() => setTheme('system')}
              className={cn(
                'flex-1 flex items-center justify-center p-2 rounded-md transition-colors',
                theme === 'system'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              title="System preference"
            >
              <Monitor className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Global Filters Header */}
        <header className="bg-card border-b px-6 py-3">
          <div className="flex items-center gap-4">
            {/* Time Range Filter */}
            <div className="flex items-center gap-2">
              <label className="text-sm text-muted-foreground">Time Range:</label>
              <select
                value={filters.days ?? 30}
                onChange={(e) => {
                  const value = parseInt(e.target.value, 10)
                  setFilters({ days: value === 30 ? null : value })
                }}
                className="px-3 py-1.5 border rounded-lg bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {TIME_RANGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Project Filter */}
            <div className="flex items-center gap-2">
              <label className="text-sm text-muted-foreground">Project:</label>
              <select
                value={filters.project ?? ''}
                onChange={(e) => setFilters({ project: e.target.value || null })}
                className="px-3 py-1.5 border rounded-lg bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary max-w-[300px]"
              >
                <option value="">All Projects</option>
                {sortedProjects.map((project) => (
                  <option key={project.project_id} value={project.project_id}>
                    {formatProjectName(project.project_id)}
                  </option>
                ))}
              </select>
            </div>

            {/* Filter indicator */}
            {(filters.days !== 30 || filters.project) && (
              <button
                onClick={() => setFilters({ days: null, project: null })}
                className="text-xs text-muted-foreground hover:text-foreground underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  )
}
