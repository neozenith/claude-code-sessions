import { render, screen, cleanup } from '@testing-library/react'
import { createElement } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import ScopeBreadcrumb from './ScopeBreadcrumb'

afterEach(cleanup)

describe('ScopeBreadcrumb', () => {
  it('renders one crumb per scope_path segment in order, root first, leaf last', () => {
    render(createElement(ScopeBreadcrumb, { scopePath: 'domain/client/project/module' }))

    const crumbs = screen.getAllByTestId('scope-crumb')
    expect(crumbs).toHaveLength(4)
    expect(crumbs.map((c) => c.textContent)).toEqual([
      'domain',
      'client',
      'project',
      'module',
    ])
  })
})
