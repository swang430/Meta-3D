/**
 * Frontend logging shim — batches browser-side events and ships them to
 * `POST /api/v1/system-logs/frontend`, which writes them into the server's
 * `logs/frontend.log` channel.
 *
 * Why this exists: the backend has had a /system-logs/frontend endpoint and
 * a dedicated `frontend.log` file for a while, but no front-end caller was
 * ever wired up. React render crashes, unhandled promise rejections and bad
 * API responses therefore left no trace on the server. This module closes
 * that gap.
 *
 * Design notes:
 * - **Decoupled from axios** — uses `fetch` so an axios crash can still log.
 * - **Batched** — up to FLUSH_BATCH_SIZE entries OR FLUSH_INTERVAL_MS, whichever
 *   comes first; pageshow/pagehide/unload events trigger a final flush.
 * - **Best-effort** — one retry on network failure, then drop. Never throws
 *   into caller code (logging must not be the thing that breaks).
 * - **Self-bounded queue** — drops the oldest entry past MAX_QUEUE to survive
 *   error storms.
 */

interface FrontendLogEntry {
  ts: number // unix ms
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'
  action: string
  page?: string
  component?: string
  message?: string
  url?: string
  status_code?: number
  elapsed_ms?: number
  error?: string
  user_agent?: string
}

const ENDPOINT = '/api/v1/system-logs/frontend'
const FLUSH_INTERVAL_MS = 1500
const FLUSH_BATCH_SIZE = 50
const MAX_QUEUE = 500
const RETRY_DELAY_MS = 2000

let queue: FrontendLogEntry[] = []
let flushTimer: ReturnType<typeof setTimeout> | null = null
let sessionId: string = ''

function ensureSessionId(): string {
  if (sessionId) return sessionId
  // Stable per-tab id — survives reloads via sessionStorage
  try {
    const existing = sessionStorage.getItem('frontend-log-session-id')
    if (existing) {
      sessionId = existing
      return existing
    }
    const fresh = `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
    sessionStorage.setItem('frontend-log-session-id', fresh)
    sessionId = fresh
    return fresh
  } catch {
    sessionId = `s_${Date.now().toString(36)}`
    return sessionId
  }
}

function scheduleFlush(): void {
  if (flushTimer !== null) return
  flushTimer = setTimeout(() => {
    flushTimer = null
    void flush(false)
  }, FLUSH_INTERVAL_MS)
}

async function flush(useBeacon: boolean): Promise<void> {
  if (queue.length === 0) return
  const batch = queue.splice(0, FLUSH_BATCH_SIZE)
  const body = JSON.stringify({ entries: batch, session_id: ensureSessionId() })

  // sendBeacon is fire-and-forget and survives unload — preferred for
  // pagehide/beforeunload paths.
  if (useBeacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
    try {
      const blob = new Blob([body], { type: 'application/json' })
      navigator.sendBeacon(ENDPOINT, blob)
      return
    } catch {
      // fall through to fetch path
    }
  }

  try {
    const resp = await fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      // Don't credentialize/cache; logging is independent of auth state.
      cache: 'no-store',
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  } catch {
    // Retry once after a delay. If it still fails, drop the batch silently.
    setTimeout(() => {
      void fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        cache: 'no-store',
      }).catch(() => {
        /* drop */
      })
    }, RETRY_DELAY_MS)
  }

  if (queue.length > 0) scheduleFlush()
}

function enqueue(entry: FrontendLogEntry): void {
  if (queue.length >= MAX_QUEUE) {
    queue.shift() // drop oldest under pressure
  }
  queue.push(entry)
  if (queue.length >= FLUSH_BATCH_SIZE) {
    void flush(false)
  } else {
    scheduleFlush()
  }
}

function basePage(): string {
  if (typeof window === 'undefined') return '-'
  return window.location.pathname + window.location.hash
}

function baseUserAgent(): string {
  if (typeof navigator === 'undefined') return '-'
  return navigator.userAgent
}

/** Public API — log a single event. Never throws. */
export function logFrontendEvent(input: {
  level?: FrontendLogEntry['level']
  action: string
  message?: string
  component?: string
  url?: string
  status_code?: number
  elapsed_ms?: number
  error?: string
}): void {
  try {
    enqueue({
      ts: Date.now(),
      level: input.level ?? 'INFO',
      action: input.action,
      page: basePage(),
      component: input.component,
      message: input.message,
      url: input.url,
      status_code: input.status_code,
      elapsed_ms: input.elapsed_ms,
      error: input.error,
      user_agent: baseUserAgent(),
    })
  } catch {
    /* swallow — logging must not crash callers */
  }
}

/** Force-flush any pending entries. Used at unload. */
export function flushFrontendLogger(): void {
  if (flushTimer !== null) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
  void flush(true)
}

/**
 * Install global handlers exactly once. Idempotent. Wires:
 *   - window.onerror (uncaught synchronous JS)
 *   - window.onunhandledrejection (unhandled promise rejections)
 *   - pagehide/beforeunload final flush
 */
let installed = false
export function installGlobalErrorHandlers(): void {
  if (installed || typeof window === 'undefined') return
  installed = true

  window.addEventListener('error', (event) => {
    logFrontendEvent({
      level: 'ERROR',
      action: 'window_error',
      message: event.message,
      error: event.error?.stack || String(event.error || event.message),
      url: event.filename ? `${event.filename}:${event.lineno}:${event.colno}` : undefined,
    })
  })

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason
    const errStr =
      reason instanceof Error
        ? reason.stack || `${reason.name}: ${reason.message}`
        : (() => {
            try {
              return JSON.stringify(reason)
            } catch {
              return String(reason)
            }
          })()
    logFrontendEvent({
      level: 'ERROR',
      action: 'unhandled_rejection',
      message: reason instanceof Error ? reason.message : 'unhandled promise rejection',
      error: errStr,
    })
  })

  // Final flush attempts. pagehide is more reliable than beforeunload on mobile
  // and bfcache; both are wired for safety.
  window.addEventListener('pagehide', () => flushFrontendLogger())
  window.addEventListener('beforeunload', () => flushFrontendLogger())
}
