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

test('sparse legacy NR draft derives a TDD period that agrees with its own SCS', () => {
  // 后端 `uxm_nr_tdd_period_for_pattern()` 按「时隙数 × 单时隙时长」推导；界面此前
  // 对缺失周期一律填 5MS，于是非 30 kHz 的旧配置一打开就自相矛盾。
  // 期望值 = 默认模式 DDDDDDDSUU（10 个时隙）× 该 SCS 的单时隙时长。
  const expected: Record<number, string> = {
    15: '10MS',    // 10 × 1 ms
    30: '5MS',     // 10 × 0.5 ms
    60: '2.5MS',   // 10 × 0.25 ms
    120: '1.25MS', // 10 × 0.125 ms
  }
  for (const [scs, period] of Object.entries(expected)) {
    const configuration = {
      component_carriers: [{
        radio_technology: 'nr5g',
        subcarrier_spacing_khz: Number(scs),
      }],
      mimo_layers: 2,
      csi_rs_ports: 4,
    }
    const draft = profileDraftForConfiguration(configuration, 'nr5g')
    assert.equal(draft.kind, 'nr_throughput')
    assert.equal(
      draft.kind === 'nr_throughput' ? draft.tdd_period : null,
      period,
      `SCS ${scs} kHz 应推出 ${period}`,
    )
    // 可观察后果：推出来的草稿必须能直接通过保存前校验，
    // 而不是一打开编辑器就报「模式、SCS 与周期不一致」。
    assert.equal(
      macProfileTruth.validateMacProfileDraftForSave(configuration),
      null,
      `SCS ${scs} kHz 的稀疏旧配置不应报不一致`,
    )
  }

  // 显式写下的周期仍然原样保留，不被推导覆盖。
  const explicit = profileDraftForConfiguration({
    component_carriers: [{ radio_technology: 'nr5g', subcarrier_spacing_khz: 15 }],
    tdd_period: '5MS',
  }, 'nr5g')
  assert.equal(
    explicit.kind === 'nr_throughput' ? explicit.tdd_period : null,
    '5MS',
  )
})

// P2-56 ②（内审 F2）：LTE TDD 用例的 mac_profile 必须原样保留。
// 这段逻辑此前零测试保护 —— 整段删掉，GUI 测试全绿。
test('LTE TDD 用例保存时保留 mac_profile 且不与 stat_count 冲突', () => {
  const frozenTdd = {
    profile: {
      schema_version: 1 as const,
      profile_version: 1 as const,
      kind: 'lte_rmc' as const,
      rat: 'lte' as const,
      test_intent: 'downlink_throughput' as const,
      mimo_layers: 2 as const,
      statistical_window: { unit: 'subframes' as const, count: 5000 },
      metric_requirements: [
        { key: 'dl_throughput_mbps', scope: 'pcell' as const },
        { key: 'dl_bler_percent', scope: 'pcell' as const },
      ],
      scheduling_mode: 'rmc' as const,
      resource_allocation: 'full' as const,
      enable_amc: false as const,
      duplex: 'tdd' as const,
      transmission_mode: 'TM3' as const,
      uldl_configuration: 2 as const,
      special_subframe: 4 as const,
      rmc_version: null,
      source_reference:
        'Instrument_API_Doc/R&S CMW500/CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf' as const,
    },
    profile_digest: 'f'.repeat(64),
  }
  const tddConfig = { mac_profile: frozenTdd, mimo_layers: 2 }

  const saved = updateMacProfileDraft(tddConfig, 'lte', {})
  // ① 帧结构随冻结 profile 一起回传 —— 剥掉它后端会走 legacy 派生并拒绝
  assert.deepEqual(saved.mac_profile, frozenTdd)
  // ② 不带 stat_count：后端按值对账，改过的值必与冻结窗口不等而被拒
  assert.equal('stat_count' in saved, false)

  // ③ FDD 行为与改前逐字相同：mac_profile 被剥掉，stat_count 照常带出
  const fddConfig = {
    mac_profile: {
      ...frozenTdd,
      profile: { ...frozenTdd.profile, duplex: 'fdd' as const,
                 uldl_configuration: null, special_subframe: null },
    },
    mimo_layers: 2,
  }
  const fdd = updateMacProfileDraft(fddConfig, 'lte', {})
  assert.equal(fdd.mac_profile, undefined)
  assert.equal(fdd.stat_count, 5000)

  // ④ 形态空间：mac_profile 缺失 / null / 非对象 / profile 非对象 —— 一律按 FDD 处理
  for (const bad of [undefined, null, 'x', 42, [], { profile: 7 }]) {
    const out = updateMacProfileDraft(
      bad === undefined ? { mimo_layers: 2 } : { mac_profile: bad, mimo_layers: 2 },
      'lte',
      {},
    )
    assert.equal(out.mac_profile, undefined)
  }
})
