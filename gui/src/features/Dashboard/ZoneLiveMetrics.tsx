/**
 * P2-8 ③ 实时指标 — right main zone.
 *
 * Reuses the existing RealtimeMetricsCard, which itself consumes the
 * shared useMonitoringWebSocket hook (ws/monitoring). That component
 * already implements the acceptance criteria for this zone:
 *  - live metric cards (throughput / snr / eirp / temperature), while quiet
 *    zone remains explicit UNKNOWN until authoritative multi-point evidence
 *  - on disconnect: keeps last-known values rendered (metrics state is not
 *    cleared on close), shows a "WebSocket 断开" badge + a reconnect button
 *    — never白屏
 *
 * We deliberately do NOT re-implement WS logic here (acceptance criterion:
 * 复用现有 useMonitoringWebSocket hook, 不重复造 WS 逻辑).
 */
import { RealtimeMetricsCard } from '../../components/RealtimeMetricsCard'

export function ZoneLiveMetrics() {
  return <RealtimeMetricsCard />
}
