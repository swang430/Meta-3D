import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  projectBaseStationCapabilities,
  type BaseStationAdapterManifest,
} from './baseStationManifest.ts'

const thirdAdapter: BaseStationAdapterManifest = {
  schema_version: 2,
  adapter_id: 'adapter-c',
  model_name: 'Model C',
  vendor: 'Vendor C',
  rats: ['nr5g'],
  capabilities: ['identity', 'config', 'cell_attach', 'measurement_window'],
  rat_capabilities: [
    { rat: 'nr5g', source_reference: 'Vendor C Manual §1' },
  ],
  operations: ['identity', 'config', 'cell_attach', 'measurement_window'],
  config_fields: [],
  attach_stages: [
    {
      stage: 'cell_ready',
      evidence: 'authoritative',
      reason: 'Authoritative cell state',
      source_reference: 'Vendor C Manual §2',
    },
    {
      stage: 'ue_registered',
      evidence: 'diagnostic_only',
      reason: 'Registration is diagnostic only',
      source_reference: null,
    },
    {
      stage: 'rrc_connected',
      evidence: 'unavailable',
      reason: 'No independent RRC evidence',
      source_reference: null,
    },
    {
      stage: 'data_bearer_established',
      evidence: 'not_applicable',
      reason: 'Not applicable to this adapter',
      source_reference: null,
    },
  ],
  measurement: {
    cardinality: 'requested',
    scopes: ['pcell', 'all_cells'],
    lifecycle: 'clear_read_only',
    metrics: [
      {
        key: 'dl_throughput_mbps',
        direction: 'downlink',
        unit: 'mbps',
        scopes: ['pcell'],
        evidence: 'diagnostic_only',
        source_reference: null,
      },
      {
        key: 'ul_bler_percent',
        direction: 'uplink',
        unit: 'percent',
        scopes: ['all_cells'],
        evidence: 'unavailable',
        source_reference: null,
      },
    ],
    source_reference: null,
  },
  profile_requirement: 'not_applicable',
  profile_schema_version: null,
  profile_fields: [],
  manual_sources: ['Instrument_API_Doc/vendor-c/manual.pdf'],
  diagnostic_supported: true,
  formal_gate: 'site_certification',
}

test('a third adapter projects RAT, attach, window, and metric capabilities generically', () => {
  const projection = projectBaseStationCapabilities(thirdAdapter)

  assert.deepEqual(projection.rats.map((item) => item.key), ['nr5g'])
  assert.deepEqual(
    projection.attach.map((item) => [item.key, item.tone]),
    [
      ['cell_ready', 'green'],
      ['ue_registered', 'yellow'],
      ['rrc_connected', 'gray'],
      ['data_bearer_established', 'gray'],
    ],
  )
  assert.equal(projection.measurementWindow.key, 'clear_read_only')
  assert.equal(projection.measurementWindow.tone, 'yellow')
  assert.deepEqual(
    projection.metrics.map((item) => [item.key, item.tone]),
    [
      ['dl_throughput_mbps', 'yellow'],
      ['ul_bler_percent', 'gray'],
    ],
  )
})

test('diagnostic-only and unavailable declarations never project as formal green', () => {
  const projection = projectBaseStationCapabilities(thirdAdapter)
  const limited = [
    ...projection.attach,
    projection.measurementWindow,
    ...projection.metrics,
  ].filter((item) => item.source !== 'authoritative')

  assert.ok(limited.length > 0)
  assert.ok(limited.every((item) => item.tone !== 'green'))
})

test('production UI consumes the generic projection without adapter-name branches', () => {
  const appSource = readFileSync(new URL('../App.tsx', import.meta.url), 'utf8')
  assert.match(appSource, /projectBaseStationCapabilities/)
  assert.doesNotMatch(appSource, /adapter_id\s*={2,3}\s*['"](?:cmw500|uxm)['"]/i)
})
