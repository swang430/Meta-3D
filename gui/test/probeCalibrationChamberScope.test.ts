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

test('probe calibration status consumers recognize the partial completeness state', () => {
  const typesSource = readFileSync(
    new URL('../src/types/probeCalibration.ts', import.meta.url),
    'utf8',
  )
  const badgeSource = readFileSync(
    new URL('../src/features/ProbeCalibration/components/CalibrationStatusBadge.tsx', import.meta.url),
    'utf8',
  )
  const gridSource = readFileSync(
    new URL('../src/features/ProbeCalibration/components/ProbeCalibrationGrid.tsx', import.meta.url),
    'utf8',
  )

  assert.match(typesSource, /ValidityStatus\s*=\s*[^\n]*'partial'/)
  assert.match(badgeSource, /partial:\s*\{[\s\S]*?label:\s*'Partial'/)
  assert.match(gridSource, /partial:\s*'orange'/)
})

test('unverified polarization and link values never receive threshold verdict colors', () => {
  const detailSource = readFileSync(
    new URL('../src/features/ProbeCalibration/components/ProbeCalibrationDetail.tsx', import.meta.url),
    'utf8',
  )

  assert.match(
    detailSource,
    /function thresholdVerdictColor\([\s\S]*?useMock !== false[\s\S]*?return 'gray'/,
  )
  assert.equal(
    (detailSource.match(/thresholdVerdictColor\(\s*data\.use_mock/g) ?? []).length,
    4,
  )
})

test('dashboard and grid consume the authoritative per-probe partial status', () => {
  const dashboardSource = readFileSync(
    new URL('../src/features/ProbeCalibration/components/ProbeCalibrationDashboard.tsx', import.meta.url),
    'utf8',
  )
  const gridSource = readFileSync(
    new URL('../src/features/ProbeCalibration/components/ProbeCalibrationGrid.tsx', import.meta.url),
    'utf8',
  )

  assert.match(dashboardSource, /validProbes === totalProbes[\s\S]*'valid'/)
  assert.match(dashboardSource, /partialProbes > 0[\s\S]*'partial'/)
  assert.match(gridSource, /validityReport\.probe_statuses/)
  assert.match(
    gridSource,
    /validityReport\.partial_probes[\s\S]*Partial/,
  )
  assert.match(
    gridSource,
    /validityReport\.total_probes[\s\S]*validityReport\.partial_probes[\s\S]*Unknown/,
  )
  assert.doesNotMatch(gridSource, /We need to infer from expired\/expiring lists/)
})
