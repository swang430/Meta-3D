import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (relative: string) => readFileSync(new URL(relative, import.meta.url), 'utf8')

test('generated and handwritten types expose the shared binding truth', () => {
  const generated = read('./api.generated.ts')
  const handwritten = read('./api.ts')
  const manifest = read('./baseStationManifest.ts')
  for (const token of [
    'BaseStationAdapterManifest',
    'BaseStationBindingPreviewResponse',
    'InstrumentBindingSyncResponse',
    'base_station_manifest',
    'base_station_binding',
    'binding_digest',
  ]) {
    assert.match(generated, new RegExp(token))
    assert.match(handwritten, new RegExp(token))
  }
  assert.match(
    handwritten,
    /base_station_manifest: BaseStationAdapterManifest \| null/,
  )
  assert.doesNotMatch(handwritten, /base_station_manifest\?:/)
  assert.match(handwritten, /export type \{ BaseStationAdapterManifest \}/)
  assert.match(generated, /schema_version: 2;/)
  for (const token of [
    'profile_schema_version',
    'rat_capabilities',
    'config_fields',
    'attach_stages',
    'BaseStationMeasurementCapability',
    'BaseStationMetricCapability',
  ]) {
    assert.match(generated, new RegExp(token))
    assert.match(manifest, new RegExp(token))
  }
})

test('lab profile service types preview and sync with the common response', () => {
  const source = read('../api/labProfileService.ts')
  assert.match(source, /fetchBaseStationBindingPreview/)
  assert.match(source, /Promise<BaseStationBindingPreviewResponse>/)
  assert.match(source, /Promise<InstrumentBindingSyncResponse>/)
})

test('readiness and sync feedback consume the resolved common binding truth', () => {
  const readiness = read('../features/Dashboard/ZoneReadiness.tsx')
  const app = read('../App.tsx')
  assert.match(
    readiness,
    /projectBaseStationBindingTruth\(report\.base_station_binding\)/,
  )
  assert.match(readiness, /projectReadinessVerdict\(buildCells\(readiness\)/)
  assert.match(app, /formatBaseStationSyncTruth\(syncResult\.resolved\)/)
})
