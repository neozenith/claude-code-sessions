import { NavLink } from 'react-router-dom'
import { ReactNode } from 'react'
import { LayoutDashboard, Calendar, CalendarDays, CalendarRange, Clock, Timer, FolderOpen, Layers } from 'lucide-react'
import { cn } from '@/lib/utils'

interface LayoutProps {
  children: ReactNode
}

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/hourly', label: 'Hourly', icon: Clock },
  { path: '/hour-of-day', label: 'Hour of Day', icon: Timer },
  { path: '/daily', label: 'Daily', icon: Calendar },
  { path: '/weekly', label: 'Weekly', icon: CalendarDays },
  { path: '/monthly', label: 'Monthly', icon: CalendarRange },
  { path: '/projects', label: 'Projects', icon: FolderOpen },
  { path: '/drilldown', label: 'Drill-Down', icon: Layers },
]

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-64 bg-card border-r">
        <div className="p-4 border-b">
          <h1 className="text-xl font-bold">Claude Code</h1>
          <p className="text-sm text-muted-foreground">Session Analytics</p>
        </div>
        <nav className="p-4">
          <ul className="space-y-2">
            {navItems.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
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
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">
        {children}
      </main>
    </div>
  )
}
