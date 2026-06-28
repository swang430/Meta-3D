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

import { fetchChannelModels } from '../../../../api/service'
import { fetchDUTProfiles } from '../../../../api/dutProfileService'
import { fetchSIMProfiles } from '../../../../api/simProfileService'
import { fetchCustomCDLProfiles } from '../../../../api/customCdlProfileService'

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
  // P2-13 Phase 3: 引用一张 SIMProfile (测试卡)。precheck 拿 attach IMSI 跟声明核对 (防插错卡)。
  sim_profile_id?: string
  // strict: attach IMSI ≠ 声明 → FAIL (默认 true); false=降级 warning。
  precheck_strict_sim_identity?: boolean
  // P2-11 #1974: UXM 端口路由/调度 per-test 驱动 (留空=用 Topology Profile 默认, 不覆盖)
  mimo_port_preset?: string
  sched_algo?: string
  csi_rs_ports?: number | null
  engine_mode?: string
  theoretical_peak_throughput_mbps?: number
  pass_criteria?: PassCriteria
  step_overrides?: Record<string, unknown> | null
  // Tolerate forward-compat extras
  [key: string]: unknown
}

interface Props {
  value: MIMOOTAConfiguration
  onChange: (next: MIMOOTAConfiguration) => void
  readOnly?: boolean
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

export function MIMOOTAConfigForm({ value, onChange, readOnly = false }: Props) {
  const update = <K extends keyof MIMOOTAConfiguration>(
    key: K,
    next: MIMOOTAConfiguration[K],
  ): void => {
    onChange({ ...value, [key]: next })
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
  // P2-13 Phase 3: 列卡池供选 (precheck 拿 attach IMSI 跟它声明 IMSI 比, 防插错卡)。
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
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Select
              label="CDL 信道模型"
              description="3GPP TR 38.901 标准模型"
              data={CDL_OPTIONS}
              value={value.cdl_model_name ?? null}
              onChange={(v) => update('cdl_model_name', v ?? undefined)}
              disabled={readOnly}
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
              disabled={readOnly || !isAscEngine}
              clearable
              searchable
              placeholder={
                cdlSelectOptions.length === 0 ? '无自定义 CDL — 去「自定义 CDL」页建' : '(用标称 CDL)'
              }
            />
            <Select
              label="子载波间隔"
              data={SCS_OPTIONS}
              value={
                value.subcarrier_spacing_khz != null
                  ? String(value.subcarrier_spacing_khz)
                  : null
              }
              onChange={(v) => update('subcarrier_spacing_khz', v ? Number(v) : undefined)}
              disabled={readOnly}
              allowDeselect={false}
            />
            <NumberInput
              label="中心频率 (GHz)"
              description="后端存储为 frequency_hz"
              value={value.frequency_hz != null ? value.frequency_hz / 1e9 : undefined}
              onChange={(v) =>
                update('frequency_hz', typeof v === 'number' ? v * 1e9 : undefined)
              }
              decimalScale={3}
              step={0.1}
              min={0.4}
              max={71}
              disabled={readOnly}
            />
            <NumberInput
              label="带宽"
              suffix=" MHz"
              value={value.bandwidth_mhz}
              onChange={(v) => update('bandwidth_mhz', typeof v === 'number' ? v : undefined)}
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
              disabled={readOnly || isAscEngine}
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
              label="严格校验 (attach IMSI 不符则 fail)"
              description="关 = 仅降级 warning 继续 (bring-up 旁路)"
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
                description="用于 ratio 判定基准"
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
