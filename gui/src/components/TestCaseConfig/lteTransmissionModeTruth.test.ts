import assert from 'node:assert/strict'
import test from 'node:test'

import { primaryCarrierIdentity } from './carrierTruth'

const lteCarrier = {
  radio_technology: 'lte',
  channel_kind: 'lte_dl_earfcn',
  frequency_hz: 1_842_500_000,
  bandwidth_mhz: 20,
  band: 'B3',
  duplex: 'fdd',
  lte_dl_earfcn: 1575,
  lte_transmission_mode: 'TM3',
  role: 'pcell',
}

test('LTE PCell truth retains its explicit transmission mode', () => {
  const parsed = primaryCarrierIdentity({ component_carriers: [lteCarrier] })

  assert.equal(parsed?.lte_transmission_mode, 'TM3')
})

test('LTE PCell truth rejects a missing transmission mode', () => {
  const { lte_transmission_mode: _missing, ...withoutMode } = lteCarrier

  assert.equal(
    primaryCarrierIdentity({ component_carriers: [withoutMode] }),
    null,
  )
})
