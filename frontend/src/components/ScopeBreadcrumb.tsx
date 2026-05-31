/**
 * ScopeBreadcrumb (G8) — a reusable up/down lineage breadcrumb over a
 * variable-depth `scope_path`, rendering one crumb per segment root-first,
 * leaf-last. Each crumb carries its cumulative prefix so a consumer can drill
 * up the trie (T8.3); shared with SessionDetail (G9, ADR9.2).
 */

interface ScopeBreadcrumbProps {
  scopePath: string
  /** Called with a crumb's cumulative scope_path when clicked (drill-up). */
  onNavigate?: (scopePath: string) => void
}

export default function ScopeBreadcrumb({ scopePath, onNavigate }: ScopeBreadcrumbProps) {
  const segments = scopePath ? scopePath.split('/') : []
  const crumbs = segments.map((label, i) => ({
    label,
    path: segments.slice(0, i + 1).join('/'),
  }))

  return (
    <nav aria-label="scope lineage" className="flex flex-wrap items-center gap-1 text-sm">
      {crumbs.map((crumb, i) => (
        <span key={crumb.path} className="flex items-center gap-1">
          {i > 0 ? <span className="text-muted-foreground">/</span> : null}
          <button
            type="button"
            data-testid="scope-crumb"
            className="hover:underline"
            onClick={() => onNavigate?.(crumb.path)}
          >
            {crumb.label}
          </button>
        </span>
      ))}
    </nav>
  )
}
