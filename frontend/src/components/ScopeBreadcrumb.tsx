import { Link, useSearchParams } from 'react-router-dom'

import type { ScopeChild } from '@/lib/api-client'

/**
 * ScopeBreadcrumb (G8) — a reusable up/down lineage navigator over a
 * variable-depth `scope_path`. Crumbs render one per segment (root-first,
 * leaf-last) and link to that ancestor prefix; optional child links extend the
 * path one level down. All navigation is page-local `?path=` URL state
 * (ADR8.1), so it deep-links and is shared with SessionDetail (G9, ADR9.2).
 */

interface ScopeBreadcrumbProps {
  scopePath: string
  /** Immediate child scopes to render as drill-down links (G7 listScopeChildren). */
  childScopes?: ScopeChild[]
  /**
   * Override the crumb/child href for a scope_path. Defaults to an in-place
   * `?path=` on the current route (explorer). SessionDetail (G9) passes a builder
   * that targets the explorer route `/claims?path=…` carrying only the global
   * filters, so the session links up to the explorer scope (ADR9.2).
   */
  linkTo?: (scopePath: string) => string
  /**
   * Hard-pin mode: render the lineage as static text (no up/down navigation).
   * Used when the global Project filter pins the explorer to one project's scope —
   * drilling away would contradict the pin (the user clears the filter to regain it).
   */
  disabled?: boolean
}

export default function ScopeBreadcrumb({
  scopePath,
  childScopes,
  linkTo,
  disabled = false,
}: ScopeBreadcrumbProps) {
  const [searchParams] = useSearchParams()

  // Build a `?path=` href that sets path (or clears it at root) while
  // preserving every other current param (days/project/grain/…).
  const toPath = (path: string): string => {
    if (linkTo) return linkTo(path)
    const next = new URLSearchParams(searchParams)
    if (path === '') {
      next.delete('path')
    } else {
      next.set('path', path)
    }
    const qs = next.toString()
    return qs ? `?${qs}` : '?'
  }

  const segments = scopePath ? scopePath.split('/') : []
  const crumbs = segments.map((label, i) => ({
    label,
    path: segments.slice(0, i + 1).join('/'),
  }))

  if (disabled) {
    return (
      <nav
        aria-label="scope lineage"
        data-testid="scope-breadcrumb-pinned"
        className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground"
      >
        <span data-testid="scope-crumb-root">All</span>
        {crumbs.map((crumb) => (
          <span key={crumb.path} className="flex items-center gap-1">
            <span>/</span>
            <span data-testid="scope-crumb" className="font-medium text-foreground">
              {crumb.label}
            </span>
          </span>
        ))}
        <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs">pinned</span>
      </nav>
    )
  }

  return (
    <div className="space-y-2">
      <nav aria-label="scope lineage" className="flex flex-wrap items-center gap-1 text-sm">
        <Link data-testid="scope-crumb-root" to={toPath('')} className="hover:underline">
          All
        </Link>
        {crumbs.map((crumb) => (
          <span key={crumb.path} className="flex items-center gap-1">
            <span className="text-muted-foreground">/</span>
            <Link data-testid="scope-crumb" to={toPath(crumb.path)} className="hover:underline">
              {crumb.label}
            </Link>
          </span>
        ))}
      </nav>

      {childScopes && childScopes.length > 0 ? (
        <ul className="flex flex-wrap gap-2 text-sm">
          {childScopes.map((child) => (
            <li key={child.scope_path}>
              <Link
                data-testid="scope-child"
                to={toPath(child.scope_path)}
                className="rounded border px-2 py-0.5 hover:bg-muted"
              >
                {child.scope_path.split('/').slice(-1)[0]}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
