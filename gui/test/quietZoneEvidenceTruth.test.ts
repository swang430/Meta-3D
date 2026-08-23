import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
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

  assert.deepEqual(describePrecheckOutcome(true, legacyEvidence), {
    color: 'yellow',
    title: '预检未判定',
    message: '运行条件已检查，但缺少正式静区测量证据。诊断流程可继续。',
  })
})


test('probe-pattern spread is a diagnostic proxy, not measured ripple', () => {
  const view = describeQuietZoneEvidence(proxyEvidence)

  assert.equal(view.formalRipple, 'N/A')
  assert.equal(view.proxyRipple, '0.42 dB')
  assert.match(view.label, /诊断代理/)
  assert.match(view.label, /非静区实测/)
  assert.equal(view.verified, false)
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

  assert.match(source, /describePrecheckOutcome\(data\.overall_pass, data\.quiet_zone_evidence\)/)
  assert.match(source, /describeQuietZoneEvidence\(data\.quiet_zone_evidence\)/)
  assert.doesNotMatch(source, /data\.overall_pass \? "预检通过" : "预检失败"/)
  assert.doesNotMatch(source, /±\{data\.quiet_zone_ripple_db\} dB/)
})
