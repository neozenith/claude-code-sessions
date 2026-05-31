/**
 * Shared message-kind option catalog.
 *
 * Both SessionDetail and SearchPage expose a dropdown filter for
 * `message_kind`; the option labels + descriptions must stay identical
 * across the two so the filter feels coherent. Keeping a single source
 * here is cheaper than cross-referencing two arrays.
 */
import type { BaseMessageKind, MessageKind } from '@/lib/api-client'

export interface MsgKindOption {
  /** '' means "no filter — show all kinds". */
  value: MessageKind | ''
  label: string
  description: string
}

/** The 9 base kinds with their human-facing label + description. */
const BASE_KIND_OPTIONS: { value: BaseMessageKind; label: string; description: string }[] = [
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
 * The flat 19-option catalog (ADR9.1): "All messages" + the 18 canonical
 * `msg_kind` values (9 base × {main, `subagent-`}). Every kind — including
 * each `subagent-*` variant — is directly selectable from one control.
 */
export const MSG_KIND_OPTIONS: MsgKindOption[] = [
  { value: '', label: 'All messages', description: 'Show everything' },
  ...BASE_KIND_OPTIONS,
  ...BASE_KIND_OPTIONS.map(
    (b): MsgKindOption => ({
      value: `subagent-${b.value}`,
      label: `Subagent: ${b.label}`,
      description: `${b.description} (subagent context)`,
    }),
  ),
]

/** Prefix marking a subagent-context kind (`subagent-<base>`). */
export const SUBAGENT_PREFIX = 'subagent-'

/**
 * The base kind with any `subagent-` prefix stripped. Used only for shared
 * *styling* (a subagent event reuses its base kind's colour/icon); filtering is
 * exact on the full kind value (see `matchesKind`).
 */
export const baseKind = (kind: string): string =>
  kind.startsWith(SUBAGENT_PREFIX) ? kind.slice(SUBAGENT_PREFIX.length) : kind

/**
 * Whether an event of `kind` passes the `?msg=` filter (ADR9.1): an exact match
 * on the full kind value, with `''` meaning "no filter". No prefix stripping —
 * `subagent-tool_use` matches only `subagent-tool_use`, never `tool_use`. This
 * supersedes the retired `Scope`/`matchesKindFilter` scope composition.
 */
export const matchesKind = (kind: string, filter: MessageKind | ''): boolean =>
  filter === '' || kind === filter
