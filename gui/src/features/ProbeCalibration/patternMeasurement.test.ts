import assert from 'node:assert/strict'
import test from 'node:test'

import {
  assertPatternCalibrationJobResponse,
  buildPatternMeasurementRequest,
  type PatternMeasurementInput,
} from './patternMeasurement.ts'

const validInput: PatternMeasurementInput = {
  labProfileId: 'lab-1',
  chamberId: 'chamber-1',
  operatingMode: 'mimo_ota',
  probeCount: 32,
  probeIds: '0, 1',
  polarizations: ['V', 'H'],
  frequencyMhz: 3500,
  azimuthStepDeg: 30,
  elevationStepDeg: 30,
  measurementDistanceM: 3,
  ceTxPowerDbm: -20,
  sghGainDbi: 10,
  calibratedBy: 'operator',
  mode: 'real',
}

test('pattern request carries explicit lab context but no client route truth', () => {
  const request = buildPatternMeasurementRequest(validInput)
  assert.deepEqual(request, {
    lab_profile_id: 'lab-1',
    chamber_id: 'chamber-1',
    operating_mode: 'mimo_ota',
    probe_ids: [0, 1],
    polarizations: ['V', 'H'],
    frequency_mhz: 3500,
    azimuth_step_deg: 30,
    elevation_step_deg: 30,
    measurement_distance_m: 3,
    ce_tx_power_dbm: -20,
    sgh_gain_dbi: 10,
    calibrated_by: 'operator',
    use_mock: false,
  })
  assert.equal('ce_port' in request, false)
  assert.equal('chain_id' in request, false)
  assert.equal('topology_id' in request, false)
})

test('pattern request rejects missing context, mode, and invalid probe lists', () => {
  assert.throws(
    () => buildPatternMeasurementRequest({ ...validInput, labProfileId: '' }),
    /LabProfile/,
  )
  assert.throws(
    () => buildPatternMeasurementRequest({ ...validInput, chamberId: '' }),
    /暗室/,
  )
  assert.throws(
    () => buildPatternMeasurementRequest({ ...validInput, mode: null }),
    /模式/,
  )
  for (const probeIds of ['', '0,', '0,0', '-1', '1.5', '32']) {
    assert.throws(
      () => buildPatternMeasurementRequest({ ...validInput, probeIds }),
      /探头/,
    )
  }
})

test('pattern request validates physical inputs before any request', () => {
  const invalidCases: Array<Partial<PatternMeasurementInput>> = [
    { frequencyMhz: 0 },
    { frequencyMhz: 99.9 },
    { frequencyMhz: 100_000.1 },
    { azimuthStepDeg: 0 },
    { azimuthStepDeg: 31 },
    { elevationStepDeg: 31 },
    { measurementDistanceM: 0.4 },
    { polarizations: [] },
    { calibratedBy: ' ' },
  ]
  for (const override of invalidCases) {
    assert.throws(() => buildPatternMeasurementRequest({ ...validInput, ...override }))
  }
})

test('pattern response must disclose matching source and completed status', () => {
  const completed = {
    calibration_job_id: 'job-1',
    status: 'completed' as const,
    use_mock: false,
    warnings: [],
  }
  assert.equal(assertPatternCalibrationJobResponse(completed, false), completed)
  assert.throws(
    () => assertPatternCalibrationJobResponse({ ...completed, use_mock: undefined }, false),
    /来源缺失/,
  )
  assert.throws(
    () => assertPatternCalibrationJobResponse({ ...completed, use_mock: true }, false),
    /来源与请求不一致/,
  )
  assert.throws(
    () => assertPatternCalibrationJobResponse({ ...completed, status: 'failed' }, false),
    /未完成/,
  )
})
