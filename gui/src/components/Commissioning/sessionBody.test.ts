import assert from 'node:assert/strict'
import test from 'node:test'

import { buildCreateSessionBody } from './sessionBody'

test('LTE commissioning persists the explicitly selected transmission mode', () => {
  const body = buildCreateSessionBody({
    radioTechnology: 'lte',
    frequencyHz: 1_842_500_000,
    bandwidthMhz: 20,
    band: 'B3',
    duplex: 'fdd',
    lteDlEarfcn: 1575,
    lteTransmissionMode: 'TM3',
  })

  assert.equal(body.lte_transmission_mode, 'TM3')
})

test('NR commissioning never sends an LTE transmission mode', () => {
  const body = buildCreateSessionBody({
    radioTechnology: 'nr5g',
    lteTransmissionMode: 'TM3',
  })

  assert.equal('lte_transmission_mode' in body, false)
})
