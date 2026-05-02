/**
 * Right-panel controls for the Knowledge Graph page.
 *
 * Each control writes to a URL search param (or clears it back to the
 * default). The parent <KnowledgeGraph> component is the single source
 * of truth for state — these are dumb, controlled inputs.
 */

import type { KGCommunity, KGEdge, KGNode, KGPayload, SeedMetric } from '@/lib/kg-client'

export type LayoutEngine = 'fcose' | 'elk' | 'grid'
export type SizeMode = 'uniform' | 'degree' | 'betweenness'

export type Selection =
  | { kind: 'node'; node: KGNode }
  | { kind: 'edge'; edge: KGEdge }
  | { kind: 'community'; community: KGCommunity }

export const DEFAULT_TOP_N = 2
export const DEFAULT_SEED_METRIC: SeedMetric = 'edge_betweenness'
export const DEFAULT_MAX_DEPTH = 1
export const DEFAULT_MIN_DEGREE = 5
export const DEFAULT_LAYOUT: LayoutEngine = 'fcose'
export const DEFAULT_SIZE_MODE: SizeMode = 'degree'

export const DEFAULT_FCOSE_CONFIG = {
  quality: 'default',
  randomize: true,
  animate: false,
  fit: true,
  padding: 30,
  nodeRepulsion: 4500,
  idealEdgeLength: 50,
  edgeElasticity: 0.45,
  nestingFactor: 0.1,
  gravity: 0.25,
  gravityRangeCompound: 1.5,
  gravityCompound: 1.0,
  gravityRange: 3.8,
  initialEnergyOnIncremental: 0.3,
  tile: true,
  numIter: 2500,
}

export const DEFAULT_FCOSE_CONFIG_JSON = JSON.stringify(DEFAULT_FCOSE_CONFIG, null, 2)

interface Props {
  topN: number
  seedMetric: SeedMetric
  maxDepth: number
  minDegree: number
  layoutEngine: LayoutEngine
  sizeMode: SizeMode
  fcoseConfig: string
  fcoseConfigError: string | null
  onTopNChange: (v: number) => void
  onSeedMetricChange: (v: SeedMetric) => void
  onMaxDepthChange: (v: number) => void
  onMinDegreeChange: (v: number) => void
  onLayoutChange: (v: LayoutEngine) => void
  onSizeModeChange: (v: SizeMode) => void
  onFcoseConfigChange: (v: string) => void
  onFcoseConfigReset: () => void
  onApplyLayout: () => void
  payload: KGPayload | null
  selection: Selection | null
  onClearSelection: () => void
}

export default function KnowledgeGraphControls({
  topN,
  seedMetric,
  maxDepth,
  minDegree,
  layoutEngine,
  sizeMode,
  fcoseConfig,
  fcoseConfigError,
  onTopNChange,
  onSeedMetricChange,
  onMaxDepthChange,
  onMinDegreeChange,
  onLayoutChange,
  onSizeModeChange,
  onFcoseConfigChange,
  onFcoseConfigReset,
  onApplyLayout,
  payload,
  selection,
  onClearSelection,
}: Props): JSX.Element {
  return (
    <aside
      data-testid="kg-controls"
      className="flex w-80 shrink-0 flex-col gap-4 overflow-y-auto border-l border-border bg-card p-4 text-sm"
    >
      {selection && <SelectionPanel selection={selection} onClear={onClearSelection} />}

      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Data
        </h2>
        {payload && (
          <p className="text-xs text-muted-foreground" data-testid="kg-loaded-count">
            {payload.node_count}/{payload.total_node_count} nodes loaded
          </p>
        )}

        <label className="flex flex-col gap-1" data-testid="kg-control-seed-metric">
          <span>Seed metric</span>
          <select
            value={seedMetric}
            onChange={(e) => onSeedMetricChange(e.target.value as SeedMetric)}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          >
            <option value="edge_betweenness">edge betweenness</option>
            <option value="node_betweenness">node betweenness</option>
            <option value="degree">degree</option>
          </select>
        </label>

        <label className="flex flex-col gap-1" data-testid="kg-control-top-n">
          <span>Max seed nodes</span>
          <input
            type="number"
            min={1}
            step={1}
            value={topN}
            onChange={(e) => onTopNChange(Number(e.target.value))}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          />
          <input
            type="range"
            min={1}
            max={500}
            step={1}
            value={topN}
            onChange={(e) => onTopNChange(Number(e.target.value))}
            className="w-full"
            aria-label="Top-N slider"
          />
        </label>

        <label className="flex flex-col gap-1" data-testid="kg-control-max-depth">
          <span>Max depth (0 = unlimited)</span>
          <input
            type="number"
            min={0}
            step={1}
            value={maxDepth}
            onChange={(e) => onMaxDepthChange(Number(e.target.value))}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          />
        </label>

        <label className="flex flex-col gap-1" data-testid="kg-control-min-degree">
          <span>Min degree (prune isolates)</span>
          <input
            type="number"
            min={0}
            step={1}
            value={minDegree}
            onChange={(e) => onMinDegreeChange(Number(e.target.value))}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          />
        </label>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Layout
        </h2>
        <label className="flex flex-col gap-1" data-testid="kg-control-layout">
          <span>Engine</span>
          <select
            value={layoutEngine}
            onChange={(e) => onLayoutChange(e.target.value as LayoutEngine)}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          >
            <option value="fcose">fcose (force-directed)</option>
            <option value="elk">elk (hierarchical)</option>
            <option value="grid">grid</option>
          </select>
        </label>

        {layoutEngine === 'fcose' && (
          <div className="flex flex-col gap-1" data-testid="kg-control-fcose-config">
            <span>fcose config (JSON)</span>
            <textarea
              value={fcoseConfig}
              onChange={(e) => onFcoseConfigChange(e.target.value)}
              rows={14}
              spellCheck={false}
              className="rounded border border-input bg-background px-2 py-1 font-mono text-[10px] leading-snug"
            />
            {fcoseConfigError && (
              <p
                data-testid="kg-fcose-config-error"
                className="rounded border border-destructive/40 bg-destructive/10 px-2 py-1 text-[10px] text-destructive"
              >
                {fcoseConfigError}
              </p>
            )}
            <div className="flex gap-1">
              <button
                type="button"
                onClick={onApplyLayout}
                disabled={fcoseConfigError !== null}
                data-testid="kg-apply-layout"
                className="rounded border border-input bg-background px-2 py-1 text-xs hover:border-foreground/40 disabled:opacity-50"
              >
                Apply &amp; run
              </button>
              <button
                type="button"
                onClick={onFcoseConfigReset}
                data-testid="kg-reset-fcose-config"
                className="rounded border border-input bg-background px-2 py-1 text-xs hover:border-foreground/40"
              >
                Reset
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Styling
        </h2>
        <label className="flex flex-col gap-1" data-testid="kg-control-size-mode">
          <span>Node size by</span>
          <select
            value={sizeMode}
            onChange={(e) => onSizeModeChange(e.target.value as SizeMode)}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          >
            <option value="degree">degree</option>
            <option value="betweenness">node betweenness</option>
            <option value="uniform">uniform</option>
          </select>
        </label>
      </section>

      {payload && payload.communities.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Communities ({payload.communities.length})
          </h2>
          <ul className="flex max-h-64 flex-col gap-1 overflow-y-auto text-xs">
            {payload.communities.slice(0, 50).map((c) => (
              <li
                key={c.id}
                className="rounded border border-border bg-background px-2 py-1"
                data-testid={`kg-community-${c.id}`}
              >
                <div className="font-mono text-[10px] text-muted-foreground">#{c.id}</div>
                <div className="truncate">{c.label ?? `community ${c.id}`}</div>
                <div className="text-[10px] text-muted-foreground">
                  {c.member_count} member{c.member_count === 1 ? '' : 's'}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  )
}

interface SelectionPanelProps {
  selection: Selection
  onClear: () => void
}

const SelectionPanel = ({ selection, onClear }: SelectionPanelProps): JSX.Element => {
  return (
    <section
      data-testid="kg-selection"
      className="flex flex-col gap-2 rounded border border-foreground/30 bg-foreground/5 p-3"
    >
      <header className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide">
          Selected {selection.kind}
        </h2>
        <button
          type="button"
          onClick={onClear}
          aria-label="Clear selection"
          className="rounded px-1 text-xs text-muted-foreground hover:text-foreground"
        >
          ✕
        </button>
      </header>
      {selection.kind === 'node' && <NodeDetail node={selection.node} />}
      {selection.kind === 'edge' && <EdgeDetail edge={selection.edge} />}
      {selection.kind === 'community' && <CommunityDetail community={selection.community} />}
    </section>
  )
}

const Field = ({ label, value }: { label: string; value: string | number | null | undefined }): JSX.Element => (
  <div className="flex justify-between gap-2 text-xs">
    <span className="text-muted-foreground">{label}</span>
    <span className="break-all text-right font-mono">{value === null || value === undefined ? '—' : String(value)}</span>
  </div>
)

const NodeDetail = ({ node }: { node: KGNode }): JSX.Element => (
  <div className="flex flex-col gap-1" data-testid="kg-selection-node">
    <div className="break-all text-sm font-semibold">{node.label}</div>
    <Field label="id" value={node.id} />
    <Field label="entity type" value={node.entity_type} />
    <Field label="mention count" value={node.mention_count} />
    <Field label="community id" value={node.community_id} />
    <Field
      label="node betweenness"
      value={node.node_betweenness !== null ? node.node_betweenness.toFixed(4) : null}
    />
  </div>
)

const EdgeDetail = ({ edge }: { edge: KGEdge }): JSX.Element => (
  <div className="flex flex-col gap-1" data-testid="kg-selection-edge">
    <div className="break-all text-sm font-semibold">
      {edge.source} → {edge.target}
    </div>
    <Field label="rel type" value={edge.rel_type} />
    <Field label="weight" value={edge.weight !== null ? edge.weight.toFixed(3) : null} />
    <Field
      label="edge betweenness"
      value={edge.edge_betweenness !== null ? edge.edge_betweenness.toFixed(4) : null}
    />
  </div>
)

const CommunityDetail = ({ community }: { community: KGCommunity }): JSX.Element => {
  const sample = community.node_ids.slice(0, 30)
  return (
    <div className="flex flex-col gap-1" data-testid="kg-selection-community">
      <div className="break-all text-sm font-semibold">
        {community.label ?? `community #${community.id}`}
      </div>
      <Field label="id" value={community.id} />
      <Field label="member count" value={community.member_count} />
      <div className="mt-2 flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          Members ({sample.length}/{community.node_ids.length})
        </span>
        <ul className="flex max-h-48 flex-col gap-0.5 overflow-y-auto rounded border border-border bg-background p-1 font-mono text-[10px]">
          {sample.map((id) => (
            <li key={id} className="break-all">
              {id}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
