import { NavLink } from 'react-router-dom'
import { ReactNode, useEffect, useMemo, useState } from 'react'
import {
  LayoutDashboard,
  Calendar,
  CalendarDays,
  CalendarRange,
  Clock,
  Timer,
  Activity,
  GitBranch,
  Sun,
  Moon,
  Monitor,
  History,
  PanelLeftClose,
  PanelLeftOpen,
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
  { path: '/sessions', label: 'Sessions', icon: History },
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

const SIDEBAR_COLLAPSED_KEY = 'sidebar:collapsed'

export default function Layout({ children }: LayoutProps) {
  const { filters, setFilters, filterSearchString } = useFilters()
  const { theme, setTheme } = useTheme()

  // Sidebar collapse state is persisted to localStorage so a refresh
  // keeps the user's choice. Default to expanded on first visit.
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'
  })
  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0')
  }, [collapsed])

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
      {/* Sidebar — width animates between expanded (w-64) and collapsed
          (w-16, icon-only). The collapsed state persists to localStorage. */}
      <aside
        className={cn(
          'bg-card border-r flex flex-col transition-[width] duration-200',
          collapsed ? 'w-16' : 'w-64'
        )}
      >
        {/* Header row: title + collapse toggle. When collapsed the title
            is hidden and only the toggle button remains, centered. */}
        <div
          className={cn(
            'border-b flex items-center',
            collapsed ? 'justify-center p-2' : 'justify-between p-4'
          )}
        >
          {!collapsed && (
            <div>
              <h1 className="text-xl font-bold">Claude Code</h1>
              <p className="text-sm text-muted-foreground">Session Analytics</p>
            </div>
          )}
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-accent"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Navigation */}
        <nav className={cn('flex-1 overflow-y-auto', collapsed ? 'p-2' : 'p-4')}>
          <ul className="space-y-2">
            {navItems.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={buildNavTo(item.path)}
                  // `title` gives a native tooltip with the full label when
                  // the sidebar is collapsed to icons only.
                  title={collapsed ? item.label : undefined}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center rounded-lg transition-colors',
                      collapsed ? 'justify-center p-2' : 'px-4 py-2',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                    )
                  }
                >
                  <item.icon className={cn('h-4 w-4', !collapsed && 'mr-3')} />
                  {!collapsed && item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* Theme Toggle — horizontal when expanded, vertical when collapsed
            so the three buttons still fit in a 64px column. */}
        <div className={cn('border-t', collapsed ? 'p-2' : 'p-4')}>
          {!collapsed && (
            <p className="text-xs text-muted-foreground mb-2">Theme</p>
          )}
          <div
            className={cn(
              'bg-muted rounded-lg p-1',
              collapsed ? 'flex flex-col gap-1' : 'flex items-center gap-1'
            )}
          >
            <button
              onClick={() => setTheme('light')}
              className={cn(
                'flex items-center justify-center p-2 rounded-md transition-colors',
                collapsed ? 'w-full' : 'flex-1',
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
                'flex items-center justify-center p-2 rounded-md transition-colors',
                collapsed ? 'w-full' : 'flex-1',
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
                'flex items-center justify-center p-2 rounded-md transition-colors',
                collapsed ? 'w-full' : 'flex-1',
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
