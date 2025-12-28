/**
 * WebSocket Hook for Real-time Monitoring Data
 *
 * Provides real-time monitoring metrics from the backend via WebSocket.
 * Automatically handles connection, reconnection, and cleanup.
 *
 * Phase 2.6 Optimizations:
 * - Throttled updates to prevent excessive re-renders
 * - Memoized return values for performance
 * - Configurable update frequency
 *
 * Usage:
 * ```tsx
 * const { metrics, isConnected, error } = useMonitoringWebSocket();
 *
 * // Access real-time metrics
 * console.log(metrics.throughput.value, metrics.throughput.unit);
 * console.log(metrics.snr.status); // "normal" | "warning" | "critical"
 * ```
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'

export interface MonitoringMetricData {
  value: number
  unit: string
  timestamp: string
  status: 'normal' | 'warning' | 'critical'
}

export interface MonitoringMetrics {
  throughput: MonitoringMetricData
  snr: MonitoringMetricData
  quiet_zone_uniformity: MonitoringMetricData
  eirp: MonitoringMetricData
  temperature: MonitoringMetricData
}

export interface MonitoringMessage {
  type: 'connected' | 'metrics' | 'pong' | 'error'
  data?: MonitoringMetrics
  message?: string
  timestamp: string
}

export interface UseMonitoringWebSocketReturn {
  /** Current monitoring metrics */
  metrics: MonitoringMetrics | null
  /** WebSocket connection status */
  isConnected: boolean
  /** Connection error if any */
  error: Error | null
  /** Manually reconnect */
  reconnect: () => void
  /** Send ping to server */
  sendPing: () => void
}

interface UseMonitoringWebSocketOptions {
  /** WebSocket URL (defaults to dynamic based on current host) */
  url?: string
  /** Auto-reconnect on disconnect (default: true) */
  autoReconnect?: boolean
  /** Reconnect delay in ms (default: 3000) */
  reconnectDelay?: number
  /** Maximum reconnection attempts (default: Infinity) */
  maxReconnectAttempts?: number
  /** Enable debug logging (default: false) */
  debug?: boolean
  /** Throttle update interval in ms (default: 100, 0 = no throttle) */
  throttleMs?: number
}

const DEFAULT_OPTIONS: Required<Omit<UseMonitoringWebSocketOptions, 'url'>> = {
  autoReconnect: true,
  reconnectDelay: 3000,
  maxReconnectAttempts: Infinity,
  debug: false,
  throttleMs: 100, // Max 10 updates/sec
}

export function useMonitoringWebSocket(
  options: UseMonitoringWebSocketOptions = {}
): UseMonitoringWebSocketReturn {
  // Calculate default URL dynamically based on current window location
  // This ensures it works through the Vite proxy (e.g., ws://localhost:5173/api/...)
  // instead of bypassing it and hitting 8001 directly.
  const defaultUrl = useMemo(() => {
    if (typeof window !== 'undefined') {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      return `${protocol}//${window.location.host}/api/v1/ws/monitoring`
    }
    return 'ws://localhost:8001/api/v1/ws/monitoring' // Fallback for non-browser envs
  }, [])

  const opts = { ...DEFAULT_OPTIONS, url: defaultUrl, ...options }

  const [metrics, setMetrics] = useState<MonitoringMetrics | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const shouldConnectRef = useRef(true)
  const lastUpdateTimeRef = useRef<number>(0)
  const pendingMetricsRef = useRef<MonitoringMetrics | null>(null)
  const throttleTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const log = useCallback(
    (...args: any[]) => {
      if (opts.debug) {
        console.log('[useMonitoringWebSocket]', ...args)
      }
    },
    [opts.debug]
  )

  // Throttled metrics update to prevent excessive re-renders
  const updateMetrics = useCallback(
    (newMetrics: MonitoringMetrics) => {
      const now = Date.now()
      const timeSinceLastUpdate = now - lastUpdateTimeRef.current

      if (opts.throttleMs === 0) {
        // No throttling
        setMetrics(newMetrics)
        lastUpdateTimeRef.current = now
        return
      }

      if (timeSinceLastUpdate >= opts.throttleMs) {
        // Enough time has passed, update immediately
        setMetrics(newMetrics)
        lastUpdateTimeRef.current = now

        // Clear any pending throttled update
        if (throttleTimeoutRef.current) {
          clearTimeout(throttleTimeoutRef.current)
          throttleTimeoutRef.current = null
        }
      } else {
        // Too soon, schedule throttled update
        pendingMetricsRef.current = newMetrics

        if (!throttleTimeoutRef.current) {
          const delay = opts.throttleMs - timeSinceLastUpdate
          throttleTimeoutRef.current = setTimeout(() => {
            if (pendingMetricsRef.current) {
              setMetrics(pendingMetricsRef.current)
              lastUpdateTimeRef.current = Date.now()
              pendingMetricsRef.current = null
            }
            throttleTimeoutRef.current = null
          }, delay)
        }
      }
    },
    [opts.throttleMs]
  )

  const connect = useCallback(() => {
    // Clear any existing connection
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    if (!shouldConnectRef.current) {
      log('Connection cancelled (shouldConnect = false)')
      return
    }

    log('Connecting to', opts.url)

    try {
      const ws = new WebSocket(opts.url)
      wsRef.current = ws

      ws.onopen = () => {
        log('Connected successfully')
        setIsConnected(true)
        setError(null)
        reconnectAttemptsRef.current = 0
      }

      ws.onmessage = (event) => {
        try {
          const message: MonitoringMessage = JSON.parse(event.data)
          log('Received message:', message.type)

          switch (message.type) {
            case 'connected':
              log('Connection confirmed:', message.message)
              break

            case 'metrics':
              if (message.data) {
                updateMetrics(message.data)
              }
              break

            case 'pong':
              log('Pong received at', message.timestamp)
              break

            case 'error':
              console.error('Server error:', message.message)
              setError(new Error(message.message || 'Unknown server error'))
              break

            default:
              log('Unknown message type:', message)
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err)
        }
      }

      ws.onerror = (event) => {
        console.error('WebSocket error:', event)
        setError(new Error('WebSocket connection error'))
      }

      ws.onclose = (event) => {
        log('Connection closed:', event.code, event.reason)
        setIsConnected(false)
        wsRef.current = null

        // Auto-reconnect logic
        if (
          opts.autoReconnect &&
          shouldConnectRef.current &&
          reconnectAttemptsRef.current < opts.maxReconnectAttempts
        ) {
          reconnectAttemptsRef.current += 1
          log(
            `Reconnecting in ${opts.reconnectDelay}ms (attempt ${reconnectAttemptsRef.current}/${opts.maxReconnectAttempts})`
          )

          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, opts.reconnectDelay)
        } else if (reconnectAttemptsRef.current >= opts.maxReconnectAttempts) {
          setError(new Error('Max reconnection attempts reached'))
        }
      }
    } catch (err) {
      console.error('Failed to create WebSocket:', err)
      setError(err as Error)
    }
  }, [opts.url, opts.autoReconnect, opts.reconnectDelay, opts.maxReconnectAttempts, log, updateMetrics])

  const reconnect = useCallback(() => {
    log('Manual reconnect requested')
    reconnectAttemptsRef.current = 0
    shouldConnectRef.current = true

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    connect()
  }, [connect, log])

  const sendPing = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const message = JSON.stringify({ type: 'ping' })
      wsRef.current.send(message)
      log('Ping sent')
    } else {
      log('Cannot send ping: WebSocket not connected')
    }
  }, [log])

  // Initial connection
  useEffect(() => {
    shouldConnectRef.current = true
    connect()

    // Cleanup on unmount
    return () => {
      shouldConnectRef.current = false

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }

      if (throttleTimeoutRef.current) {
        clearTimeout(throttleTimeoutRef.current)
        throttleTimeoutRef.current = null
      }

      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }

      log('Cleanup completed')
    }
  }, [connect, log])

  // Memoize return value to prevent unnecessary re-renders
  return useMemo(
    () => ({
      metrics,
      isConnected,
      error,
      reconnect,
      sendPing,
    }),
    [metrics, isConnected, error, reconnect, sendPing]
  )
}