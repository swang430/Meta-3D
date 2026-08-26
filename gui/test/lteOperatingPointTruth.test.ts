import assert from 'node:assert/strict'
import test from 'node:test'

import {
  patchPrimaryCarrierFields,
  primaryCarrierIdentity,
  updatePrimaryCarrierIdentity,
} from '../src/components/TestCaseConfig/carrierTruth.ts'
import { buildCreateSessionBody } from '../src/components/Commissioning/sessionBody.ts'

test('LTE PCell replaces NR-only fields without inheriting the NR peak', () => {
  const next = updatePrimaryCarrierIdentity(
    {
      theoretical_peak_throughput_mbps: 450,
      component_carriers: [{
        radio_technology: 'nr5g',
        frequency_hz: 3_549_990_000,
        bandwidth_mhz: 40,
        subcarrier_spacing_khz: 30,
        nr_arfcn: 636666,
        role: 'pcell',
      }],
    },
    {
      radio_technology: 'lte',
      channel_kind: 'lte_dl_earfcn',
      frequency_hz: 1_842_500_000,
      bandwidth_mhz: 20,
      band: 'B3',
      duplex: 'fdd',
      lte_dl_earfcn: 1575,
      role: 'pcell',
    },
  )

  assert.equal(next.theoretical_peak_throughput_mbps, undefined)
  assert.deepEqual(primaryCarrierIdentity(next), {
    radio_technology: 'lte',
    channel_kind: 'lte_dl_earfcn',
    frequency_hz: 1_842_500_000,
    bandwidth_mhz: 20,
    band: 'B3',
    duplex: 'fdd',
    lte_dl_earfcn: 1575,
    role: 'pcell',
  })
})

test('legacy complete PCell remains an exact NR read translation', () => {
  assert.deepEqual(primaryCarrierIdentity({
    component_carriers: [{
      frequency_hz: 3_549_990_000,
      bandwidth_mhz: 40,
      subcarrier_spacing_khz: 30,
      nr_arfcn: 636666,
      role: 'pcell',
    }],
  }), {
    radio_technology: 'nr5g',
    channel_kind: 'nr_arfcn',
    frequency_hz: 3_549_990_000,
    bandwidth_mhz: 40,
    subcarrier_spacing_khz: 30,
    nr_arfcn: 636666,
    role: 'pcell',
  })
})

test('commissioning LTE request sends one explicit LTE identity and no NR fields', () => {
  assert.deepEqual(buildCreateSessionBody({
    radioTechnology: 'lte',
    frequencyHz: 1_842_500_000,
    bandwidthMhz: 20,
    band: 'B3',
    duplex: 'fdd',
    lteDlEarfcn: 1575,
    uxmDlPowerDbmPerBw: -15,
  }), {
    radio_technology: 'lte',
    engine_mode: 'mimo_first_asc',
    frequency_hz: 1_842_500_000,
    bandwidth_mhz: 20,
    band: 'B3',
    duplex: 'fdd',
    lte_dl_earfcn: 1575,
  })
})

test('editing the NR PCell preserves every existing SCell', () => {
  const scell = {
    radio_technology: 'nr5g',
    channel_kind: 'nr_arfcn',
    frequency_hz: 3_600_000_000,
    bandwidth_mhz: 40,
    subcarrier_spacing_khz: 30,
    nr_arfcn: 638000,
    role: 'scell',
  }
  const next = patchPrimaryCarrierFields({
    component_carriers: [{
      radio_technology: 'nr5g',
      channel_kind: 'nr_arfcn',
      frequency_hz: 3_549_990_000,
      bandwidth_mhz: 40,
      subcarrier_spacing_khz: 30,
      nr_arfcn: 636666,
      role: 'pcell',
    }, scell],
  }, { band: 'N78' })

  assert.equal(next.component_carriers?.length, 2)
  assert.deepEqual(next.component_carriers?.[1], scell)
  assert.equal(next.component_carriers?.[0]?.band, 'N78')
})
