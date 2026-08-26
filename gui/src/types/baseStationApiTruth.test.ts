import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const generated = readFileSync(
  new URL('./api.generated.ts', import.meta.url),
  'utf8',
)

test('generated commissioning API names the generic base-station mode', () => {
  assert.match(
    generated,
    /Vendor-neutral base-station configuration mode; inherit is diagnostic-only\.[\s\S]*base_station_config_mode\?: "dispatch" \| "inherit" \| null;/,
  )
  assert.doesNotMatch(generated, /uxm_config_mode\?:/)
  assert.doesNotMatch(generated, /base_station_dl_power_dbm_per_bw\?:/)
})

test('generated channel contracts preserve RAT and channel-kind unions', () => {
  assert.match(generated, /radio_technology: "nr5g" \| "lte";/)
  assert.match(generated, /channel_kind: "nr_arfcn" \| "lte_dl_earfcn";/)
})
