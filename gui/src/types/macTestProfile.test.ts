import assert from 'node:assert/strict'
import test from 'node:test'
import * as macProfileTruth from './macTestProfile.ts'

import {
  profileDraftForConfiguration,
  updateMacProfileDraft,
  UXM_NR_HARQ_MAX_TRANS_VALUES,
  UXM_NR_HARQ_PROCESSES_VALUES,
  UXM_NR_TDD_PERIOD_VALUES,
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

test('legacy NR draft preserves layer-derived CSI-RS port defaults', () => {
  assert.equal(
    profileDraftForConfiguration({ mimo_layers: 1 }, 'nr5g').csi_rs_ports,
    2,
  )
  assert.equal(
    profileDraftForConfiguration({ mimo_layers: 4 }, 'nr5g').csi_rs_ports,
    8,
  )
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
  assert.equal(next.mimo_layers, 2)
  for (const key of ['mcs', 'tdd_pattern', 'harq_processes', 'csi_rs_ports']) {
    assert.equal(next[key], undefined)
  }
})

test('NR editor choices mirror the server-audited UXM enum domain', () => {
  assert.deepEqual(UXM_NR_TDD_PERIOD_VALUES, [
    '0.5MS', '0.625MS', '1MS', '1.25MS', '2MS',
    '2.5MS', '3MS', '4MS', '5MS', '10MS',
  ])
  assert.deepEqual(UXM_NR_HARQ_MAX_TRANS_VALUES, [
    1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 28,
  ])
  assert.deepEqual(UXM_NR_HARQ_PROCESSES_VALUES, [
    1, 2, 4, 6, 8, 10, 12, 13, 14, 16, 32,
  ])
  assert.deepEqual(macProfileTruth.UXM_NR_MIMO_LAYERS_VALUES, [1, 2, 4])
  assert.deepEqual(macProfileTruth.UXM_NR_CSI_RS_PORTS_VALUES, [
    1, 2, 4, 8, 12, 16, 24, 32,
  ])
})

test('NR draft keeps AMC fixed off and validates the frozen TDD duration', () => {
  const withAmc = updateMacProfileDraft(
    { component_carriers: [{ radio_technology: 'nr5g', subcarrier_spacing_khz: 30 }] },
    'nr5g',
    { enable_amc: true },
  )
  assert.equal(withAmc.enable_amc, false)

  assert.equal(typeof macProfileTruth.validateMacProfileDraftForSave, 'function')
  assert.match(
    macProfileTruth.validateMacProfileDraftForSave({
      component_carriers: [{ radio_technology: 'nr5g', subcarrier_spacing_khz: 30 }],
      mimo_layers: 2,
      tdd_pattern: 'DDDSU',
      tdd_period: '5MS',
      csi_rs_ports: 4,
    }) ?? '',
    /TDD/,
  )
  assert.equal(
    macProfileTruth.validateMacProfileDraftForSave({
      component_carriers: [{ radio_technology: 'nr5g', subcarrier_spacing_khz: 30 }],
      mimo_layers: 4,
      tdd_pattern: 'DDDDDDDSUU',
      tdd_period: '5MS',
      csi_rs_ports: 8,
    }),
    null,
  )
})
