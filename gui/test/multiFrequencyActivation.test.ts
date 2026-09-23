import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  assertMultiFrequencyPathLossJobResponse,
  buildMultiFrequencyPathLossRequest,
} from '../src/components/SystemCalibration/multiFrequencyCalibration.ts'


const validInput = {
  chamberId: '09fbdf36-ce6c-46d8-a8e8-b636f87f5b21',
  probeIds: '1, 2',
  polarization: 'V' as const,
  frequencyStartMhz: 3400,
  frequencyStopMhz: 3600,
  frequencyStepMhz: 100,
  sghModel: 'SGH-01',
  sghGainDbi: 10,
  calibratedBy: 'p2-32a',
  mode: 'real' as const,
}


test('multi-frequency request builder preserves explicit real and mock provenance', () => {
  assert.deepEqual(buildMultiFrequencyPathLossRequest(validInput), {
    chamber_id: validInput.chamberId,
    probe_ids: [1, 2],
    polarization: 'V',
    freq_start_mhz: 3400,
    freq_stop_mhz: 3600,
    freq_step_mhz: 100,
    sgh_model: 'SGH-01',
    sgh_gain_dbi: 10,
    calibrated_by: 'p2-32a',
    use_mock: false,
  })
  assert.equal(
    buildMultiFrequencyPathLossRequest({ ...validInput, mode: 'mock' }).use_mock,
    true,
  )
})


test('multi-frequency request builder rejects ambiguous or invalid execution inputs', () => {
  const invalidInputs = [
    { ...validInput, chamberId: '' },
    { ...validInput, mode: null },
    { ...validInput, probeIds: '' },
    { ...validInput, probeIds: '1, 1' },
    { ...validInput, probeIds: '1, 2.5' },
    { ...validInput, probeIds: '1, -2' },
    { ...validInput, frequencyStopMhz: 3400 },
    { ...validInput, frequencyStepMhz: 0 },
  ]

  for (const input of invalidInputs) {
    assert.throws(
      () => buildMultiFrequencyPathLossRequest(input),
      Error,
      JSON.stringify(input),
    )
  }
})


test('multi-frequency response provenance must exactly match the explicit request', () => {
  const completedReal = {
    calibration_job_id: '09fbdf36-ce6c-46d8-a8e8-b636f87f5b21',
    status: 'completed' as const,
    use_mock: false,
    warnings: [],
  }

  assert.equal(
    assertMultiFrequencyPathLossJobResponse(completedReal, false),
    completedReal,
  )
  assert.throws(
    () => assertMultiFrequencyPathLossJobResponse(
      { ...completedReal, use_mock: null },
      false,
    ),
    /执行来源缺失/,
  )
  assert.throws(
    () => assertMultiFrequencyPathLossJobResponse(
      { ...completedReal, use_mock: true },
      false,
    ),
    /执行来源与请求不一致/,
  )
  assert.throws(
    () => assertMultiFrequencyPathLossJobResponse(
      { ...completedReal, status: 'failed' },
      false,
    ),
    /任务未完成/,
  )
})


test('multi-frequency GUI uses the authoritative endpoint with explicit provenance', () => {
  const serviceSource = readFileSync(
    new URL('../src/api/calibrationService.ts', import.meta.url),
    'utf8',
  )
  const wizardSource = readFileSync(
    new URL('../src/components/SystemCalibration/CalibrationWizard.tsx', import.meta.url),
    'utf8',
  )
  const builderSource = readFileSync(
    new URL('../src/components/SystemCalibration/multiFrequencyCalibration.ts', import.meta.url),
    'utf8',
  )

  const call = serviceSource.match(
    /export async function startMultiFrequencyPathLoss[\s\S]*?\n}\n/,
  )?.[0] ?? ''
  assert.match(call, /calibration\/path-loss\/multi-frequency\/start/)
  assert.doesNotMatch(call, /ALLOW_FALLBACK|USE_MOCK|Math\.random/)
  assert.doesNotMatch(serviceSource, /generateMockMultiFrequencyResult/)
  assert.doesNotMatch(serviceSource, /'\/calibration\/multi-frequency'/)

  assert.match(wizardSource, /multiFrequencyMode/)
  assert.match(wizardSource, /buildMultiFrequencyPathLossRequest/)
  assert.match(wizardSource, /mode: multiFrequencyMode/)
  assert.match(builderSource, /use_mock: input\.mode === 'mock'/)
  assert.match(builderSource, /当前 LabProfile 未绑定暗室/)
  assert.match(builderSource, /请选择真实仪表或模拟诊断模式/)
  assert.match(wizardSource, /真实扫频完成/)
  assert.match(wizardSource, /模拟诊断完成/)
  assert.doesNotMatch(
    wizardSource.match(
      /calibrationType === 'multi_frequency'[\s\S]*?startMultiFrequencyPathLoss\(request\)/,
    )?.[0] ?? '',
    /overall_pass|validation_pass|reference_trp_dbm|reference_tis_dbm/,
  )
})
