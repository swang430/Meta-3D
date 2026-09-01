import assert from 'node:assert/strict'
import test from 'node:test'

import {
  profileDraftForConfiguration,
  updateMacProfileDraft,
} from './macTestProfile.ts'

const frozenNr = {
  profile: {
    schema_version: 1 as const,
    profile_version: 1 as const,
    kind: 'nr_throughput' as const,
    rat: 'nr5g' as const,
    test_intent: 'downlink_throughput' as const,
    mimo_layers: 4,
    statistical_window: { unit: 'subframes' as const, count: 6000 },
    metric_requirements: [{ key: 'dl_throughput_mbps', scope: 'pcell' as const }],
    source_reference: 'manual',
    rb_allocation: 'all' as const,
    scheduler_algorithm: 'full_throughput' as const,
    mcs: 19,
    enable_amc: false,
    tdd_pattern: 'DDDSU',
    tdd_period: '5MS',
    harq_max_trans: 4,
    harq_processes: 16,
    subcarrier_spacing_khz: 30,
    csi_rs_ports: 8,
  },
  profile_digest: 'a'.repeat(64),
}

test('saved canonical profile is projected without using adapter/model identity', () => {
  const draft = profileDraftForConfiguration({ mac_profile: frozenNr }, 'nr5g')
  assert.equal(draft.kind, 'nr_throughput')
  assert.equal(draft.mcs, 19)
  assert.equal(draft.statistical_window.count, 6000)
})

test('editing NR emits only supported legacy inputs and drops stale frozen digest', () => {
  const next = updateMacProfileDraft(
    { mac_profile: frozenNr, transmission_mode: 'TM3' },
    'nr5g',
    { mcs: 23, statistical_window_count: 7000 },
  )
  assert.equal(next.mac_profile, undefined)
  assert.equal(next.mcs, 23)
  assert.equal(next.stat_count, 7000)
  assert.equal(next.transmission_mode, undefined)
})

test('LTE draft never submits NR-only controls', () => {
  const next = updateMacProfileDraft(
    {
      mac_profile: frozenNr,
      mcs: 19,
      tdd_pattern: 'DDDSU',
      harq_processes: 16,
      csi_rs_ports: 8,
    },
    'lte',
    { statistical_window_count: 5000 },
  )
  assert.equal(next.mac_profile, undefined)
  assert.equal(next.stat_count, 5000)
  for (const key of ['mcs', 'tdd_pattern', 'harq_processes', 'csi_rs_ports']) {
    assert.equal(next[key], undefined)
  }
})
