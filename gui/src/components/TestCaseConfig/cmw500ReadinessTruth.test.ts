import assert from 'node:assert/strict'
import test from 'node:test'

import {
  compareFrozenCmwApproval,
  describeCmw500Readiness,
} from './cmw500ReadinessTruth.ts'

const readiness = {
  status: 'ready' as const,
  adapter_registered: true,
  connection_id: 'connection-1',
  model: 'CMW',
  identity_verified: true,
  firmware_version: '3.5.40',
  options: ['CMW-KS500', 'CMW-KS520'],
  formal_enabled: true,
  formal_updated_at: '2026-08-26T12:00:00',
  fdd_ready: true,
  tdd_ready: false,
  detail: 'FDD ready; TDD missing KS550',
}

test('duplex readiness stays specific and inherit is diagnostic only', () => {
  assert.equal(describeCmw500Readiness(readiness, 'fdd', 'dispatch').status, 'ready')
  assert.equal(describeCmw500Readiness(readiness, 'tdd', 'dispatch').status, 'warning')
  const inherited = describeCmw500Readiness(readiness, 'fdd', 'inherit')
  assert.equal(inherited.status, 'diagnostic')
  assert.match(inherited.message, /仅诊断/)
})

test('missing live snapshot is warning and never a blocking hardware claim', () => {
  const view = describeCmw500Readiness(undefined, 'fdd', 'dispatch')
  assert.equal(view.status, 'warning')
  assert.match(view.message, /UNKNOWN/)
  assert.equal(view.blocksDevelopment, false)
})

test('execution approval is immutable and drift only affects later executions', () => {
  const message = compareFrozenCmwApproval(
    readiness,
    {
      base_station_adapter_profile_freeze: {
        resolution: { adapter: 'cmw500' },
        cmw500_lte_2x2_formal_capability: {
          instrument_connection_id: 'connection-1',
          enabled: false,
          updated_at: '2026-08-26T11:00:00',
        },
      },
    },
  )

  assert.match(message ?? '', /仅影响后续执行/)
})
