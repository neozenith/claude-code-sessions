import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { createElement } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import ScopeBreadcrumb from './ScopeBreadcrumb'

afterEach(cleanup)

/** Renders the current router search string so tests can probe URL state. */
function LocationProbe() {
  const loc = useLocation()
  return createElement('div', { 'data-testid': 'loc' }, loc.search)
}

const currentPath = (): string | null =>
  new URLSearchParams(screen.getByTestId('loc').textContent ?? '').get('path')

describe('ScopeBreadcrumb', () => {
  it('renders one crumb per scope_path segment in order, root first, leaf last', () => {
    render(
      createElement(
        MemoryRouter,
        null,
        createElement(ScopeBreadcrumb, { scopePath: 'domain/client/project/module' }),
      ),
    )

    const crumbs = screen.getAllByTestId('scope-crumb')
    expect(crumbs).toHaveLength(4)
    expect(crumbs.map((c) => c.textContent)).toEqual([
      'domain',
      'client',
      'project',
      'module',
    ])
  })

  it('ancestor crumb truncates path and child link extends it (URL state)', () => {
    render(
      createElement(
        MemoryRouter,
        { initialEntries: ['/summaries?path=clients/acme'] },
        createElement(ScopeBreadcrumb, {
          scopePath: 'clients/acme',
          childScopes: [{ scope_path: 'clients/acme/app', scope_depth: 3 }],
        }),
        createElement(LocationProbe),
      ),
    )

    // Drill DOWN: clicking the child link extends ?path= by one segment.
    fireEvent.click(screen.getByTestId('scope-child'))
    expect(currentPath()).toBe('clients/acme/app')

    // Drill UP: clicking the 'clients' ancestor crumb truncates ?path=.
    const clientsCrumb = screen.getAllByTestId('scope-crumb')[0]
    fireEvent.click(clientsCrumb)
    expect(currentPath()).toBe('clients')
  })
})
