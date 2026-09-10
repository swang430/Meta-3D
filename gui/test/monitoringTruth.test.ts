import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const hookSource = readFileSync(
  new URL('../src/hooks/useMonitoringWebSocket.ts', import.meta.url),
  'utf8',
)
const realtimeSource = readFileSync(
  new URL('../src/components/RealtimeMetricsCard.tsx', import.meta.url),
  'utf8',
)
const executionSource = readFileSync(
  new URL('../src/features/Monitoring/components/ExecutionMetricsCard.tsx', import.meta.url),
  'utf8',
)
const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')


test('monitoring contract represents missing and simulated observations explicitly', () => {
  assert.match(hookSource, /value: number \| null/)
  assert.match(hookSource, /status: 'observed' \| 'unavailable' \| 'simulated'/)
  assert.match(hookSource, /provenance: 'real' \| 'simulated' \| 'unknown'/)
  assert.match(hookSource, /reason: string \| null/)
  assert.doesNotMatch(hookSource, /'normal' \| 'warning' \| 'critical'/)
})


test('monitoring cards render unavailable observations as N/A', () => {
  assert.match(realtimeSource, /data\.value === null/)
  assert.match(realtimeSource, /N\/A/)
  assert.match(executionSource, /data\.value === null/)
  assert.match(executionSource, /N\/A/)
})


test('diagnostic monitoring has no hard-coded compliance verdict', () => {
  assert.doesNotMatch(executionSource, /expectedRanges/)
  assert.doesNotMatch(executionSource, /complianceRate/)
  assert.doesNotMatch(executionSource, /指标合规率/)
  assert.doesNotMatch(appSource, /throughput: \{ min: 140, max: 160 \}/)
})
