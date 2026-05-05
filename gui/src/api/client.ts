import axios from 'axios'
import { logFrontendEvent } from '../observability/frontendLogger'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 300000,
})

// Tag each outgoing request with a start timestamp so the response interceptor
// can compute elapsed_ms without mutating axios's public types.
client.interceptors.request.use((config) => {
  ;(config as { _startedAt?: number })._startedAt = Date.now()
  return config
})

// Ship 4xx/5xx + network failures to the server-side frontend log channel.
// Skip the logging endpoint itself to avoid feedback loops if it returns errors.
client.interceptors.response.use(
  (response) => response,
  (error) => {
    try {
      const config = error?.config ?? {}
      const url: string = config.url || ''
      // Don't log calls to the log endpoint — would loop on outage.
      if (!url.includes('/system-logs/frontend')) {
        const startedAt = (config as { _startedAt?: number })._startedAt
        const elapsed = startedAt ? Date.now() - startedAt : undefined
        const status = error?.response?.status
        const detail =
          error?.response?.data?.detail ||
          error?.response?.data?.message ||
          error?.message ||
          'request failed'
        logFrontendEvent({
          level: status && status < 500 ? 'WARN' : 'ERROR',
          action: 'api_error',
          message: `${(config.method || 'GET').toUpperCase()} ${url} — ${detail}`,
          url,
          status_code: status,
          elapsed_ms: elapsed,
          error: typeof detail === 'string' ? detail : JSON.stringify(detail),
        })
      }
    } catch {
      /* swallow — interceptor must not break the rejection path */
    }
    return Promise.reject(error)
  },
)

export default client
