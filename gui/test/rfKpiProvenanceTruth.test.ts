import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  describeRfKpiEvidence,
  formatRfKpiValue,
} from '../src/components/Commissioning/rfKpiEvidence.ts'


test('unverified RF KPI stays N/A even when a historical number is present', () => {
  assert.equal(formatRfKpiValue(-78.25, false, 2), 'N/A')
  assert.equal(formatRfKpiValue(18.5, undefined, 1), 'N/A')
  assert.equal(describeRfKpiEvidence(false).verified, false)
})


test('verified finite RF KPI preserves real zero and requested precision', () => {
  assert.equal(formatRfKpiValue(0, true, 1), '0.0')
  assert.equal(formatRfKpiValue(-78.256, true, 2), '-78.26')
  assert.equal(formatRfKpiValue(Number.NaN, true, 1), 'N/A')
  assert.equal(describeRfKpiEvidence(true).verified, true)
})


test('commissioning table consumes the explicit server verdict', () => {
  const source = readFileSync(
    new URL('../src/components/Commissioning/Phases.tsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /describeRfKpiEvidence\(data\.formal_rf_kpi_verified\)/)
  assert.match(source, /formatRfKpiValue\(az\.rsrp_dbm, rfKpiView\.verified/)
  assert.match(source, /formatRfKpiValue\(az\.sinr_db, rfKpiView\.verified/)
  assert.match(
    source,
    /formatRfKpiValue\(az\.rank_indicator, rfKpiView\.verified, 2\)/,
  )
  assert.doesNotMatch(source, /<Table\.Td>\{az\.(?:rsrp_dbm|sinr_db|rank_indicator)\}<\/Table\.Td>/)
})
