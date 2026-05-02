// Ambient declarations for cytoscape extensions and the React wrapper.
// None of these ship .d.ts files; the surfaces we use are loose enough
// that the loose typing is acceptable — the main `cytoscape` types
// provide the full Core/Element typing.

declare module 'cytoscape-fcose' {
  const fcose: unknown
  export default fcose
}

declare module 'cytoscape-elk' {
  const elk: unknown
  export default elk
}

declare module 'react-cytoscapejs' {
  import type { ComponentType, CSSProperties } from 'react'
  import type { Core, ElementDefinition, StylesheetStyle } from 'cytoscape'

  export interface CytoscapeComponentProps {
    elements: ElementDefinition[]
    stylesheet?: StylesheetStyle[] | unknown[]
    style?: CSSProperties
    cy?: (cy: Core) => void
    layout?: { name: string; [key: string]: unknown }
    minZoom?: number
    maxZoom?: number
    wheelSensitivity?: number
    pan?: { x?: number; y?: number }
    zoom?: number
    boxSelectionEnabled?: boolean
    autoungrabify?: boolean
    autounselectify?: boolean
    headless?: boolean
  }

  const CytoscapeComponent: ComponentType<CytoscapeComponentProps>
  export default CytoscapeComponent
}
