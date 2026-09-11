import assert from 'node:assert/strict'
import test from 'node:test'

import type { components } from './api.generated.ts'
import type {
  BaseStationMacDimensionCapability,
  BaseStationMacDimensionValueCapability,
  BaseStationMacProfileCapability,
} from './baseStationManifest.ts'

const valueCapability: BaseStationMacDimensionValueCapability = {
  value: null,
  support: 'not_applicable',
  satisfying_options: [],
  required_options: [],
  minimum_firmware: null,
  requires: [],
  reason: 'FDD does not use a TDD-only dimension',
  source_reference: 'R&S CMW500 LTE User Manual §2.6',
}

const dimensionCapability: BaseStationMacDimensionCapability = {
  dimension: 'uldl_configuration',
  values: [
    valueCapability,
    { ...valueCapability, value: 'TM3' },
    { ...valueCapability, value: 2 },
    { ...valueCapability, value: false },
  ],
}

const handwrittenProfile: BaseStationMacProfileCapability = {
  kind: 'lte_rmc',
  profile_version: 1,
  rat: 'lte',
  application_evidence: 'authoritative_readback',
  source_reference: 'R&S CMW500 LTE User Manual §2.6',
  dimensions: [dimensionCapability],
}

const generatedProfile: components['schemas']['BaseStationMacProfileCapability'] = {
  ...handwrittenProfile,
}

test('generated and handwritten MAC capability contracts preserve dimensions', () => {
  assert.deepEqual(generatedProfile.dimensions, [dimensionCapability])
  assert.deepEqual(
    generatedProfile.dimensions[0].values.map((item) => item.value),
    [null, 'TM3', 2, false],
  )
})
