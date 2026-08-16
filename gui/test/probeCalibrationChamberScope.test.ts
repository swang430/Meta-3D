import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { probeCalibrationKeys } from '../src/hooks/useProbeCalibration.ts'

test('probe calibration cache keys isolate identical probe numbers by chamber', () => {
  const chamberA = 'aaaaaaaa-0000-0000-0000-000000000001'
  const chamberB = 'bbbbbbbb-0000-0000-0000-000000000002'

  assert.notDeepEqual(
    probeCalibrationKeys.amplitude(chamberA, 1),
    probeCalibrationKeys.amplitude(chamberB, 1),
  )
  assert.notDeepEqual(
    probeCalibrationKeys.probeValidity(chamberA, 1),
    probeCalibrationKeys.probeValidity(chamberB, 1),
  )
  assert.notDeepEqual(
    probeCalibrationKeys.probeData(chamberA, 1),
    probeCalibrationKeys.probeData(chamberB, 1),
  )
})

test('probe calibration reads send chamber_id and queries fail closed without it', () => {
  const serviceSource = readFileSync(
    new URL('../src/api/probeCalibrationService.ts', import.meta.url),
    'utf8',
  )
  const hooksSource = readFileSync(
    new URL('../src/hooks/useProbeCalibration.ts', import.meta.url),
    'utf8',
  )

  for (const functionName of [
    'getAmplitudeCalibration',
    'getAmplitudeCalibrationHistory',
    'getPhaseCalibration',
    'getPhaseCalibrationHistory',
    'getPolarizationCalibration',
    'getPolarizationCalibrationHistory',
    'getPatternCalibration',
    'getValidityReport',
    'getExpiringCalibrations',
    'getExpiredCalibrations',
    'getProbeValidity',
    'getProbeCalibrationData',
  ]) {
    const start = serviceSource.indexOf(`export async function ${functionName}`)
    const next = serviceSource.indexOf('\nexport async function ', start + 1)
    const body = serviceSource.slice(start, next === -1 ? serviceSource.length : next)
    assert.ok(start >= 0, `${functionName} must remain an active service entry`)
    assert.match(body, /chamber_id\s*:\s*chamberId/, `${functionName} must send chamber_id`)
  }

  const chamberAwareQueries = hooksSource.match(/enabled:\s*enabled\s*&&\s*Boolean\(chamberId\)/g) ?? []
  assert.equal(chamberAwareQueries.length, 12)
})

test('probe calibration page passes one chamber truth to dashboard, grid, and detail', () => {
  const pageSource = readFileSync(
    new URL('../src/features/ProbeCalibration/ProbeCalibrationPage.tsx', import.meta.url),
    'utf8',
  )

  assert.match(pageSource, /interface ProbeCalibrationPageProps[\s\S]*chamberId:\s*string/)
  assert.match(pageSource, /interface ProbeCalibrationPageProps[\s\S]*probeCount:\s*number/)
  assert.match(pageSource, /<ProbeCalibrationDashboard[\s\S]*chamberId=\{chamberId\}/)
  assert.match(pageSource, /<ProbeCalibrationGrid[\s\S]*chamberId=\{chamberId\}/)
  assert.match(pageSource, /<ProbeCalibrationDetail[\s\S]*chamberId=\{chamberId\}/)
  assert.match(pageSource, /<ProbeCalibrationGrid[\s\S]*probeCount=\{probeCount\}/)
  assert.doesNotMatch(pageSource, /probeCount=\{32\}/)
})

test('probe calibration detail presents simulated and unknown provenance as unverified', () => {
  const detailSource = readFileSync(
    new URL('../src/features/ProbeCalibration/components/ProbeCalibrationDetail.tsx', import.meta.url),
    'utf8',
  )

  assert.equal((detailSource.match(/useMock=\{data\.use_mock\}/g) ?? []).length, 4)
  assert.match(detailSource, /useMock=\{latestPattern\.use_mock\}/)
  assert.match(detailSource, /useMock=\{data\.use_mock\}/)
  assert.match(detailSource, /SIMULATED/)
  assert.match(detailSource, /SOURCE UNKNOWN/)
  assert.match(detailSource, /useMock === false[\s\S]*CalibrationStatusBadge/)
})

test('probe invalidation client requires and sends the chamber scope', () => {
  const serviceSource = readFileSync(
    new URL('../src/api/probeCalibrationService.ts', import.meta.url),
    'utf8',
  )
  const hooksSource = readFileSync(
    new URL('../src/hooks/useProbeCalibration.ts', import.meta.url),
    'utf8',
  )
  const serviceStart = serviceSource.indexOf('export async function invalidateCalibration')
  const serviceEnd = serviceSource.indexOf('\nexport async function ', serviceStart + 1)
  const serviceBody = serviceSource.slice(serviceStart, serviceEnd)
  assert.match(serviceBody, /chamberId:\s*string/)
  assert.match(serviceBody, /params:\s*\{\s*chamber_id:\s*chamberId\s*\}/)

  const hookStart = hooksSource.indexOf('export function useInvalidateCalibration')
  const hookEnd = hooksSource.indexOf('\nexport function ', hookStart + 1)
  const hookBody = hooksSource.slice(hookStart, hookEnd)
  assert.match(hookBody, /chamberId:\s*string/)
  assert.match(
    hookBody,
    /invalidateCalibration\(calibrationType, calibrationId, chamberId, request\)/,
  )
})
