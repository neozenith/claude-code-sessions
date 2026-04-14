/**
 * Re-export of react-plotly.js Plot component using the factory pattern.
 *
 * Vite 8's CJS interop wraps `require()` results as `export default { default: X }`
 * instead of `export default X`. We must unwrap `.default` on both the factory
 * function and the Plotly library to get the actual values.
 */
import type { PlotParams } from 'react-plotly.js'

// @ts-expect-error — plotly.js/dist/plotly has no type declarations
import _PlotlyModule from 'plotly.js/dist/plotly'
import _factoryModule from 'react-plotly.js/factory'

// Vite 8 CJS interop: `import X from 'cjs-pkg'` gives `{ default: actual }` not `actual`
type MaybeWrapped = { default?: unknown }
const unwrap = (m: unknown): unknown => {
  const mod = m as MaybeWrapped
  return mod && typeof mod === 'object' && 'default' in mod && typeof mod.default === 'function'
    ? mod.default
    : m
}

const createPlotlyComponent = unwrap(_factoryModule) as (plotly: object) => React.ComponentType<PlotParams>
const Plotly = unwrap(_PlotlyModule) as object

const Plot = createPlotlyComponent(Plotly)
export default Plot
