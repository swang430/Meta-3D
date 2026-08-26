import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildVendorSCDConfig,
  parseChannelFrequencyIdentity,
} from '../src/features/ChannelWorkbench/channelFrequencyIdentity.ts'

test('new LTE vendor asset writes only the LTE channel-number slot', () => {
  assert.deepEqual(buildVendorSCDConfig({
    radioTechnology: 'lte',
    band: 'B3',
    channelNumber: 1575,
    bandwidthMhz: 20,
    model: 'TDLA',
    scenario: 'Indoor',
    mimo: '2x2',
    polarization: 'DP',
    version: 1,
  }), {
    radio_technology: 'lte',
    channel_kind: 'lte_dl_earfcn',
    band: 'B3',
    lte_dl_earfcn: 1575,
    bandwidth_mhz: 20,
    model: 'TDLA',
    scenario: 'Indoor',
    mimo: '2x2',
    polarization: 'DP',
    version: 1,
  })
})

test('bare and incomplete legacy identities stay unknown', () => {
  assert.equal(parseChannelFrequencyIdentity({ band: 'N78', arfcn: 640000 }), null)
  assert.equal(parseChannelFrequencyIdentity('MF_N78_640000.smu'), null)
})

test('complete legacy vendor SCD is translated only as NR', () => {
  assert.deepEqual(parseChannelFrequencyIdentity({
    band: 'N78', arfcn: 640000, bandwidth_mhz: 100,
    model: 'CDLC', scenario: 'UMa', mimo: '4x4', polarization: 'DP', version: 1,
  }), {
    radioTechnology: 'nr5g',
    channelKind: 'nr_arfcn',
    band: 'N78',
    channelNumber: 640000,
  })
})

