import assert from 'node:assert/strict'
import test from 'node:test'

import { formatPortLabel, resolvePortHandles } from './baseStationPorts.ts'

test('logical BaseStation port direction comes from role, never RF6 spelling', () => {
  assert.deepEqual(
    resolvePortHandles({
      ports: ['DL1', 'DL2', 'UL1'],
      port_roles: { DL1: 'dl', DL2: 'dl', UL1: 'ul' },
      physical_port_display: { DL1: 'RF3OUT', DL2: 'RF4OUT', UL1: 'RF6IN' },
    }),
    [
      { id: 'DL1', role: 'dl', handleType: 'source', physicalPort: 'RF3OUT' },
      { id: 'DL2', role: 'dl', handleType: 'source', physicalPort: 'RF4OUT' },
      { id: 'UL1', role: 'ul', handleType: 'target', physicalPort: 'RF6IN' },
    ],
  )
})

test('legacy physical UXM ports still use explicit roles instead of port name inference', () => {
  const ports = resolvePortHandles({
    ports: ['RF5', 'RF6'],
    port_roles: { RF5: 'dl', RF6: 'ul' },
  })
  assert.equal(ports[0].handleType, 'source')
  assert.equal(ports[1].handleType, 'target')
})

test('physical connector is display-only metadata on the logical port label', () => {
  assert.equal(
    formatPortLabel({ id: 'DL1', role: 'dl', handleType: 'source', physicalPort: 'RF3OUT' }),
    'DL1 → RF3OUT',
  )
  assert.equal(
    formatPortLabel({ id: 'DL1', role: 'dl', handleType: 'source' }),
    'DL1',
  )
})
