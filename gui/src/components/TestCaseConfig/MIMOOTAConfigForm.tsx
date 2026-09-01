/**
 * Typed editor for MIMO_OTA TestCase / TestStep configuration.
 *
 * Reads the raw 27-field flat JSON written by `mimo_ota.factory` /
 * `legacy_to_mimo_ota_config` and renders it as a structured Mantine form
 * with Chinese labels, sensible groupings, unit-aware inputs, and a sane
 * default split between "shown by default" (channel / MIMO / sweep / power /
 * pass criteria) and "advanced" (base-station MAC, reference antenna,
 * channel-generation engine, raw step_overrides) behind an Accordion.
 *
 * Controlled component: `value` is the canonical raw shape; every change
 * fires `onChange(nextValue)` with a freshly merged copy. Keeps no internal
 * state so callers (StepEditor) can drive save/reset.
 */
import {
  Accordion,
  Alert,
  Code,
  Fieldset,
  Group,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  TagsInput,
  Text,
  TextInput,
} from '@mantine/core'
import { useQuery } from '@tanstack/react-query'

import { fetchChannelModels, fetchReadiness } from '../../api/service'
import { fetchDUTProfiles } from '../../api/dutProfileService'
import { fetchSIMProfiles } from '../../api/simProfileService'
import { fetchCustomCDLProfiles } from '../../api/customCdlProfileService'
import { fetchChannelAssets } from '../../api/channelAssetService'
import {
  LTE_TRANSMISSION_MODES,
  type LteTransmissionMode,
  patchPrimaryCarrierFields,
  primaryCarrierValue,
  updatePrimaryCarrierValue,
} from './carrierTruth'
import {
  resolveBaseStationConfigMode,
  updateBaseStationConfigMode,
} from './baseStationConfigTruth'
import { useOperationalLab } from '../../features/OperationalLab'
import { describeCmw500Readiness } from './cmw500ReadinessTruth'
import { projectBaseStationCompatibilityTruth } from '../../features/Dashboard/baseStationBindingTruth'

// --- Local typings: mirror the backend MIMOOTAConfiguration shape ---

interface PassCriteria {
  min_throughput_ratio?: number
  min_throughput_mbps?: number
  max_rsrp_variance_db?: number
  rsrp_range_dbm?: [number, number] | number[]
  min_sinr_db?: number
  min_avg_rank_indicator?: number
  max_quiet_zone_ripple_db?: number
}

export interface MIMOOTAConfiguration {
  // P2-16 S4-5: 统一信道资产引用 (信道工作台 ChannelAsset)。设了 → 后端 channel_asset_resolver
  // 按 source_type 派生 engine_mode + 覆盖下方传统信道字段 (cdl_model_name/cdl_profile_id/
  // scd_id/emulation_file)。留空=走传统字段 (方案 A 向后兼容)。
  channel_asset_id?: string
  cdl_model_name?: string
  // P2-15: 引用一个自定义 CDL 档案 (簇级参数, 在「自定义 CDL」页建)。选了它 → 后端
  // input_mode=custom 用 profile 簇合成 (优先于标称 cdl_model_name)。留空=用标称 CDL。
  cdl_profile_id?: string
  // GCM (keysight_gcm) 模式下 F64 加载的 .smu 完整路径 (= available_channel_models
  // entry 的 filename = SCD associated_file_path)。ASC 模式无关 (.asc 按 frequency 生成)。
  emulation_file?: string
  // P2-12 slice 4: 引用 SCD (优先于裸 emulation_file; measure 查 SCD 解析 .smu + 频率 cross-check)。
  scd_id?: string
  frequency_hz?: number
  bandwidth_mhz?: number
  /** Phase 2g 载波聚合。表单只编辑 PCell；SCell 仍由 configuration JSON 管理。 */
  component_carriers?: Array<{
    radio_technology?: 'nr5g' | 'lte'
    channel_kind?: 'nr_arfcn' | 'lte_dl_earfcn'
    frequency_hz?: number
    bandwidth_mhz?: number
    subcarrier_spacing_khz?: number
    band?: string | null
    duplex?: 'fdd' | 'tdd' | null
    nr_arfcn?: number | null
    lte_dl_earfcn?: number | null
    lte_transmission_mode?: LteTransmissionMode | null
    role?: string
  }>
  mimo_layers?: number
  modulation?: string
  subcarrier_spacing_khz?: number
  azimuths_deg?: number[]
  measurement_duration_s?: number
  settling_time_s?: number
  num_samples_per_azimuth?: number
  sample_interval_ms?: number
  target_tx_power_dbm?: number
  target_rsrp_dbm?: number
  target_snr_db?: number
  reference_antenna_model?: string
  reference_antenna_gain_dbi?: number
  mcs?: number
  enable_amc?: boolean
  tdd_pattern?: string
  tdd_period?: string
  harq_max_trans?: number
  harq_processes?: number
  stat_count?: number
  // DUTProfile 阶段 2/3: 引用一个 DUT 自声明能力档案。precheck section 2.3 拿请求 (mimo_layers/
  // modulation) 跟声明比, 请求 > 声明提前 fail (规划期, attach 前)。留空=不做声明校验。
  dut_profile_id?: string
  // strict: 请求超声明时 FAIL (默认 true); false=降级 warning 继续 (bring-up 旁路)。
  precheck_strict_dut_capability?: boolean
  // P2-13 Phase 3: 引用一张 SIMProfile。managed 流程在 MEASURE 受控 attach 后核对
  // UXM/UE 实测 IMSI；legacy/unmanaged 流程仍在 PRECHECK 核对已有 attach 快照。
  sim_profile_id?: string
  // strict: attach IMSI ≠ 声明 → FAIL (默认 true); false=降级 warning。
  precheck_strict_sim_identity?: boolean
  // P2-11 #1974: UXM 端口路由/调度 per-test 驱动 (留空=用 Topology Profile 默认, 不覆盖)
  mimo_port_preset?: string
  sched_algo?: string
  csi_rs_ports?: number | null
  engine_mode?: string
  theoretical_peak_throughput_mbps?: number
  // === 仪表使用参数 (开关 3 块 2, #217) — 全部留空 = 现行为不变 ===
  // F64 直通模式 1-3: 非空 = 测量停在无衰落直通态 (STATIC <mode>, 不 GO);
  // 2=Butler (保 MIMO 秩) / 3=校准 (-10dB 等增益) / 1=模型旁路。
  f64_bypass_mode?: number
  // 非空 = 手动定标 (直接写 F64 输入参考, 跳过 AUTOSET 闭环 + 读回存档)。
  f64_input_ref_dbm?: number
  // 手动定标的峰均比 — 随 f64_input_ref_dbm 一起生效, 单独填后端不消费。
  f64_crest_db?: number
  // 非空 = 信道加载后对全部活跃输出统一写 OUTP:GAIN。
  f64_output_gain_db?: number
  // AUTOSET 闭环的 UXM 起始功率 (留空 = controller 默认 -10 dBm)。
  input_loop_initial_dl_power_dbm?: number
  base_station_config_mode?: string
  /** @deprecated 仅用于读取旧 TestCase；表单不再写该键。 */
  uxm_config_mode?: string
  pass_criteria?: PassCriteria
  step_overrides?: Record<string, unknown> | null
  // Tolerate forward-compat extras
  [key: string]: unknown
}

interface Props {
  value: MIMOOTAConfiguration
  onChange: (next: MIMOOTAConfiguration) => void
  readOnly?: boolean
  testCaseId?: string | null
  labProfileId?: string | null
  compatibilityContextSaved?: boolean
}

const CDL_OPTIONS = [
  { value: 'UMi LOS CDL-D', label: 'UMi LOS · CDL-D' },
  { value: 'UMi NLOS CDL-A', label: 'UMi NLOS · CDL-A' },
  { value: 'UMa LOS CDL-D', label: 'UMa LOS · CDL-D' },
  { value: 'UMa NLOS CDL-C', label: 'UMa NLOS · CDL-C' },
  { value: 'InH CDL-B', label: 'InH · CDL-B' },
  { value: 'CDL-A', label: 'CDL-A' },
  { value: 'CDL-B', label: 'CDL-B' },
  { value: 'CDL-C', label: 'CDL-C' },
  { value: 'CDL-D', label: 'CDL-D' },
  { value: 'CDL-E', label: 'CDL-E' },
]

const MODULATION_OPTIONS = ['QPSK', '16QAM', '64QAM', '256QAM', '1024QAM']
// P2-16 S4-5: ChannelAsset source_type → 中文标签 (供统一信道资产 Select 显示)
const CHANNEL_ASSET_SOURCE_LABEL: Record<string, string> = {
  standard_3gpp: '标准 3GPP',
  custom_static: '自定义 CDL',
  rt_dynamic: 'RT 动态',
  vendor_file: '厂商文件',
}

const SCS_OPTIONS = [
  { value: '15', label: '15 kHz' },
  { value: '30', label: '30 kHz' },
  { value: '60', label: '60 kHz' },
  { value: '120', label: '120 kHz' },
]

const ENGINE_OPTIONS = [
  { value: 'mimo_first_asc', label: 'MIMO-First ASC (自研)' },
  { value: 'keysight_gcm', label: 'Keysight GCM (原生)' },
]

// P2-11 #1974: UXM MIMO 天线→物理端口路由 preset (跟后端 RealUxmDriver.MIMO_PORT_PRESETS 同步)
const MIMO_PORT_PRESET_OPTIONS = [
  { value: 'siso', label: 'SISO (单端口)' },
  { value: '2x2', label: '2×2' },
  { value: '4x4', label: '4×4' },
  { value: '2x2_alt', label: '2×2 备用端口 (RF3+RF4)' },
]

export function MIMOOTAConfigForm({
  value,
  onChange,
  readOnly = false,
  testCaseId,
  labProfileId,
  compatibilityContextSaved = false,
}: Props) {
  const { selectedLabProfileId } = useOperationalLab()
  const compatibilityLabProfileId = labProfileId !== undefined
    ? labProfileId
    : selectedLabProfileId
  const rawPCell = value.component_carriers?.[0]
  const radioTechnology = rawPCell?.radio_technology === 'lte' ? 'lte' : 'nr5g'
  const baseStationConfigMode = resolveBaseStationConfigMode(value)
  const cmwReadinessQuery = useQuery({
    queryKey: [
      'base-station-testcase-readiness',
      compatibilityLabProfileId ?? 'unselected',
      testCaseId ?? 'unsaved',
    ],
    queryFn: () => fetchReadiness(compatibilityLabProfileId ?? undefined, testCaseId!),
    enabled: compatibilityContextSaved
      && Boolean(testCaseId),
  })
  const cmwReadiness = cmwReadinessQuery.data?.cmw500_lte_2x2
  const siteCertification = cmwReadinessQuery.data?.base_station_site_certification
  const cmwReadinessView = describeCmw500Readiness(
    cmwReadiness,
    rawPCell?.duplex,
    baseStationConfigMode.mode,
    siteCertification,
  )
  const compatibilityView = !compatibilityContextSaved
    ? {
        light: 'red' as const,
        valueText: '未保存',
        detail: 'TestCase 配置或 LabProfile 仍有未保存修改；保存后才能核对仪表兼容性',
      }
    : cmwReadinessQuery.isLoading
      ? {
          light: 'red' as const,
          valueText: '核对中',
          detail: '正在根据已保存 TestCase 与 LabProfile 核对 BaseStation 兼容性',
        }
      : cmwReadinessQuery.error
        ? {
            light: 'red' as const,
            valueText: '读取失败',
            detail: '无法确认已保存 TestCase 与 BaseStation 的兼容性',
          }
        : projectBaseStationCompatibilityTruth(
            cmwReadinessQuery.data?.base_station_testcase_compatibility,
          )
  const showCmwReadiness = radioTechnology === 'lte'
    && cmwReadiness?.status !== 'not_applicable'
  const update = <K extends keyof MIMOOTAConfiguration>(
    key: K,
    next: MIMOOTAConfiguration[K],
  ): void => {
    onChange({ ...value, [key]: next })
  }

  /**
   * P1-55：PCell 是唯一运行真值。界面从 PCell 显示，编辑时同步旧顶层镜像；
   * SCell 与 band 均保持不变。后端会拒绝任何显式分叉，避免错频静默落库。
   */
  const updateCarrierField = (
    key: 'frequency_hz' | 'bandwidth_mhz' | 'subcarrier_spacing_khz',
    next: number | undefined,
  ): void => {
    if (typeof next !== 'number' || !Number.isFinite(next)) return

    onChange(updatePrimaryCarrierValue(value, key, next))
  }

  const patchPCell = (patch: Record<string, unknown>): void => {
    onChange(patchPrimaryCarrierFields(value, patch))
  }

  const switchRadioTechnology = (rat: 'nr5g' | 'lte'): void => {
    const current = rawPCell ?? {
      frequency_hz: value.frequency_hz,
      bandwidth_mhz: value.bandwidth_mhz,
      role: 'pcell',
    }
    const pcell = rat === 'lte'
      ? {
          ...current, radio_technology: 'lte' as const, channel_kind: 'lte_dl_earfcn' as const,
          band: undefined, duplex: undefined, lte_dl_earfcn: undefined,
          lte_transmission_mode: undefined,
          nr_arfcn: undefined, subcarrier_spacing_khz: undefined, role: 'pcell' as const,
        }
      : {
          ...current, radio_technology: 'nr5g' as const, channel_kind: 'nr_arfcn' as const,
          band: undefined, nr_arfcn: undefined, subcarrier_spacing_khz: 30,
          duplex: undefined, lte_dl_earfcn: undefined, role: 'pcell' as const,
          lte_transmission_mode: undefined,
        }
    const next: MIMOOTAConfiguration = { ...value, component_carriers: [pcell] }
    if (rat === 'lte') {
      next.subcarrier_spacing_khz = undefined
      next.theoretical_peak_throughput_mbps = undefined
    }
    onChange(next)
  }

  const updatePass = <K extends keyof PassCriteria>(key: K, next: PassCriteria[K]): void => {
    onChange({ ...value, pass_criteria: { ...(value.pass_criteria ?? {}), [key]: next } })
  }

  // GCM 模式 F64 加载的 .smu 来自 operator-curated available_channel_models (SCD 关联 +
  // 手敲); 按类别取 (生产里 channelEmulator 全局唯一 = 一台 F64), 跟 ChannelModelsCard 同源。
  const channelModelsQuery = useQuery({
    queryKey: ['channelModels', 'channelEmulator'],
    queryFn: () => fetchChannelModels('channelEmulator'),
  })
  // value=filename (F64 CALC:FILT:FILE 加载的真实路径, 直接当 emulation_file), 显示=label (SCD 标准名)。
  // 只列 type==='smu' (Codex on #120): keysight_gcm 走 F64 原生管线 (CALC:FILT:FILE →
  // DIAG:SIMU:GO) 只播 .smu; .rtc 是 Runtime 管线 (CH:MOD:CONT:ENV)、.asc 是 ASC 引擎产物 ——
  // 选进 emulation_file 会在 F64 信道加载时才失败, 在表单这里就挡掉无效原生 GCM 文件。
  const smuItems = (channelModelsQuery.data?.items ?? []).filter((e) => e.type === 'smu')
  // slice 4: filename → scd_id 查找。SCD 派生 entry 有 scd_id → 选中存 scd_id (measure 查
  // SCD + 频率 cross-check); 手敲 entry 无 scd_id → 选中存裸 emulation_file (legacy, 无 cross-check)。
  const scdIdByFilename = new Map(smuItems.map((e) => [e.filename, e.scd_id ?? null]))
  const fetchedEmulationOptions = smuItems.map((e) => ({ value: e.filename, label: e.label }))
  // Select 以 filename 为统一 value: scd_id 引用 → 反查它的 filename; 否则用裸 emulation_file。
  const selectedFilename = value.scd_id
    ? (smuItems.find((e) => e.scd_id === value.scd_id)?.filename ?? null)
    : (value.emulation_file ?? null)
  // 当前选中若不在清单 (别处设的/清单外), 也列出来避免静默丢显示。
  const emulationFileOptions =
    selectedFilename && !fetchedEmulationOptions.some((o) => o.value === selectedFilename)
      ? [...fetchedEmulationOptions, { value: selectedFilename, label: `${selectedFilename} (清单外)` }]
      : fetchedEmulationOptions
  // engine_mode = ASC 时 .smu 无关 (channel-engine 按 frequency 生成 .asc, 不用 .smu)。
  const isAscEngine = value.engine_mode === 'mimo_first_asc'

  // DUTProfile 阶段 3: 列规划期建好的 DUT 声明供选 (precheck section 2.3 拿请求跟它比)。
  const dutProfilesQuery = useQuery({
    queryKey: ['dut-profiles'],
    queryFn: () => fetchDUTProfiles(false),
  })
  const dutProfiles = dutProfilesQuery.data ?? []
  const dutOptions = dutProfiles.map((d) => ({ value: d.id, label: d.name }))
  const selectedDut = dutProfiles.find((d) => d.id === value.dut_profile_id) ?? null
  // 选中若不在清单 (别处设的 id / 已删) 也列出避免静默丢显示。
  const dutSelectOptions =
    value.dut_profile_id && !dutOptions.some((o) => o.value === value.dut_profile_id)
      ? [...dutOptions, { value: value.dut_profile_id, label: `${value.dut_profile_id} (清单外)` }]
      : dutOptions
  // strict 默认 true (后端 default), 仅当显式 false 才关。
  const dutStrict = value.precheck_strict_dut_capability !== false
  // P2-13 Phase 3: 列卡池供选（managed 流程在 MEASURE attach 后核对实测 IMSI）。
  const simProfilesQuery = useQuery({
    queryKey: ['sim-profiles'],
    queryFn: () => fetchSIMProfiles(false),
  })
  const simProfiles = simProfilesQuery.data ?? []
  const simOptions = simProfiles.map((s) => ({ value: s.id, label: s.name }))
  const selectedSim = simProfiles.find((s) => s.id === value.sim_profile_id) ?? null
  const simSelectOptions =
    value.sim_profile_id && !simOptions.some((o) => o.value === value.sim_profile_id)
      ? [...simOptions, { value: value.sim_profile_id, label: `${value.sim_profile_id} (清单外)` }]
      : simOptions
  const simStrict = value.precheck_strict_sim_identity !== false
  // P2-15: 列自定义 CDL 档案供选 (选了 → 后端 input_mode=custom 用 profile 簇覆盖标称 CDL)。
  const cdlProfilesQuery = useQuery({
    queryKey: ['custom-cdl-profiles'],
    queryFn: () => fetchCustomCDLProfiles(false),
  })
  const cdlProfiles = cdlProfilesQuery.data ?? []
  const cdlOptions = cdlProfiles.map((c) => ({ value: c.id, label: c.name }))
  const cdlSelectOptions =
    value.cdl_profile_id && !cdlOptions.some((o) => o.value === value.cdl_profile_id)
      ? [...cdlOptions, { value: value.cdl_profile_id, label: `${value.cdl_profile_id} (清单外)` }]
      : cdlOptions
  // P2-16 S4-5: 列信道工作台 ChannelAsset 供选 (选了 → 后端 channel_asset_resolver 按 source_type
  // 派生 engine_mode + 覆盖下方传统信道字段; 方案 A: 留空走传统字段)。
  const channelAssetsQuery = useQuery({
    queryKey: ['channel-assets', 'active'],
    queryFn: () => fetchChannelAssets({ includeInactive: false }),
  })
  const channelAssets = channelAssetsQuery.data ?? []
  // 多快照 rt_dynamic 资产执行会 fail-loud (轨迹执行待 S5, channel_asset_resolver 对 snapshots>1
  // raise), 故选择器禁用该 option + 标注, 别让用户选了到运行期才发现不能执行 (Codex #185 P2)。
  const channelAssetOptions = channelAssets.map((a) => {
    const snaps = (a.payload as { snapshots?: unknown[] })?.snapshots
    const isMultiSnapshotRt =
      a.source_type === 'rt_dynamic' && Array.isArray(snaps) && snaps.length > 1
    return {
      value: a.id,
      label:
        `${a.name}（${CHANNEL_ASSET_SOURCE_LABEL[a.source_type] ?? a.source_type}）` +
        (isMultiSnapshotRt ? ' — 多快照·执行待 S5' : ''),
      disabled: isMultiSnapshotRt,
    }
  })
  const channelAssetSelectOptions =
    value.channel_asset_id && !channelAssetOptions.some((o) => o.value === value.channel_asset_id)
      ? [...channelAssetOptions, { value: value.channel_asset_id, label: `${value.channel_asset_id} (清单外/已删)`, disabled: false }]
      : channelAssetOptions
  const selectedAsset = channelAssets.find((a) => a.id === value.channel_asset_id) ?? null
  const hasChannelAsset = value.channel_asset_id != null && value.channel_asset_id !== ''
  // 实时一致性预览 — 跟后端 precheck section 2.3 / check_dut_capability 同口径, 表单里就给反馈,
  // 不用等真跑。声明项缺失 (null) 跳过该项。调制阶数用 MODULATION_OPTIONS 顺序 (= 后端 _MODULATIONS)。
  const dutPreviewViolations: string[] = []
  if (selectedDut) {
    if (
      selectedDut.max_dl_layers != null &&
      value.mimo_layers != null &&
      value.mimo_layers > selectedDut.max_dl_layers
    ) {
      dutPreviewViolations.push(`DL 层 ${value.mimo_layers} > 声明 ${selectedDut.max_dl_layers}`)
    }
    const modIdx = (m?: string | null) => (m ? MODULATION_OPTIONS.indexOf(m.toUpperCase()) : -1)
    const reqMod = modIdx(value.modulation)
    const decMod = modIdx(selectedDut.max_modulation_dl)
    if (reqMod >= 0 && decMod >= 0 && reqMod > decMod) {
      dutPreviewViolations.push(
        `DL 调制 ${value.modulation} > 声明 ${selectedDut.max_modulation_dl}`,
      )
    }
  }

  const azimuths = value.azimuths_deg ?? []
  const pass = value.pass_criteria ?? {}
  const rsrpLow = pass.rsrp_range_dbm?.[0]
  const rsrpHigh = pass.rsrp_range_dbm?.[1]

  return (
    <Stack gap="md">
      {/* Channel */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text size="sm" fw={600}>
            3GPP 信道模型
          </Text>
          {/* P2-16 S4-5: 统一信道资产引用 (信道工作台 ChannelAsset)。设了 → 后端按 source_type
              派生 engine_mode + 覆盖下方传统信道字段 (方案 A)。 */}
          <Select
            label="统一信道资产 (ChannelAsset)"
            description="选信道工作台的资产 → 按 source_type 派生引擎 + 覆盖下方传统信道源字段；留空=用下方传统字段"
            data={channelAssetSelectOptions}
            value={value.channel_asset_id ?? null}
            onChange={(v) => update('channel_asset_id', v ?? undefined)}
            disabled={readOnly}
            clearable
            searchable
            placeholder={
              channelAssetSelectOptions.length === 0
                ? '无信道资产 — 去「信道工作台」建'
                : '(用下方传统信道字段)'
            }
          />
          {hasChannelAsset && (
            <Alert color="blue" variant="light">
              已选统一信道资产
              {selectedAsset ? `「${selectedAsset.name}」（${CHANNEL_ASSET_SOURCE_LABEL[selectedAsset.source_type] ?? selectedAsset.source_type}）` : ''}
              —— 后端按其 source_type 派生 engine_mode 并覆盖下方标称/自定义 CDL / .smu 字段（下方信道源已禁用）。
            </Alert>
          )}
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Select
              label="CDL 信道模型"
              description="3GPP TR 38.901 标准模型"
              data={CDL_OPTIONS}
              value={value.cdl_model_name ?? null}
              onChange={(v) => update('cdl_model_name', v ?? undefined)}
              disabled={readOnly || hasChannelAsset}
              allowDeselect={false}
              searchable
            />
            <Select
              label="自定义 CDL (可选)"
              description={
                isAscEngine
                  ? '选「自定义 CDL」页建的簇档案 → input_mode=custom; 留空=用上面标称 CDL'
                  : '仅 MIMO-First ASC 引擎支持; GCM 引擎用标称 CDL / .smu (Codex P2 #171)'
              }
              data={cdlSelectOptions}
              value={value.cdl_profile_id ?? null}
              onChange={(v) => update('cdl_profile_id', v ?? undefined)}
              disabled={readOnly || !isAscEngine || hasChannelAsset}
              clearable
              searchable
              placeholder={
                cdlSelectOptions.length === 0 ? '无自定义 CDL — 去「自定义 CDL」页建' : '(用标称 CDL)'
              }
            />
            <Select
              label="无线制式"
              description="PCell 显式真值；LTE 不继承 NR ARFCN/SCS/峰值"
              data={[{ value: 'nr5g', label: '5G NR' }, { value: 'lte', label: 'LTE' }]}
              value={radioTechnology}
              onChange={(v) => switchRadioTechnology(v === 'lte' ? 'lte' : 'nr5g')}
              disabled={readOnly}
              allowDeselect={false}
            />
            <TextInput
              label="频段 Band"
              placeholder={radioTechnology === 'lte' ? 'B3' : 'N78'}
              value={rawPCell?.band ?? ''}
              onChange={(e) => patchPCell({ band: e.currentTarget.value.toUpperCase() || undefined })}
              disabled={readOnly}
              required={radioTechnology === 'lte'}
            />
            {radioTechnology === 'lte' ? (
              <>
                <Select
                  label="双工模式"
                  data={[{ value: 'fdd', label: 'FDD' }, { value: 'tdd', label: 'TDD' }]}
                  value={rawPCell?.duplex ?? null}
                  onChange={(v) => patchPCell({ duplex: v ?? undefined })}
                  disabled={readOnly}
                  required
                />
                <NumberInput
                  label="LTE DL EARFCN"
                  value={rawPCell?.lte_dl_earfcn ?? undefined}
                  onChange={(v) => patchPCell({ lte_dl_earfcn: typeof v === 'number' ? v : undefined })}
                  min={0}
                  disabled={readOnly}
                  required
                />
                <Select
                  label="LTE 传输模式"
                  data={LTE_TRANSMISSION_MODES.map((mode) => ({ value: mode, label: mode }))}
                  value={rawPCell?.lte_transmission_mode ?? null}
                  onChange={(v) => patchPCell({ lte_transmission_mode: v ?? undefined })}
                  disabled={readOnly}
                  required
                />
              </>
            ) : (
              <NumberInput
                label="NR-ARFCN（可选显式）"
                value={rawPCell?.nr_arfcn ?? undefined}
                onChange={(v) => patchPCell({ nr_arfcn: typeof v === 'number' ? v : undefined })}
                min={0}
                disabled={readOnly}
              />
            )}
            <Select
              label="子载波间隔"
              data={SCS_OPTIONS}
              value={
                primaryCarrierValue(value, 'subcarrier_spacing_khz') != null
                  ? String(primaryCarrierValue(value, 'subcarrier_spacing_khz'))
                  : null
              }
              onChange={(v) => updateCarrierField('subcarrier_spacing_khz', v ? Number(v) : undefined)}
              disabled={readOnly || radioTechnology === 'lte'}
              allowDeselect={false}
            />
            {/* P2-11 一致性按 ARFCN 整数比对 (nr_arfcn.py), 输入粒度必须细过 NR 栅格
                (5/15/60 kHz): MHz 3 位小数 = 1 kHz, 全档覆盖 (此前 GHz 3 位 = 1 MHz,
                3549.99 写不进, 门永挂)。Math.round 消 ×1e6 浮点尘埃 (栅格频率是整 Hz)。 */}
            <NumberInput
              label="中心频率 (MHz)"
              description="后端存储为 frequency_hz; MHz 口径跟 ARFCN/资产/报错文案一致 (例 3549.99)"
              value={
                primaryCarrierValue(value, 'frequency_hz') != null
                  ? primaryCarrierValue(value, 'frequency_hz')! / 1e6
                  : undefined
              }
              onChange={(v) =>
                updateCarrierField(
                  'frequency_hz',
                  typeof v === 'number' ? Math.round(v * 1e6) : undefined,
                )
              }
              decimalScale={3}
              step={1}
              min={400}
              max={71000}
              disabled={readOnly}
            />
            <NumberInput
              label="带宽"
              suffix=" MHz"
              value={primaryCarrierValue(value, 'bandwidth_mhz')}
              onChange={(v) => updateCarrierField('bandwidth_mhz', typeof v === 'number' ? v : undefined)}
              min={1}
              max={400}
              disabled={readOnly}
            />
            <Select
              label="信道仿真文件 (.smu)"
              description={
                isAscEngine
                  ? 'ASC 模式按频率自动生成 .asc, 无需指定'
                  : 'GCM 模式 F64 加载的标准信道文件 (来自信道仿真器清单 / SCD)'
              }
              data={emulationFileOptions}
              value={selectedFilename}
              onChange={(v) => {
                // slice 4: 选 SCD 派生项 (有 scd_id) → 存 scd_id 走 cross-check; 选手敲项 →
                // 存裸 emulation_file (legacy); 二者互斥, 清掉另一个。
                const scd = v ? scdIdByFilename.get(v) : null
                if (scd) onChange({ ...value, scd_id: scd, emulation_file: undefined })
                else onChange({ ...value, scd_id: undefined, emulation_file: v ?? undefined })
              }}
              disabled={readOnly || isAscEngine || hasChannelAsset}
              placeholder={
                emulationFileOptions.length === 0
                  ? '无可选 .smu — 去信道仿真器抽屉或 SCD 管理添加'
                  : '选择标准信道文件'
              }
              searchable
              clearable
              nothingFoundMessage="无匹配的信道文件"
            />
          </SimpleGrid>
        </Stack>
      </Paper>

      {/* MIMO */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text size="sm" fw={600}>
            MIMO 配置
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <NumberInput
              label="MIMO 层数"
              description="layer 数, 不是天线数"
              value={value.mimo_layers}
              onChange={(v) => update('mimo_layers', typeof v === 'number' ? v : undefined)}
              min={1}
              max={8}
              disabled={readOnly}
            />
            <Select
              label="调制方式"
              data={MODULATION_OPTIONS}
              value={value.modulation ?? null}
              onChange={(v) => update('modulation', v ?? undefined)}
              disabled={readOnly}
              allowDeselect={false}
            />
            <Select
              label="MIMO 端口路由 (preset)"
              description="留空=用 Topology Profile 默认 (不覆盖)"
              data={MIMO_PORT_PRESET_OPTIONS}
              value={value.mimo_port_preset ?? null}
              onChange={(v) => update('mimo_port_preset', v ?? undefined)}
              disabled={readOnly}
              clearable
              placeholder="(用 profile 默认)"
            />
            <NumberInput
              label="CSI-RS 端口数"
              description="留空=按 MIMO 层数自动推断"
              value={value.csi_rs_ports ?? undefined}
              onChange={(v) => update('csi_rs_ports', typeof v === 'number' ? v : null)}
              min={1}
              max={32}
              disabled={readOnly}
            />
          </SimpleGrid>
        </Stack>
      </Paper>

      {/* DUT 声明能力校验 */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text size="sm" fw={600}>
            DUT 声明能力校验
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Select
              label="DUT 声明"
              description="选规划期建好的 DUT 能力档案 (在「DUT 声明」页维护); 留空=不校验"
              data={dutSelectOptions}
              value={value.dut_profile_id ?? null}
              onChange={(v) => update('dut_profile_id', v ?? undefined)}
              disabled={readOnly}
              clearable
              searchable
              placeholder={
                dutSelectOptions.length === 0
                  ? '无 DUT 声明 — 去「DUT 声明」页新建'
                  : '选择 DUT 声明'
              }
              nothingFoundMessage="无匹配的 DUT 声明"
            />
            <Switch
              label="严格校验 (请求超声明则 fail)"
              description="关 = 仅降级 warning 继续 (bring-up 旁路)"
              checked={dutStrict}
              onChange={(e) =>
                update('precheck_strict_dut_capability', e.currentTarget.checked)
              }
              disabled={readOnly || !value.dut_profile_id}
              mt="lg"
            />
          </SimpleGrid>
          {selectedDut ? (
            <Text size="xs" c="dimmed">
              声明: 最大 DL {selectedDut.max_dl_layers ?? '—'} 层 / 调制{' '}
              {selectedDut.max_modulation_dl ?? '—'}
              {selectedDut.duplex_mode ? ` / ${selectedDut.duplex_mode}` : ''}
            </Text>
          ) : null}
          {selectedDut && dutPreviewViolations.length > 0 ? (
            <Text size="xs" c="red">
              ⚠ 请求超声明: {dutPreviewViolations.join('; ')} —{' '}
              {dutStrict ? '严格模式下预检会 fail' : '当前降级 warning 继续'}
            </Text>
          ) : null}
        </Stack>
      </Paper>

      {/* SIM 卡 (防插错卡) */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text size="sm" fw={600}>
            SIM 卡 (防插错卡)
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Select
              label="SIM 卡"
              description="选规划期建好的测试卡 (在「SIM 卡管理」页维护); 留空=不校验"
              data={simSelectOptions}
              value={value.sim_profile_id ?? null}
              onChange={(v) => update('sim_profile_id', v ?? undefined)}
              disabled={readOnly}
              clearable
              searchable
              placeholder={
                simSelectOptions.length === 0
                  ? '无 SIM 卡 — 去「SIM 卡管理」页新建'
                  : '选择 SIM 卡'
              }
              nothingFoundMessage="无匹配的 SIM 卡"
            />
            <Switch
              label="严格校验（实测 IMSI 缺失或不符则 fail）"
              description="managed 流程在受控 attach 后核对 UXM/UE 实测值；关 = 未验证 warning 继续"
              checked={simStrict}
              onChange={(e) =>
                update('precheck_strict_sim_identity', e.currentTarget.checked)
              }
              disabled={readOnly || !value.sim_profile_id}
              mt="lg"
            />
          </SimpleGrid>
          {selectedSim ? (
            <Text size="xs" c="dimmed">
              声明: IMSI {selectedSim.imsi ?? '—'}
              {selectedSim.mcc && selectedSim.mnc ? ` / PLMN ${selectedSim.mcc}-${selectedSim.mnc}` : ''}
              {selectedSim.card_kind ? ` / ${selectedSim.card_kind}` : ''} ——
              attach 后拿实测 IMSI 跟它比, 不符提示插错卡
            </Text>
          ) : null}
        </Stack>
      </Paper>

      {/* Spatial sweep + sampling */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text size="sm" fw={600}>
            转台扫描 & 采样
          </Text>
          <TagsInput
            label="测量方位角 (度)"
            description="用空格或回车分隔, 例如 0 90 180 270"
            value={azimuths.map(String)}
            onChange={(tags) =>
              update(
                'azimuths_deg',
                tags
                  .map((t) => parseFloat(t))
                  .filter((n) => Number.isFinite(n)),
              )
            }
            disabled={readOnly}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <NumberInput
              label="单方位测量时长"
              suffix=" s"
              value={value.measurement_duration_s}
              onChange={(v) =>
                update('measurement_duration_s', typeof v === 'number' ? v : undefined)
              }
              min={0}
              decimalScale={1}
              step={0.5}
              disabled={readOnly}
            />
            <NumberInput
              label="转台稳定等待"
              suffix=" s"
              value={value.settling_time_s}
              onChange={(v) =>
                update('settling_time_s', typeof v === 'number' ? v : undefined)
              }
              min={0}
              decimalScale={1}
              step={0.5}
              disabled={readOnly}
            />
            <NumberInput
              label="每方位采样数"
              value={value.num_samples_per_azimuth}
              onChange={(v) =>
                update('num_samples_per_azimuth', typeof v === 'number' ? v : undefined)
              }
              min={1}
              max={10000}
              disabled={readOnly}
            />
            <NumberInput
              label="采样间隔"
              suffix=" ms"
              value={value.sample_interval_ms}
              onChange={(v) =>
                update('sample_interval_ms', typeof v === 'number' ? v : undefined)
              }
              min={1}
              decimalScale={1}
              disabled={readOnly}
            />
          </SimpleGrid>
        </Stack>
      </Paper>

      {/* Power targets */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text size="sm" fw={600}>
            功率目标
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
            <NumberInput
              label="基站发射功率"
              suffix=" dBm"
              value={value.target_tx_power_dbm}
              onChange={(v) =>
                update('target_tx_power_dbm', typeof v === 'number' ? v : undefined)
              }
              decimalScale={1}
              disabled={readOnly}
            />
            <NumberInput
              label="目标 RSRP"
              suffix=" dBm"
              value={value.target_rsrp_dbm}
              onChange={(v) =>
                update('target_rsrp_dbm', typeof v === 'number' ? v : undefined)
              }
              decimalScale={1}
              disabled={readOnly}
            />
            <NumberInput
              label="目标 SNR"
              suffix=" dB"
              value={value.target_snr_db}
              onChange={(v) =>
                update('target_snr_db', typeof v === 'number' ? v : undefined)
              }
              decimalScale={1}
              disabled={readOnly}
            />
          </SimpleGrid>
        </Stack>
      </Paper>

      {/* Pass criteria */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text size="sm" fw={600}>
            CTIA 判定门限
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <NumberInput
              label="吞吐量比例下限"
              description="实测 / 理论峰值"
              value={pass.min_throughput_ratio}
              onChange={(v) =>
                updatePass('min_throughput_ratio', typeof v === 'number' ? v : undefined)
              }
              min={0}
              max={1}
              step={0.05}
              decimalScale={2}
              disabled={readOnly}
            />
            <NumberInput
              label="吞吐量绝对下限"
              suffix=" Mbps"
              value={pass.min_throughput_mbps}
              onChange={(v) =>
                updatePass('min_throughput_mbps', typeof v === 'number' ? v : undefined)
              }
              min={0}
              decimalScale={1}
              disabled={readOnly}
            />
            <NumberInput
              label="RSRP 方位间最大偏差"
              suffix=" dB"
              value={pass.max_rsrp_variance_db}
              onChange={(v) =>
                updatePass('max_rsrp_variance_db', typeof v === 'number' ? v : undefined)
              }
              min={0}
              decimalScale={1}
              disabled={readOnly}
            />
            <NumberInput
              label="SINR 下限"
              suffix=" dB"
              value={pass.min_sinr_db}
              onChange={(v) => updatePass('min_sinr_db', typeof v === 'number' ? v : undefined)}
              decimalScale={1}
              disabled={readOnly}
            />
            <NumberInput
              label="平均 Rank Indicator 下限"
              value={pass.min_avg_rank_indicator}
              onChange={(v) =>
                updatePass(
                  'min_avg_rank_indicator',
                  typeof v === 'number' ? v : undefined,
                )
              }
              min={0}
              max={8}
              decimalScale={2}
              step={0.1}
              disabled={readOnly}
            />
            <NumberInput
              label="静区纹波上限"
              suffix=" dB"
              value={pass.max_quiet_zone_ripple_db}
              onChange={(v) =>
                updatePass(
                  'max_quiet_zone_ripple_db',
                  typeof v === 'number' ? v : undefined,
                )
              }
              min={0}
              decimalScale={2}
              disabled={readOnly}
            />
          </SimpleGrid>
          <Fieldset legend="可接受 RSRP 范围 (dBm)">
            <Group grow>
              <NumberInput
                label="下限"
                value={rsrpLow}
                onChange={(v) => {
                  const lo = typeof v === 'number' ? v : 0
                  const hi = typeof rsrpHigh === 'number' ? rsrpHigh : lo
                  updatePass('rsrp_range_dbm', [lo, hi])
                }}
                decimalScale={1}
                disabled={readOnly}
              />
              <NumberInput
                label="上限"
                value={rsrpHigh}
                onChange={(v) => {
                  const hi = typeof v === 'number' ? v : 0
                  const lo = typeof rsrpLow === 'number' ? rsrpLow : hi
                  updatePass('rsrp_range_dbm', [lo, hi])
                }}
                decimalScale={1}
                disabled={readOnly}
              />
            </Group>
          </Fieldset>
        </Stack>
      </Paper>

      {/* Advanced — collapsed by default */}
      <Accordion variant="separated" radius="md" multiple>
        <Accordion.Item value="reference">
          <Accordion.Control>
            <Text size="sm" fw={600}>
              参考天线 (Phase 2 基线测量)
            </Text>
          </Accordion.Control>
          <Accordion.Panel>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              <TextInput
                label="标准增益喇叭型号"
                value={value.reference_antenna_model ?? ''}
                onChange={(e) => update('reference_antenna_model', e.target.value)}
                disabled={readOnly}
              />
              <NumberInput
                label="参考天线增益"
                suffix=" dBi"
                value={value.reference_antenna_gain_dbi}
                onChange={(v) =>
                  update(
                    'reference_antenna_gain_dbi',
                    typeof v === 'number' ? v : undefined,
                  )
                }
                decimalScale={2}
                disabled={readOnly}
              />
            </SimpleGrid>
          </Accordion.Panel>
        </Accordion.Item>

        <Accordion.Item value="basestation">
          <Accordion.Control>
            <Text size="sm" fw={600}>
              基站 MAC 配置 (Phase 3 吞吐量测量)
            </Text>
          </Accordion.Control>
          <Accordion.Panel>
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
              <NumberInput
                label="MCS 索引"
                description="3GPP MCS 0-31"
                value={value.mcs}
                onChange={(v) => update('mcs', typeof v === 'number' ? v : undefined)}
                min={0}
                max={31}
                disabled={readOnly}
              />
              <Switch
                label="启用 AMC"
                description="关闭=固定 MCS, 结果可重复"
                checked={value.enable_amc ?? false}
                onChange={(e) => update('enable_amc', e.currentTarget.checked)}
                disabled={readOnly}
              />
              <TextInput
                label="TDD 时隙模式"
                placeholder="DDDSU"
                value={value.tdd_pattern ?? ''}
                onChange={(e) => update('tdd_pattern', e.target.value)}
                disabled={readOnly}
              />
              <TextInput
                label="TDD 周期"
                placeholder="5MS"
                value={value.tdd_period ?? ''}
                onChange={(e) => update('tdd_period', e.target.value)}
                disabled={readOnly}
              />
              <TextInput
                label="PDSCH 调度算法"
                description="留空=用 profile 默认"
                placeholder="FULLBUFFER"
                value={value.sched_algo ?? ''}
                onChange={(e) => update('sched_algo', e.target.value || undefined)}
                disabled={readOnly}
              />
              <NumberInput
                label="HARQ 最大重传次数"
                value={value.harq_max_trans}
                onChange={(v) =>
                  update('harq_max_trans', typeof v === 'number' ? v : undefined)
                }
                min={1}
                max={16}
                disabled={readOnly}
              />
              <NumberInput
                label="HARQ 进程数"
                value={value.harq_processes}
                onChange={(v) =>
                  update('harq_processes', typeof v === 'number' ? v : undefined)
                }
                min={1}
                max={32}
                disabled={readOnly}
              />
              <NumberInput
                label="统计窗口"
                description="≥5000 大致 5s"
                value={value.stat_count}
                onChange={(v) => update('stat_count', typeof v === 'number' ? v : undefined)}
                min={100}
                disabled={readOnly}
              />
            </SimpleGrid>
          </Accordion.Panel>
        </Accordion.Item>

        <Accordion.Item value="engine">
          <Accordion.Control>
            <Text size="sm" fw={600}>
              信道生成引擎
            </Text>
          </Accordion.Control>
          <Accordion.Panel>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              <Select
                label="引擎模式"
                data={ENGINE_OPTIONS}
                value={value.engine_mode ?? null}
                onChange={(v) => {
                  const next = v ?? undefined
                  // P2-15 (Codex P2 #171): 切离 ASC 引擎时清空 cdl_profile_id —— custom CDL 只
                  // ASC 支持, 否则 disabled 的下拉留 stale 值 + 后端 gate 拒绝 → plan 卡死无法清。
                  if (next !== 'mimo_first_asc' && value.cdl_profile_id) {
                    onChange({ ...value, engine_mode: next, cdl_profile_id: undefined })
                  } else {
                    update('engine_mode', next)
                  }
                }}
                disabled={readOnly}
                allowDeselect={false}
              />
              <NumberInput
                label="理论峰值吞吐量"
                suffix=" Mbps"
                description={
                  radioTechnology === 'lte'
                    ? 'LTE 只接受本次显式值；留空时绝对吞吐可用，ratio 与相关判决显示 N/A'
                    : '用于 ratio 判定基准'
                }
                value={value.theoretical_peak_throughput_mbps}
                onChange={(v) =>
                  update(
                    'theoretical_peak_throughput_mbps',
                    typeof v === 'number' ? v : undefined,
                  )
                }
                min={0}
                disabled={readOnly}
              />
            </SimpleGrid>
          </Accordion.Panel>
        </Accordion.Item>

        {/* 开关 3 块 2 (#217): 仪表使用参数 — 后端 measure 消费, 此前只能 API 改。
            全部留空 = 现行为不变 (UXM 主动下发 + F64 自动定标闭环 + 衰落回放)。 */}
        <Accordion.Item value="instrument">
          <Accordion.Control>
            <Text size="sm" fw={600}>
              仪表使用参数 (现场调试旋钮)
            </Text>
          </Accordion.Control>
          <Accordion.Panel>
            <Stack gap="md">
              <Text size="xs" c="dimmed">
                全部留空 = 现行为不变：UXM 主动下发小区参数、F64 自动定标闭环、正常衰落回放。
              </Text>
              <Alert
                color={compatibilityView.light === 'green'
                  ? 'green'
                  : compatibilityView.light === 'yellow'
                    ? 'yellow'
                    : 'red'}
                variant="light"
                title={`TestCase × BaseStation：${compatibilityView.valueText}`}
              >
                <Text size="sm">{compatibilityView.detail}</Text>
              </Alert>
              {showCmwReadiness && (
                <Alert
                  color={cmwReadinessView.color}
                  variant="light"
                  title={cmwReadinessView.title}
                >
                  <Stack gap={4}>
                    <Text size="sm">{cmwReadinessView.message}</Text>
                    {cmwReadiness && (
                      <Text size="xs">
                        适配器{cmwReadiness.adapter_registered ? '已注册' : '未注册'} · 型号{' '}
                        {cmwReadiness.model ?? 'UNKNOWN'} · 固件{' '}
                        {cmwReadiness.firmware_version ?? 'UNKNOWN'} · 选件{' '}
                        {cmwReadiness.options.length > 0
                          ? cmwReadiness.options.join(', ')
                          : 'UNKNOWN'} · 正式能力{' '}
                        {cmwReadiness.formal_enabled ? '已显式启用' : '默认关闭'}
                        {cmwReadiness.formal_updated_at
                          ? ` · 服务器更新 ${cmwReadiness.formal_updated_at}`
                          : ''}
                      </Text>
                    )}
                    <Text size="xs">
                      当前现场认证：{siteCertification?.status === 'active'
                        && siteCertification.binding_digest === cmwReadiness?.binding_digest
                        ? `有效 · ${siteCertification.certified_at}`
                        : siteCertification?.status === 'revoked'
                          ? '已撤销，仅可诊断'
                          : siteCertification
                            ? '与当前 binding 不匹配，仅可诊断'
                            : '未认证，仅可诊断'}
                    </Text>
                    <Text size="xs">
                      上述 CMW 正式能力开关仅为历史兼容快照，不授予本次执行正式资格。
                    </Text>
                    <Text size="xs">发布前仍需真机确认；本片不做功率预算判定。</Text>
                  </Stack>
                </Alert>
              )}
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                <Select
                  label="基站小区配置来源 (开关 1)"
                  description="调试继承 = 跳过静态小区下发并核对当前态；所得数据不进入正式 KPI 或判决"
                  data={[
                    { value: 'dispatch', label: '主动下发 (默认) — 下发全套小区参数并回读对账' },
                    { value: 'inherit', label: '基站当前态调试继承 — 仅诊断，不参与正式判定' },
                  ]}
                  value={baseStationConfigMode.mode}
                  error={baseStationConfigMode.conflict ? '新旧配置来源字段冲突，请重新选择后保存' : undefined}
                  onChange={(v) =>
                    onChange(
                      updateBaseStationConfigMode(
                        value,
                        v === 'inherit' ? 'inherit' : 'dispatch',
                      ),
                    )
                  }
                  allowDeselect={false}
                  disabled={readOnly}
                />
                <Select
                  label="F64 直通模式 (开关 2)"
                  description="设了 = 测量阶段停在无衰落直通态 (不播衰落, 输出功率显示会冻结)；留空 = 正常衰落回放"
                  data={[
                    { value: '2', label: 'STATIC 2 — Butler 直通 (保 MIMO 秩, 4×4 建链用)' },
                    { value: '3', label: 'STATIC 3 — 校准直通 (统一 -10 dB, 单层/校准)' },
                    { value: '1', label: 'STATIC 1 — 模型直通 (模型平均衰减)' },
                  ]}
                  value={value.f64_bypass_mode != null ? String(value.f64_bypass_mode) : null}
                  onChange={(v) => update('f64_bypass_mode', v ? Number(v) : undefined)}
                  clearable
                  placeholder="(衰落回放)"
                  disabled={readOnly}
                />
                <NumberInput
                  label="F64 输入参考电平"
                  suffix=" dBm"
                  description="设了 = 手动定标, 跳过自动定标闭环并读回存档 (07-03 实证 -15)；留空 = 自动定标"
                  value={value.f64_input_ref_dbm}
                  onChange={(v) =>
                    update('f64_input_ref_dbm', typeof v === 'number' ? v : undefined)
                  }
                  decimalScale={1}
                  disabled={readOnly}
                />
                <NumberInput
                  label="峰均比 (crest)"
                  suffix=" dB"
                  description="手动定标的一部分, 随「输入参考电平」一起生效 (07-03 实证 12)"
                  value={value.f64_crest_db}
                  onChange={(v) =>
                    update('f64_crest_db', typeof v === 'number' ? v : undefined)
                  }
                  decimalScale={1}
                  disabled={readOnly}
                />
                <NumberInput
                  label="F64 输出增益"
                  suffix=" dB"
                  description="设了 = 信道加载后对全部活跃输出统一写增益；留空 = 不调整"
                  value={value.f64_output_gain_db}
                  onChange={(v) =>
                    update('f64_output_gain_db', typeof v === 'number' ? v : undefined)
                  }
                  decimalScale={1}
                  disabled={readOnly}
                />
                <NumberInput
                  label="闭环起点功率 (UXM)"
                  suffix=" dBm"
                  description="自动定标闭环的 UXM 起始功率；留空 = 默认 -10 (比 -46 基线热 36 dB)。手动定标时不生效"
                  value={value.input_loop_initial_dl_power_dbm}
                  onChange={(v) =>
                    update(
                      'input_loop_initial_dl_power_dbm',
                      typeof v === 'number' ? v : undefined,
                    )
                  }
                  decimalScale={1}
                  disabled={readOnly}
                />
              </SimpleGrid>
              {value.f64_crest_db != null && value.f64_input_ref_dbm == null && (
                <Alert color="yellow" variant="light">
                  峰均比单独填不生效 —— 它是手动定标的一部分, 请把「F64 输入参考电平」也填上；
                  只想用自动定标就把峰均比清空。
                </Alert>
              )}
              {value.f64_input_ref_dbm != null &&
                value.input_loop_initial_dl_power_dbm != null && (
                  <Alert color="yellow" variant="light">
                    已设「输入参考电平」= 手动定标, 「闭环起点功率」不会被消费 (它只属于自动定标闭环)。
                  </Alert>
                )}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>

        {value.step_overrides && Object.keys(value.step_overrides).length > 0 && (
          <Accordion.Item value="overrides">
            <Accordion.Control>
              <Text size="sm" fw={600}>
                Step 级 Override (高级 / 只读)
              </Text>
            </Accordion.Control>
            <Accordion.Panel>
              <Code block style={{ whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(value.step_overrides, null, 2)}
              </Code>
              <Text size="xs" c="dimmed" mt="xs">
                此处的 sweep_type / power_range 等参数由 legacy 迁移工具填入,
                目前不在编辑器中暴露。需要修改请直接编辑 TestCase.configuration JSON.
              </Text>
            </Accordion.Panel>
          </Accordion.Item>
        )}
      </Accordion>
    </Stack>
  )
}
