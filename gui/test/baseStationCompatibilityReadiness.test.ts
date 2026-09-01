import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (relative: string): string =>
  readFileSync(new URL(`../${relative}`, import.meta.url), 'utf8')

test('readiness and binding clients send optional saved TestCase context', () => {
  const readiness = read('src/api/service.ts')
  const binding = read('src/api/labProfileService.ts')

  assert.match(readiness, /fetchReadiness\s*=\s*async\s*\(labProfileId\?:\s*string,\s*testCaseId\?:\s*string\)/)
  assert.match(readiness, /test_case_id\s*:\s*testCaseId/)
  assert.match(binding, /syncCurrentInstrumentBinding[\s\S]*testCaseId\?:\s*string/)
  assert.match(binding, /fetchBaseStationBindingPreview[\s\S]*testCaseId\?:\s*string/)
  assert.match(binding, /test_case_id\s*:\s*testCaseId/)
})

test('saved TestCase editor supplies context while unsaved drafts fail closed locally', () => {
  const modal = read('src/components/TestPlanManagement/TestCaseEditModal.tsx')
  const form = read('src/components/TestCaseConfig/MIMOOTAConfigForm.tsx')

  assert.match(modal, /testCaseId=\{testCaseId\}/)
  assert.match(modal, /labProfileId=/)
  assert.match(modal, /compatibilityContextSaved=/)
  assert.match(form, /compatibilityContextSaved/)
  assert.match(form, /testCaseId/)
  assert.match(form, /base_station_testcase_compatibility/)
  assert.match(form, /未保存/)
})

test('dashboard renders the separate TestCase compatibility truth', () => {
  const source = read('src/features/Dashboard/ZoneReadiness.tsx')

  assert.match(source, /projectBaseStationCompatibilityTruth/)
  assert.match(source, /report\.base_station_testcase_compatibility/)
  assert.match(source, /key:\s*'base-station-compatibility'/)
})

test('generated and handwritten API mirrors expose compatibility readiness', () => {
  const generated = read('src/types/api.generated.ts')
  const handwritten = read('src/types/api.ts')

  assert.match(generated, /BaseStationCompatibilityPreviewResponse:/)
  assert.match(generated, /testcase_compatibility:\s*components\["schemas"\]\["BaseStationCompatibilityPreviewResponse"\]/)
  assert.match(generated, /base_station_testcase_compatibility:\s*components\["schemas"\]\["BaseStationCompatibilityPreviewResponse"\]/)
  assert.match(handwritten, /export type BaseStationCompatibilityPreviewResponse/)
  assert.match(handwritten, /base_station_testcase_compatibility:\s*BaseStationCompatibilityPreviewResponse/)
})
