/**
 * Helper Utilities for Test Management
 *
 * Common utility functions for status colors, labels, formatting, etc.
 *
 * @version 2.0.0
 */

import type { TestPlanStatus, TestStepStatus } from '../types'

/**
 * Get color for test plan status
 */
export function getTestPlanStatusColor(status: TestPlanStatus): string {
  const colorMap: Record<TestPlanStatus, string> = {
    draft: 'gray',
    ready: 'blue',
    queued: 'cyan',
    running: 'green',
    paused: 'yellow',
    completed: 'teal',
    failed: 'red',
    cancelled: 'orange',
  }
  return colorMap[status] || 'gray'
}

/**
 * Get label for test plan status
 */
export function getTestPlanStatusLabel(status: TestPlanStatus): string {
  const labelMap: Record<TestPlanStatus, string> = {
    draft: '草稿',
    ready: '就绪',
    queued: '已排队',
    running: '执行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return labelMap[status] || status
}

/**
 * Get color for test step status
 */
export function getTestStepStatusColor(status?: TestStepStatus): string {
  if (!status) return 'gray'

  const colorMap: Record<TestStepStatus, string> = {
    pending: 'gray',
    running: 'blue',
    completed: 'green',
    failed: 'red',
    skipped: 'yellow',
  }
  return colorMap[status] || 'gray'
}

/**
 * Get label for test step status
 */
export function getTestStepStatusLabel(status?: TestStepStatus): string {
  if (!status) return '待执行'

  const labelMap: Record<TestStepStatus, string> = {
    pending: '待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    skipped: '已跳过',
  }
  return labelMap[status] || status
}

/**
 * Format duration in minutes to human-readable string
 */
export function formatDuration(minutes: number): string {
  if (minutes < 1) {
    return '< 1 分钟'
  }
  if (minutes < 60) {
    return `${Math.round(minutes)} 分钟`
  }
  const hours = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)
  if (mins === 0) {
    return `${hours} 小时`
  }
  return `${hours} 小时 ${mins} 分钟`
}

/**
 * Format date to relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(date: string | Date): string {
  const now = new Date()
  const then = typeof date === 'string' ? new Date(date) : date
  const diffMs = now.getTime() - then.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins} 分钟前`

  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours} 小时前`

  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays} 天前`

  const diffWeeks = Math.floor(diffDays / 7)
  if (diffWeeks < 4) return `${diffWeeks} 周前`

  const diffMonths = Math.floor(diffDays / 30)
  return `${diffMonths} 个月前`
}

/**
 * Calculate progress percentage
 */
export function calculateProgress(completed: number, total: number): number {
  if (total === 0) return 0
  return Math.round((completed / total) * 100)
}

/**
 * Truncate text with ellipsis
 */
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength - 3) + '...'
}

/**
 * Get initials from name (for avatars)
 */
export function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .substring(0, 2)
}

/**
 * Format file size
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'

  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

/**
 * Validate parameter value based on type and validation rules
 */
export function validateParameterValue(
  value: any,
  type: string,
  validation?: {
    min?: number
    max?: number
    pattern?: string
    options?: string[]
    required?: boolean
  },
): { valid: boolean; error?: string } {
  // Check required
  if (validation?.required && (value === null || value === undefined || value === '')) {
    return { valid: false, error: '此字段为必填项' }
  }

  // Type-specific validation
  switch (type) {
    case 'number':
      if (typeof value !== 'number' || isNaN(value)) {
        return { valid: false, error: '请输入有效的数字' }
      }
      if (validation?.min !== undefined && value < validation.min) {
        return { valid: false, error: `值不能小于 ${validation.min}` }
      }
      if (validation?.max !== undefined && value > validation.max) {
        return { valid: false, error: `值不能大于 ${validation.max}` }
      }
      break

    case 'text':
      if (validation?.pattern) {
        const regex = new RegExp(validation.pattern)
        if (!regex.test(value)) {
          return { valid: false, error: '格式不正确' }
        }
      }
      break

    case 'select':
      if (validation?.options && !validation.options.includes(value)) {
        return { valid: false, error: '请选择有效的选项' }
      }
      break

    case 'json':
      try {
        JSON.parse(typeof value === 'string' ? value : JSON.stringify(value))
      } catch {
        return { valid: false, error: 'JSON 格式不正确' }
      }
      break
  }

  return { valid: true }
}

/**
 * Debounce function
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number,
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null

  return function executedFunction(...args: Parameters<T>) {
    const later = () => {
      timeout = null
      func(...args)
    }

    if (timeout) {
      clearTimeout(timeout)
    }
    timeout = setTimeout(later, wait)
  }
}

/**
 * Throttle function
 */
export function throttle<T extends (...args: any[]) => any>(
  func: T,
  limit: number,
): (...args: Parameters<T>) => void {
  let inThrottle: boolean = false

  return function executedFunction(...args: Parameters<T>) {
    if (!inThrottle) {
      func(...args)
      inThrottle = true
      setTimeout(() => {
        inThrottle = false
      }, limit)
    }
  }
}

/**
 * Deep clone object
 */
export function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj))
}

/**
 * Sort array by multiple fields
 */
export function multiSort<T>(
  array: T[],
  ...comparators: Array<(a: T, b: T) => number>
): T[] {
  return array.sort((a, b) => {
    for (const comparator of comparators) {
      const result = comparator(a, b)
      if (result !== 0) return result
    }
    return 0
  })
}

/**
 * Group array by key
 */
export function groupBy<T>(array: T[], key: keyof T): Record<string, T[]> {
  return array.reduce((result, item) => {
    const groupKey = String(item[key])
    if (!result[groupKey]) {
      result[groupKey] = []
    }
    result[groupKey].push(item)
    return result
  }, {} as Record<string, T[]>)
}

/**
 * Check if value is empty
 */
export function isEmpty(value: any): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim().length === 0
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}
