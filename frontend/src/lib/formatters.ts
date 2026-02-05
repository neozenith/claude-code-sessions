/**
 * Formatting utilities for displaying data in the UI
 *
 * These functions provide consistent formatting across all dashboard pages
 * for numbers, currencies, project names, and other display values.
 */

/**
 * Format large numbers in human-friendly format (e.g., 1.2M, 592k)
 *
 * @param num - The number to format
 * @returns Formatted string like "1.2M", "592k", or the original number as string
 *
 * @example
 * formatNumber(1_234_567) // "1.2M"
 * formatNumber(12_345)    // "12k"
 * formatNumber(999)       // "999"
 */
export function formatNumber(num: number): string {
  if (num >= 1_000_000) {
    return (num / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M'
  }
  if (num >= 1_000) {
    return (num / 1_000).toFixed(0) + 'k'
  }
  return num.toString()
}

/**
 * Format a project ID for display by removing the user path prefix
 * and converting dashes to slashes
 *
 * @param projectId - The raw project ID from the API (e.g., "-Users-joshpeak-code-myproject")
 * @returns Cleaned up project name (e.g., "code/myproject")
 *
 * @example
 * formatProjectName("-Users-joshpeak-code-myproject") // "code/myproject"
 * formatProjectName("my-simple-project")              // "my/simple/project"
 */
export function formatProjectName(projectId: string): string {
  return projectId.replace(/-Users-joshpeak-/, '').replace(/-/g, '/')
}

/**
 * Format a number as USD currency
 *
 * @param amount - The amount in USD
 * @param decimals - Number of decimal places (default: 2)
 * @returns Formatted string like "$123.45"
 *
 * @example
 * formatCurrency(123.456)    // "$123.46"
 * formatCurrency(123.456, 0) // "$123"
 */
export function formatCurrency(amount: number, decimals: number = 2): string {
  return `$${amount.toFixed(decimals)}`
}

/**
 * Format a number with thousand separators
 *
 * @param num - The number to format
 * @returns Formatted string with commas (e.g., "1,234,567")
 *
 * @example
 * formatWithCommas(1234567) // "1,234,567"
 */
export function formatWithCommas(num: number): string {
  return num.toLocaleString()
}

/**
 * Format tokens as millions with suffix (for display in token metrics)
 *
 * @param tokens - Number of tokens
 * @returns Formatted string like "1.23M"
 *
 * @example
 * formatTokensMillions(1_234_567) // "1.23M"
 */
export function formatTokensMillions(tokens: number): string {
  return `${(tokens / 1_000_000).toFixed(2)}M`
}

/**
 * Truncate a string to a maximum length with ellipsis
 *
 * @param str - The string to truncate
 * @param maxLength - Maximum length before truncation
 * @returns Truncated string with "..." if needed
 *
 * @example
 * truncate("Hello World", 8) // "Hello..."
 * truncate("Hi", 8)          // "Hi"
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str
  return str.substring(0, maxLength - 3) + '...'
}

/**
 * Format a model ID for display by removing common prefixes
 *
 * @param modelId - The raw model ID (e.g., "claude-sonnet-4-5-20250929")
 * @returns Shortened model name (e.g., "sonnet-4-5-20250929")
 *
 * @example
 * formatModelName("claude-sonnet-4-5-20250929") // "sonnet-4-5-20250929"
 */
export function formatModelName(modelId: string): string {
  return modelId.replace('claude-', '')
}

/**
 * Format a session ID for display (truncated with ellipsis)
 *
 * @param sessionId - The full session ID
 * @param maxLength - Maximum length (default: 16)
 * @returns Truncated session ID
 *
 * @example
 * formatSessionId("abc123def456ghi789jkl") // "abc123def456ghi7..."
 */
export function formatSessionId(sessionId: string, maxLength: number = 16): string {
  if (sessionId.length <= maxLength) return sessionId
  return sessionId.substring(0, maxLength) + '...'
}
