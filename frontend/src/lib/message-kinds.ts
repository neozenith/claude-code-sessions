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
