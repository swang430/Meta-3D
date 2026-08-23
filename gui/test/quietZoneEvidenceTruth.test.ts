import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  describePrecheckMessages,
  describePrecheckOutcome,
  describeQuietZoneEvidence,
} from '../src/components/Commissioning/quietZoneEvidence.ts'


const proxyEvidence = {
  schema_version: 1,
  status: 'diagnostic_proxy',
  source: 'probe_pattern_peak_spread',
  formal_verified: false,
  measured_ripple_db: null,
  proxy_ripple_db: 0.42,
  calibration_id: null,
}


test('unknown precheck is yellow and never presented as pass or fail', () => {
  assert.deepEqual(describePrecheckOutcome(null, proxyEvidence), {
    color: 'yellow',
    title: '预检未判定',
    message: '运行条件已检查，但缺少正式静区测量证据。诊断流程可继续。',
  })
})


test('legacy overall true cannot revive a green precheck without canonical formal evidence', () => {
  const legacyEvidence = {
    quiet_zone_verified: true,
    quiet_zone_ripple_db: 0.7,
  }

  assert.deepEqual(describePrecheckOutcome(true, legacyEvidence, undefined), {
    color: 'yellow',
    title: '预检未判定',
    message: '运行条件已检查，但缺少正式静区测量证据。诊断流程可继续。',
  })
})


test('legacy overall false cannot revive a formal quiet-zone failure', () => {
  const legacyEvidence = {
    quiet_zone_verified: false,
    quiet_zone_ripple_db: 1.2,
  }

  assert.deepEqual(describePrecheckOutcome(false, legacyEvidence, undefined), {
    color: 'yellow',
    title: '预检未判定',
    message: '运行条件已检查，但缺少正式静区测量证据。诊断流程可继续。',
  })
})


test('current operational failure remains red even when quiet-zone evidence is unavailable', () => {
  assert.equal(
    describePrecheckOutcome(false, proxyEvidence, false).color,
    'red',
  )
})


test('legacy free-text quiet-zone verdicts are replaced by a canonical diagnostic notice', () => {
  const messages = describePrecheckMessages(
    ['Quiet zone ripple: 2.00 dB (FAIL) [probe_pattern_peak_spread]'],
    { quiet_zone_verified: false, quiet_zone_ripple_db: 2.0 },
  )

  assert.deepEqual(messages, [
    '静区结论未判定：无权威多点场扫描证据；历史提示未作为正式证据发布。',
  ])
})


test('probe-pattern spread is a diagnostic proxy, not measured ripple', () => {
  const view = describeQuietZoneEvidence(proxyEvidence)

  assert.equal(view.formalRipple, 'N/A')
  assert.equal(view.proxyRipple, '0.42 dB')
  assert.match(view.label, /诊断代理/)
  assert.match(view.label, /非静区实测/)
  assert.equal(view.verified, false)
})


test('zero probe-pattern spread is still labelled as a diagnostic proxy', () => {
  const view = describeQuietZoneEvidence({ ...proxyEvidence, proxy_ripple_db: 0 })

  assert.equal(view.proxyRipple, '0.00 dB')
  assert.match(view.label, /诊断代理/)
})


test('legacy or malformed evidence cannot produce a green view', () => {
  const legacy = describeQuietZoneEvidence({
    quiet_zone_verified: true,
    quiet_zone_ripple_db: 0.7,
  })
  const malformed = describeQuietZoneEvidence({ ...proxyEvidence, extra: true })

  assert.equal(legacy.verified, false)
  assert.equal(legacy.formalRipple, 'N/A')
  assert.equal(malformed.verified, false)
  assert.equal(malformed.formalRipple, 'N/A')
})


test('commissioning phase consumes the shared tri-state presenter', () => {
  const source = readFileSync(
    new URL('../src/components/Commissioning/Phases.tsx', import.meta.url),
    'utf8',
  )

  assert.match(
    source,
    /describePrecheckOutcome\(\s*data\.overall_pass,\s*data\.quiet_zone_evidence,\s*data\.operational_ready,?\s*\)/,
  )
  assert.match(source, /describeQuietZoneEvidence\(data\.quiet_zone_evidence\)/)
  assert.match(source, /describePrecheckMessages\(data\.messages, data\.quiet_zone_evidence\)/)
  assert.match(
    source,
    /data\.overall_pass === false && data\.operational_ready === false && \(\(\) =>/,
  )
  assert.match(source, /quietZoneView\.verified && data\.quiet_zone_pass === false/)
  assert.doesNotMatch(source, /data\.overall_pass \? "预检通过" : "预检失败"/)
  assert.doesNotMatch(source, /±\{data\.quiet_zone_ripple_db\} dB/)
})


test('live monitoring never presents a derived quiet-zone value or status', () => {
  const realtimeSource = readFileSync(
    new URL('../src/components/RealtimeMetricsCard.tsx', import.meta.url),
    'utf8',
  )
  const executionSource = readFileSync(
    new URL('../src/features/Monitoring/components/ExecutionMetricsCard.tsx', import.meta.url),
    'utf8',
  )
  const hookSource = readFileSync(
    new URL('../src/hooks/useMonitoringWebSocket.ts', import.meta.url),
    'utf8',
  )

  assert.doesNotMatch(realtimeSource, /metrics\.quiet_zone_uniformity/)
  assert.doesNotMatch(executionSource, /metrics\.quiet_zone_uniformity/)
  assert.doesNotMatch(hookSource, /quiet_zone_uniformity:/)
  assert.match(realtimeSource, /静区均匀度/)
  assert.match(realtimeSource, /UNKNOWN/)
  assert.match(realtimeSource, />N\/A</)
  assert.match(executionSource, /静区均匀度/)
  assert.match(
    executionSource,
    /<UnavailableMetricCard label=\{METRIC_LABELS\.quiet_zone_uniformity\} \/>/,
  )
})
