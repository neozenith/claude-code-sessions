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
}

export default function ScopeBreadcrumb({ scopePath, childScopes }: ScopeBreadcrumbProps) {
  const [searchParams] = useSearchParams()

  // Build a `?path=` href that sets path (or clears it at root) while
  // preserving every other current param (days/project/grain/…).
  const toPath = (path: string): string => {
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
