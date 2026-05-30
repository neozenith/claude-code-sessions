/**
 * Shared message-kind option catalog.
 *
 * Both SessionDetail and SearchPage expose a dropdown filter for
 * `message_kind`; the option labels + descriptions must stay identical
 * across the two so the filter feels coherent. Keeping a single source
 * here is cheaper than cross-referencing two arrays.
 */
import type { MessageKind } from '@/lib/api-client'

export interface MsgKindOption {
  /** '' means "no filter — show all kinds". */
  value: MessageKind | ''
  label: string
  description: string
}

export const MSG_KIND_OPTIONS: MsgKindOption[] = [
  { value: '', label: 'All messages', description: 'Show everything' },
  { value: 'human', label: 'Human prompt', description: 'Actual typed user input' },
  { value: 'task_notification', label: 'Task notification', description: 'Async task completion callbacks' },
  { value: 'assistant_text', label: 'Assistant text', description: 'Model text responses' },
  { value: 'thinking', label: 'Thinking', description: 'Extended thinking blocks' },
  { value: 'tool_use', label: 'Tool call', description: 'Tool invocations by the model' },
  { value: 'tool_result', label: 'Tool result', description: 'Output returned from tools' },
  { value: 'user_text', label: 'User text', description: 'User messages with text blocks' },
  { value: 'meta', label: 'Meta / injected', description: 'System-injected context (isMeta=true)' },
  { value: 'other', label: 'System / progress', description: 'Progress, system, queue-operation events' },
]

/**
 * Subagent dimension (G3 ADR): a `?scope=` param orthogonal to `?msg=`.
 * Subagent events carry a `subagent-<base>` kind; the base kind is recovered
 * by stripping the prefix when matching, so `?msg=tool_use` matches both
 * `tool_use` and `subagent-tool_use` unless `?scope=` narrows it.
 */
export const SUBAGENT_PREFIX = 'subagent-'

/** Subagent scope filter: all kinds, main-thread only, or subagent only. */
export type Scope = 'all' | 'main' | 'subagent'

/** The base kind with any `subagent-` prefix stripped. */
export const baseKind = (kind: string): string =>
  kind.startsWith(SUBAGENT_PREFIX) ? kind.slice(SUBAGENT_PREFIX.length) : kind

export const isSubagentKind = (kind: string): boolean => kind.startsWith(SUBAGENT_PREFIX)

/**
 * Whether an event of `kind` passes the composed `{msg, scope}` filter.
 * `msg` is a base kind ('' = any). `scope` narrows by subagent-ness.
 * The two compose: e.g. msg='tool_use' + scope='subagent' → subagent tool calls.
 */
export const matchesKindFilter = (kind: string, msg: string, scope: Scope = 'all'): boolean => {
  if (scope === 'subagent' && !isSubagentKind(kind)) return false
  if (scope === 'main' && isSubagentKind(kind)) return false
  if (msg && baseKind(kind) !== baseKind(msg)) return false
  return true
}
