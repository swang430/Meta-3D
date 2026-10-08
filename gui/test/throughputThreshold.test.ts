import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { buildCreateSessionBody } from '../src/components/Commissioning/sessionBody.ts'

test('commissioning preserves explicit absolute threshold without adding a default', () => {
  assert.equal(buildCreateSessionBody({ minThroughputMbps: 96.5 }).min_throughput_mbps, 96.5)
  assert.equal(buildCreateSessionBody().min_throughput_mbps, undefined)
  assert.equal(buildCreateSessionBody({ minThroughputMbps: 0 }).min_throughput_mbps, 0)
})

test('case editor has no active theory or ratio controls', () => {
  const source = readFileSync(new URL('../src/components/TestCaseConfig/MIMOOTAConfigForm.tsx', import.meta.url), 'utf8')
  assert.ok(!source.includes('label="吞吐量比例下限"'))
  assert.ok(!source.includes('label="理论峰值吞吐量"'))
  assert.ok(source.includes('未设置时吞吐判决 UNKNOWN'))
  assert.ok(source.includes("updatePass('min_throughput_mbps', typeof v === 'number' ? v : null)"))
})
