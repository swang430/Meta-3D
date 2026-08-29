import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  buildBaseStationAdapterProfile,
  emptyBaseStationProfileDraft,
  readBaseStationProfileDraft,
  validateBaseStationProfileDraft,
  type BaseStationAdapterManifest,
} from './baseStationManifest.ts'

const thirdAdapter: BaseStationAdapterManifest = {
  schema_version: 2,
  adapter_id: 'adapter-c',
  model_name: 'Model C',
  vendor: 'Vendor C',
  rats: ['lte'],
  capabilities: ['config'],
  rat_capabilities: [
    { rat: 'lte', source_reference: 'Vendor C Manual §1' },
  ],
  operations: ['config'],
  config_fields: [],
  attach_stages: [],
  measurement: null,
  profile_requirement: 'required',
  profile_schema_version: 1,
  profile_fields: [
    {
      path: 'radio.port',
      label: 'Radio port',
      required: true,
      placeholder: 'PORT1',
      description: 'Selected radio port',
    },
    {
      path: 'radio.converter',
      label: 'Converter',
      required: true,
      placeholder: 'CONV1',
      description: 'Selected converter',
    },
  ],
  manual_sources: ['Instrument_API_Doc/vendor/manual.pdf'],
  diagnostic_supported: true,
  formal_gate: 'site_certification',
}

test('manifest paths drive empty values and nested profile readback', () => {
  assert.deepEqual(emptyBaseStationProfileDraft(thirdAdapter), {
    'radio.port': '',
    'radio.converter': '',
  })
  assert.deepEqual(
    readBaseStationProfileDraft(thirdAdapter, {
      schema_version: 1,
      adapter: 'adapter-c',
      radio: { port: 'PORT1', converter: 'CONV1' },
    }),
    { 'radio.port': 'PORT1', 'radio.converter': 'CONV1' },
  )
})

test('manifest required fields fail before a profile request is built', () => {
  const draft = { 'radio.port': 'PORT1', 'radio.converter': ' ' }
  assert.match(validateBaseStationProfileDraft(thirdAdapter, draft) ?? '', /Converter/)
  assert.throws(() => buildBaseStationAdapterProfile(thirdAdapter, draft), /Converter/)
})

test('manifest constructs the adapter envelope without model-specific branches', () => {
  assert.deepEqual(
    buildBaseStationAdapterProfile(thirdAdapter, {
      'radio.port': ' PORT1 ',
      'radio.converter': 'CONV1',
    }),
    {
      schema_version: 1,
      adapter: 'adapter-c',
      radio: { port: 'PORT1', converter: 'CONV1' },
    },
  )
})

test('not-applicable manifests produce no profile payload', () => {
  assert.equal(
    buildBaseStationAdapterProfile(
      {
        ...thirdAdapter,
        profile_requirement: 'not_applicable',
        profile_schema_version: null,
        profile_fields: [],
      },
      {},
    ),
    null,
  )
})

test('manifest v2 keeps the persisted profile envelope at schema v1', () => {
  const profile = buildBaseStationAdapterProfile(thirdAdapter, {
    'radio.port': 'PORT1',
    'radio.converter': 'CONV1',
  })

  assert.equal(profile?.schema_version, 1)
  assert.deepEqual(readBaseStationProfileDraft(thirdAdapter, profile), {
    'radio.port': 'PORT1',
    'radio.converter': 'CONV1',
  })
  assert.deepEqual(
    readBaseStationProfileDraft(thirdAdapter, {
      ...profile,
      schema_version: 2,
    }),
    { 'radio.port': '', 'radio.converter': '' },
  )
})

test('production equipment UI does not branch on a vendor model or fixed route fields', () => {
  const appSource = readFileSync(new URL('../App.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(appSource, /model\s*={2,3}\s*['"]CMW500['"]/)
  assert.doesNotMatch(appSource, /CMW500_ROUTE_FIELDS|cmw500_route/)
})
