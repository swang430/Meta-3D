import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'

const helperUrl = new URL(
  '../src/components/TestCaseConfig/carrierTruth.ts',
  import.meta.url,
)

test('carrier truth helper exists', () => {
  assert.equal(
    existsSync(helperUrl),
    true,
    'P1-55 requires one shared GUI PCell truth helper',
  )
})

test('display prefers PCell and edits preserve SCells', async () => {
  if (!existsSync(helperUrl)) return
  const { primaryCarrierValue, updatePrimaryCarrierValue } = await import(
    helperUrl.href
  )
  const config = {
    frequency_hz: 3_600_000_000,
    bandwidth_mhz: 100,
    component_carriers: [
      {
        frequency_hz: 3_500_000_000,
        bandwidth_mhz: 40,
        subcarrier_spacing_khz: 30,
        role: 'pcell',
      },
      {
        frequency_hz: 3_700_000_000,
        bandwidth_mhz: 80,
        subcarrier_spacing_khz: 60,
        role: 'scell',
      },
    ],
  }

  assert.equal(primaryCarrierValue(config, 'frequency_hz'), 3_500_000_000)
  const updated = updatePrimaryCarrierValue(config, 'bandwidth_mhz', 50)
  assert.equal(updated.bandwidth_mhz, 50)
  assert.equal(updated.component_carriers?.[0].bandwidth_mhz, 50)
  assert.equal(updated.component_carriers?.[1].bandwidth_mhz, 80)
})

test('legacy config without carriers continues to edit the top-level mirror', async () => {
  if (!existsSync(helperUrl)) return
  const { primaryCarrierValue, updatePrimaryCarrierValue } = await import(
    helperUrl.href
  )
  const config = { frequency_hz: 3_500_000_000 }

  assert.equal(primaryCarrierValue(config, 'frequency_hz'), 3_500_000_000)
  assert.deepEqual(
    updatePrimaryCarrierValue(config, 'frequency_hz', 3_600_000_000),
    { frequency_hz: 3_600_000_000 },
  )
})

test('an invalid PCell value never falls back to a stale top-level mirror', async () => {
  if (!existsSync(helperUrl)) return
  const { primaryCarrierValue } = await import(helperUrl.href)

  assert.equal(
    primaryCarrierValue(
      {
        frequency_hz: 3_600_000_000,
        component_carriers: [{ frequency_hz: Number.NaN }],
      },
      'frequency_hz',
    ),
    undefined,
  )
})
