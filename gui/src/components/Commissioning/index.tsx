import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Container, Title, Text, Stepper, Group, Button, Paper, Stack, Divider, Loader, Select, Badge, Alert, TextInput, Switch, NumberInput, SimpleGrid } from '@mantine/core'
import { IconTestPipe, IconPlayerPlay, IconPlayerTrackNext, IconAlertTriangle } from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import { PrecheckPhase, ReferencePhase, MIMOTestPhase, AnalysisPhase, ReportPhase } from './Phases'
import * as api from './api'
import type { SessionResponse, LabResolutionDetail } from './api'
import { useOperationalLab, useOperationalLabSwitchGuard } from '../../features/OperationalLab'
import { fetchChannelAssets, type ChannelAsset } from '../../api/channelAssetService'
import { parseChannelFrequencyIdentity } from '../../features/ChannelWorkbench/channelFrequencyIdentity'
import { fetchReadiness } from '../../api/service'
import {
  compareFrozenCmwApproval,
  readFrozenCmwApproval,
} from '../TestCaseConfig/cmw500ReadinessTruth'

const PHASE_STEPS = [
  { id: 'precheck', label: '系统预检', desc: '仪表状态与校准验证' },
  { id: 'reference', label: '参考测量', desc: '基线TRP测量与补偿' },
  { id: 'mimo_test', label: 'MIMO测试', desc: '3GPP CDL 吞吐量' },
  { id: 'analysis', label: '分析判定', desc: 'CTIA 门限对比' },
  { id: 'report', label: '报告归档', desc: '生成标准报告' },
]

interface HttpLikeError {
  message?: string
  response?: {
    status?: number
    data?: { detail?: unknown }
  }
}

const asHttpError = (error: unknown): HttpLikeError =>
  typeof error === 'object' && error !== null ? error as HttpLikeError : {}

export function CommissioningSandbox() {
  const [session, setSession] = useState<SessionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  // 暗室首测是操作员显式选择资产后启动的临时 bring-up UI，默认走 F64
  // 原生 GCM；无 ChannelAsset / .smu 时下方启动门保持禁用。后端与正式
  // TestCase 的无参默认仍是 ASC，避免把缺资产的隐式请求改成必然失败。
  const [engineMode, setEngineMode] = useState<string>(
    api.DEFAULT_COMMISSIONING_ENGINE_MODE,
  )
  // RF 冷启动工作点：2026-08-07 现场已验证的基线。它们不是共享 schema
  // 默认，而是本次 session 的显式输入；创建后会固定进 execution.config。
  const [frequencyMhz, setFrequencyMhz] = useState(3549.99)
  const [bandwidthMhz, setBandwidthMhz] = useState(40)
  const [radioTechnology, setRadioTechnology] = useState<'nr5g' | 'lte'>('nr5g')
  const [band, setBand] = useState('N78')
  const [duplex, setDuplex] = useState<'fdd' | 'tdd'>('fdd')
  const [nrArfcn, setNrArfcn] = useState<number | string>(636666)
  const [lteDlEarfcn, setLteDlEarfcn] = useState<number | string>('')
  const [lteTransmissionMode, setLteTransmissionMode] = (
    useState<api.LteTransmissionMode>('TM3')
  )
  const [subcarrierSpacingKhz, setSubcarrierSpacingKhz] = useState(30)
  const [theoreticalPeakMbps, setTheoreticalPeakMbps] = useState<number | string>('')
  const [uxmPowerDbmPerBw, setUxmPowerDbmPerBw] = useState(-15)
  const [f64InputRefDbm, setF64InputRefDbm] = useState(-17)
  const [f64CrestDb, setF64CrestDb] = useState(15)
  const [f64OutputLevelDbm, setF64OutputLevelDbm] = useState(-52)
  const [f64BypassAssist, setF64BypassAssist] = useState(true)
  const [emulationFile, setEmulationFile] = useState('')
  const [channelAssetId, setChannelAssetId] = useState<string | null>(null)
  const [channelAssets, setChannelAssets] = useState<ChannelAsset[]>([])
  // Lab-smoke: relax strict safety gates（cal 在 PRECHECK；managed DUT 动态门在
  // MEASURE）for local rehearsal without a real DUT/calibration. Default OFF
  // keeps on-site first-call fail-loud protection enabled.
  const [labSmoke, setLabSmoke] = useState(false)
  // 2026-08-07 现场: 只放过校准证书那一道门。跟 labSmoke 分开是因为 labSmoke
  // 一开就废掉全部 8 道。校准没做完 vs DUT 能不能在本次 RF 配置下 attach
  // 是两件事，后者仍由 MEASURE 的受控 attach 动态门负责。
  const [diagnosticMode, setDiagnosticMode] = useState(false)
  const [diagnosticOperator, setDiagnosticOperator] = useState('')
  const [diagnosticReason, setDiagnosticReason] = useState('')
  // U-5: 暗室首测前逐设备自检 (借鉴转台/EMCenter standalone 验证, 首测前先单独验各仪表通)
  const [selfcheck, setSelfcheck] = useState<api.DeviceSelfcheckResult | null>(null)
  const [selfcheckLoading, setSelfcheckLoading] = useState(false)
  // DUT 身份元数据登记（可选）。正式连接不靠这条记录判定：执行器会先按
  // TestCase 初始化 UXM/F64/开关矩阵，再读取 UXM CONN 状态。这里保留 IMSI/
  // 型号输入，供 SIM 身份核对与执行追溯使用。
  const [dutImsi, setDutImsi] = useState<string>('')
  const [dutModel, setDutModel] = useState<string>('')
  const [attachResult, setAttachResult] = useState<api.AttachDutResponse | null>(null)
  const [attachError, setAttachError] = useState<string | null>(null)
  const [attachLoading, setAttachLoading] = useState(false)
  // 2026-05-18 P0-7: only meaningful when engineMode==='external_asc'.
  // Operator-supplied absolute path of a local directory of channel_InX_OutY.asc
  // files (typically produced by ChannelEgine app.py Streamlit on the same host).
  const [ascSourcePath, setAscSourcePath] = useState<string>('')

  // P1-57：LabProfile 来自全局上下文（header 唯一选择器）。本页不再自选、
  // 不再读写 localStorage —— 旧 key 已由全局上下文一次性迁移并删除。
  // 会话创建后 lab/chamber 事实锁进 session.config；切换由 guard 阻断。
  const {
    selectedLabProfileId: labId,
    selectedLabProfile,
    chamberName,
    activeLabs,
    loading: labsLoading,
    error: labsError,
    beginWork,
    activeWork,
  } = useOperationalLab()
  const cmwReadinessQuery = useQuery({
    queryKey: ['cmw500-lte-2x2-readiness', labId ?? 'unselected'],
    queryFn: () => fetchReadiness(labId!),
    enabled: Boolean(labId) && Boolean(session),
  })
  const frozenCmwApproval = readFrozenCmwApproval(session?.config)
  const frozenCmwApprovalDrift = compareFrozenCmwApproval(
    cmwReadinessQuery.data?.cmw500_lte_2x2,
    session?.config,
  )
  // 外审 R3：在途硬件工作的唯一真值 = provider 的登记表（页面卸载不消失、
  // 并发各自计数，共享布尔会被先落定的那个提前放行）。本页是目前唯一登记方。
  const hardwareBusy = activeWork.length > 0
  // 内审 F1：列表**加载失败**不得当成「0 个 LabProfile」（设计 §8）——
  // 否则瞬断会引操作员去建重复 LabProfile。失败时 error 非空，这里不判 0。
  const noActiveLab = !labsLoading && !labsError && activeLabs.length === 0
  useOperationalLabSwitchGuard(
    'commissioning',
    session ? '暗室首测会话进行中 —— 请先点「结束会话」再切换 LabProfile' : null,
  )
  // Bumped on every explicit retry attempt (button click) so the init
  // effect re-fires even when labId hasn't changed.
  // Without this, a transient failure (500, network blip, explicit lab
  // rejected by backend) would leave the page stuck — the deps
  // stays unchanged, and
  // the effect's deps don't change so nothing re-runs. Codex P2 on PR #27.
  const [initAttempt, setInitAttempt] = useState(0)


  useEffect(() => {
    fetchChannelAssets({ includeInactive: false })
      .then(setChannelAssets)
      .catch(() => {
        // 资产清单失败不伪装为空清单：裸 .smu 仍可现场输入，后端会做严格门。
        notifications.show({
          title: '信道资产清单读取失败',
          message: '可改用显式 .smu 路径；创建会话时仍会由后端校验。',
          color: 'yellow',
        })
      })
  }, [])

  // Initialization
  const initSession = async () => {
    const releaseWork = beginWork('commissioning', '首测会话正在创建（硬件初始化中）')
    try {
      setLoading(true)
      const res = await api.createSession({
        radioTechnology,
        engineMode,
        labProfileId: labId || undefined,
        ascSourcePath: engineMode === 'external_asc' ? ascSourcePath : undefined,
        channelAssetId: channelAssetId || undefined,
        frequencyHz: frequencyMhz * 1e6,
        bandwidthMhz,
        band: band.trim().toUpperCase(),
        duplex: radioTechnology === 'lte' ? duplex : undefined,
        subcarrierSpacingKhz: radioTechnology === 'nr5g' ? subcarrierSpacingKhz : undefined,
        nrArfcn: radioTechnology === 'nr5g' && typeof nrArfcn === 'number' ? nrArfcn : undefined,
        lteDlEarfcn: radioTechnology === 'lte' && typeof lteDlEarfcn === 'number' ? lteDlEarfcn : undefined,
        lteTransmissionMode: radioTechnology === 'lte' ? lteTransmissionMode : undefined,
        theoreticalPeakThroughputMbps: radioTechnology === 'lte' && typeof theoreticalPeakMbps === 'number' ? theoreticalPeakMbps : undefined,
        uxmDlPowerDbmPerBw: radioTechnology === 'nr5g' ? uxmPowerDbmPerBw : undefined,
        f64InputRefDbm,
        f64CrestDb,
        f64OutputLevelDbm,
        emulationFile: emulationFile.trim() || undefined,
        f64BypassMode: f64BypassAssist ? 2 : undefined,
        labSmoke,
        executionPolicyMode: diagnosticMode || labSmoke ? 'diagnostic' : undefined,
        executionPolicyReason: diagnosticMode || labSmoke ? diagnosticReason.trim() : undefined,
        executionPolicyUpdatedBy: diagnosticMode || labSmoke ? diagnosticOperator.trim() : undefined,
      })
      setSession(res.data)
      setActiveStep(0)
      notifications.show({ title: '首测会话已创建', message: `ID: ${res.data.session_id}`, color: 'blue' })
    } catch (error: unknown) {
      const err = asHttpError(error)
      // 422 with structured LabResolutionDetail → render picker / route
      // to wizard instead of just toasting a useless error.
      const detail = err.response?.data?.detail
      const status = err.response?.status
      if (status === 422 && detail && typeof detail === 'object' && 'kind' in detail) {
        const lrd = detail as LabResolutionDetail
        if (lrd.kind === 'ambiguous') {
          // 全局上下文送了显式 lab_profile_id 时不该出现；万一出现，
          // 指向唯一的选择入口（header），本页不再自带 picker。
          notifications.show({
            title: '请选择当前 LabProfile',
            message: `当前 DB 有 ${lrd.active_labs.length} 个活动 LabProfile —— 请用顶部选择器选定后重试`,
            color: 'yellow',
          })
        } else if (lrd.kind === 'none') {
          notifications.show({
            title: '尚无 LabProfile',
            message: '请先通过首次启动向导创建 LabProfile',
            color: 'red',
          })
        }
        return
      }
      // Other errors: keep the legacy toast behavior.
      const msg = typeof detail === 'string' ? detail : err.message ?? '未知错误'
      notifications.show({ title: '初始化失败', message: String(msg), color: 'red' })
    } finally {
      releaseWork()
      setLoading(false)
    }
  }

  useEffect(() => {
    // RF 工作点现在是会话创建前的必审输入，因此不再因“已有默认 lab / 切换
    // engine”自动创建。只有操作员点击「启动首测会话」使 initAttempt 递增才执行。
    if (initAttempt === 0) return
    if (!labId) return
    // external_asc 必须先有 ASC 路径才能建会话 (后端校验)。engineMode 在 deps 里,
    // 切到 external_asc 会触发本 effect; 若此时路径还没填, 不要 auto-fire 一个注定
    // 422 的 createSession。等操作员填好路径点「启动」(bump initAttempt) 再建。
    if (engineMode === 'external_asc' && !ascSourcePath.trim()) return
    if (
      engineMode === 'keysight_gcm' &&
      !channelAssetId &&
      !emulationFile.trim()
    ) return
    initSession()
    // 只依赖显式点击计数。选择 lab/资产、编辑频率或切换引擎都只是编辑表单，
    // 不得静默创建一个操作员尚未确认的硬件工作点。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initAttempt])

  const handleRunPhase = async (phaseId: string) => {
    if (!session) return
    const releaseWork = beginWork('commissioning', `相位 ${phaseId} 正在驱动硬件`)
    try {
      setLoading(true)
      await api.runPhase(session.session_id, phaseId)
      // refresh status
      const res = await api.getSession(session.session_id)
      setSession(res.data)
      
      const newStatus = res.data.phase_statuses[phaseId]
      if (newStatus === 'completed') {
        setActiveStep(prev => prev + 1)
      }
    } catch (error: unknown) {
      const err = asHttpError(error)
      const detail = err.response?.data?.detail || err.message
      notifications.show({ title: '执行失败', message: String(detail).substring(0, 200), color: 'red' })
    } finally {
      releaseWork()
      setLoading(false)
    }
  }

  const handleRunAll = async () => {
    if (!session) return
    const releaseWork = beginWork('commissioning', '全流程正在驱动硬件')
    try {
      setLoading(true)
      // Step through automatically or just call runAll
      await api.runAll(session.session_id)
      const res = await api.getSession(session.session_id)
      setSession(res.data)
      setActiveStep(5)
    } catch (error: unknown) {
      const err = asHttpError(error)
      const detail = err.response?.data?.detail || err.message
      notifications.show({ title: '执行全流程失败', message: String(detail).substring(0, 200), color: 'red' })
    } finally {
      releaseWork()
      setLoading(false)
    }
  }

  // Pre-session render: must show the lab picker / wizard hint BEFORE
  // showing a "loading session" spinner — otherwise a 0-active or
  // ambiguous-active deployment loops the operator on a spinner with
  // no way to make progress.
  if (!session) {
    return (
      <Container size="xl" py="md">
        <Stack gap="md">
          <Group gap="sm" align="center">
            <IconTestPipe size={28} />
            <Title order={2}>暗室首测 (Sandbox)</Title>
          </Group>

          {noActiveLab && (
            <Alert color="red" icon={<IconAlertTriangle size={18} />} title="尚无活动 LabProfile">
              请先通过首次启动向导创建至少一个活动的 LabProfile，再回到这里启动首测。
            </Alert>
          )}

          {!noActiveLab && !labId && (
            <Alert color="yellow" icon={<IconAlertTriangle size={18} />} title="请选择当前 LabProfile">
              当前有多个活动 LabProfile —— 请用顶部的全局选择器选定本次首测的实验室。
            </Alert>
          )}

          <Paper withBorder p="md" radius="md">
            <Stack gap="md">
              <Group align="flex-end">
                <TextInput
                  label="LabProfile / 暗室"
                  description="来自顶部全局选择器；会话创建后锁进 session.config"
                  value={selectedLabProfile
                    ? `${selectedLabProfile.name}${chamberName ? ` / ${chamberName}` : '（未绑定暗室）'}`
                    : '未选择'}
                  readOnly
                  w={400}
                />
                <Select
                  label="信道生成引擎"
                  description="本次首测会话使用的合成引擎; 会话创建后锁定"
                  data={[
                    { value: 'mimo_first_asc', label: '🧠 MIMO-First 自研引擎 (ASC Synthesis)' },
                    { value: 'keysight_gcm', label: '🔧 Keysight F64 原生 GCM (Native)' },
                    { value: 'external_asc', label: '📂 External ASC (operator-supplied, debug)' },
                  ]}
                  value={engineMode}
                  onChange={(val) => {
                    if (!val) return
                    setEngineMode(val)
                    // 不把上一引擎的资产残留带进新引擎；重新选择等于显式确认。
                    setChannelAssetId(null)
                  }}
                  w={360}
                />
                <Button
                  loading={loading}
                  disabled={
                    !labId ||
                    // 2026-05-18 P0-7: external_asc 必须给路径才能启动会话
                    (engineMode === 'external_asc' && !ascSourcePath.trim()) ||
                    // GCM 冷启动必须能解析本次 .smu；不能再借用 F64 遗留场景。
                    (engineMode === 'keysight_gcm' && !channelAssetId && !emulationFile.trim()) ||
                    !Number.isFinite(frequencyMhz) || frequencyMhz <= 0 ||
                    !Number.isFinite(bandwidthMhz) || bandwidthMhz <= 0 ||
                    !band.trim() ||
                    (radioTechnology === 'nr5g' && typeof nrArfcn !== 'number') ||
                    (radioTechnology === 'lte' && typeof lteDlEarfcn !== 'number')
                  }
                  onClick={() => {
                    // Bump the attempt counter so the init effect re-fires
                    // even when labId hasn't changed — i.e., retry after a
                    // transient failure on the
                    // same lab. Without this the button is a dead end after
                    // the first failure. Codex P2 on PR #27.
                    setInitAttempt((n) => n + 1)
                  }}
                  leftSection={<IconPlayerPlay size={16} />}
                >
                  启动首测会话
                </Button>
              </Group>

              <Divider label="本次 RF 冷启动工作点" labelPosition="left" />
              <Alert color="blue" title="先初始化 F64，再允许 DUT attach">
                本次会话会先加载所选信道、核对 F64 中心频率、设置输入/输出工作点并建立
                Butler 直通，然后才启动 UXM 等待 DUT。F64 带宽来自信道资产声明；没有资产时
                会明确记为 unknown，不再把设备能力 100 MHz 当作场景带宽。
              </Alert>

              <Select
                clearable
                searchable
                disabled={engineMode === 'external_asc'}
                label="信道资产（推荐）"
                description="优先选择已登记资产；资产同时提供场景文件与带宽来源"
                placeholder="选择 ChannelAsset，或在 GCM 模式输入 .smu"
                data={channelAssets.map((asset) => {
                  const requiredTarget = engineMode === 'keysight_gcm'
                    ? 'gcm_native'
                    : 'asc_baked'
                  const engineCompatible = asset.allowed_targets.includes(requiredTarget)
                  const assetPayload = asset.payload as
                    | { snapshots?: unknown[] }
                    | null
                    | undefined
                  const multiSnapshotRt =
                    asset.source_type === 'rt_dynamic' &&
                    Array.isArray(assetPayload?.snapshots) &&
                    (assetPayload?.snapshots?.length ?? 0) > 1
                  return {
                    value: asset.id,
                    label:
                      `${asset.name}（${asset.source_type}）` +
                      (!engineCompatible ? ' — 与当前引擎不兼容' : ''),
                    disabled: !engineCompatible || multiSnapshotRt,
                  }
                })}
                value={channelAssetId}
                onChange={(value) => {
                  setChannelAssetId(value)
                  const asset = channelAssets.find((item) => item.id === value)
                  const scd = parseChannelFrequencyIdentity(
                    (asset?.payload as { scd_config?: unknown } | undefined)?.scd_config,
                  )
                  if (scd) {
                    setRadioTechnology(scd.radioTechnology)
                    setBand(scd.band)
                    if (scd.radioTechnology === 'lte') {
                      setLteDlEarfcn(scd.channelNumber)
                      setNrArfcn('')
                    } else {
                      setNrArfcn(scd.channelNumber)
                      setLteDlEarfcn('')
                    }
                  }
                  if (asset?.center_frequency_hz != null) {
                    setFrequencyMhz(asset.center_frequency_hz / 1e6)
                  }
                  if (asset?.bandwidth_mhz != null) {
                    setBandwidthMhz(asset.bandwidth_mhz)
                  }
                }}
              />

              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
                <Select
                  label="无线制式"
                  data={[{ value: 'nr5g', label: '5G NR' }, { value: 'lte', label: 'LTE' }]}
                  value={radioTechnology}
                  onChange={(value) => {
                    const rat = value === 'lte' ? 'lte' : 'nr5g'
                    setRadioTechnology(rat)
                    setBand(rat === 'lte' ? '' : 'N78')
                    setNrArfcn(rat === 'nr5g' ? 636666 : '')
                    setLteDlEarfcn('')
                    setTheoreticalPeakMbps('')
                  }}
                  allowDeselect={false}
                />
                <TextInput label="频段 Band" placeholder={radioTechnology === 'lte' ? 'B3' : 'N78'} value={band}
                  onChange={(event) => setBand(event.currentTarget.value.toUpperCase())} required />
                {radioTechnology === 'lte' ? (
                  <>
                    <Select label="双工模式" data={[{ value: 'fdd', label: 'FDD' }, { value: 'tdd', label: 'TDD' }]}
                      value={duplex} onChange={(value) => setDuplex(value === 'tdd' ? 'tdd' : 'fdd')} allowDeselect={false} />
                    <NumberInput label="LTE DL EARFCN" value={lteDlEarfcn}
                      onChange={setLteDlEarfcn} min={0} required />
                    <Select label="LTE 传输模式"
                      data={[...api.LTE_TRANSMISSION_MODES]}
                      value={lteTransmissionMode}
                      onChange={(value) => setLteTransmissionMode(
                        (value ?? 'TM3') as api.LteTransmissionMode,
                      )}
                      allowDeselect={false}
                      required />
                    <NumberInput label="LTE 理论峰值（可选）" suffix=" Mbps" value={theoreticalPeakMbps}
                      description="留空时绝对吞吐仍可用，ratio 与相关判决为 N/A"
                      onChange={setTheoreticalPeakMbps} min={0} />
                  </>
                ) : (
                  <>
                    <NumberInput label="NR-ARFCN" value={nrArfcn} onChange={setNrArfcn} min={0} required />
                    <NumberInput label="子载波间隔" suffix=" kHz" value={subcarrierSpacingKhz}
                      onChange={(value) => setSubcarrierSpacingKhz(Number(value))} min={1} required />
                  </>
                )}
                <NumberInput
                  label="中心频率 (MHz)"
                  value={frequencyMhz}
                  decimalScale={3}
                  onChange={(value) => setFrequencyMhz(Number(value))}
                  min={1}
                />
                <NumberInput
                  label="基站带宽 (MHz)"
                  value={bandwidthMhz}
                  onChange={(value) => setBandwidthMhz(Number(value))}
                  min={1}
                />
                {radioTechnology === 'nr5g' && (
                  <NumberInput
                    label="UXM 整带宽功率 (dBm)"
                    value={uxmPowerDbmPerBw}
                    onChange={(value) => setUxmPowerDbmPerBw(Number(value))}
                    decimalScale={1}
                  />
                )}
                <NumberInput
                  label="F64 输入参考 (dBm)"
                  value={f64InputRefDbm}
                  onChange={(value) => setF64InputRefDbm(Number(value))}
                  decimalScale={1}
                />
                <NumberInput
                  label="F64 Crest (dB)"
                  value={f64CrestDb}
                  onChange={(value) => setF64CrestDb(Number(value))}
                  decimalScale={1}
                />
                <NumberInput
                  label="F64 输出电平 (dBm)"
                  description="现场已知 -50 会超口 1 上限；基线为 -52"
                  value={f64OutputLevelDbm}
                  onChange={(value) => setF64OutputLevelDbm(Number(value))}
                  decimalScale={1}
                />
              </SimpleGrid>

              <Switch
                checked={f64BypassAssist}
                onChange={(e) => setF64BypassAssist(e.currentTarget.checked)}
                label="attach 前使用 F64 Butler 直通（STATIC 2）"
                description="在本次 .smu 加载后建立；DUT 挂上后按既有流程撤直通并启动衰落"
              />

              {engineMode === 'keysight_gcm' && !channelAssetId && (
                <TextInput
                  required
                  label="F64 .smu 路径"
                  description="必须是 F64 本机可访问的 .smu；不允许依赖仪表上一次加载的场景"
                  placeholder={'D:\\Scenario Packs\\...\\your_model.smu'}
                  value={emulationFile}
                  onChange={(e) => setEmulationFile(e.currentTarget.value)}
                  error={!emulationFile.trim() ? 'GCM 模式必须选择信道资产或填写 .smu' : undefined}
                />
              )}

              {/* 2026-05-18 P0-7: External ASC 模式专属路径输入. 仅在 pre-session
                  阶段可编辑 (会话创建后路径被锁进 session.config), 所以只有这一
                  处可见. Codex P2 on PR #56 修复 — 之前放在 post-session UI 是
                  unreachable code. */}
              {engineMode === 'external_asc' && (
                <TextInput
                  label="ASC 目录绝对路径"
                  description="本机存放 channel_InX_OutY.asc 文件的目录 (操作员从 ChannelEgine app.py 产出)"
                  placeholder="/Users/yourname/asc_outputs/2026-05-19"
                  value={ascSourcePath}
                  onChange={(e) => setAscSourcePath(e.currentTarget.value)}
                />
              )}

              <Divider my={4} />
              <Switch
                checked={diagnosticMode}
                onChange={(e) => setDiagnosticMode(e.currentTarget.checked)}
                label="Diagnostic（仅可诊断）"
                description="本次执行冻结为黄色诊断资格；数值不会进入正式 KPI。"
              />
              <Switch
                checked={labSmoke}
                onChange={(e) => setLabSmoke(e.currentTarget.checked)}
                label="强制跳过严格 DUT / 校准门（real 模式 override）"
                description="mock 模式（无真实仪表）已自动跳过严格门，无需开此开关。仅当你接了真实仪表、但想在没有 DUT / 校准的情况下空跑预检时才打开。默认关闭，以保留 P1-8/P1-9 fail-loud 保护。"
              />
              {(diagnosticMode || labSmoke) && (
                <SimpleGrid cols={{ base: 1, sm: 2 }}>
                  <TextInput required label="操作人" value={diagnosticOperator} onChange={(e) => setDiagnosticOperator(e.currentTarget.value)} />
                  <TextInput required label="诊断原因" value={diagnosticReason} onChange={(e) => setDiagnosticReason(e.currentTarget.value)} />
                </SimpleGrid>
              )}
            </Stack>
          </Paper>

          {loading && (
            <Group gap="xs">
              <Loader size="sm" />
              <Text size="sm" c="dimmed">初始化会话中...</Text>
            </Group>
          )}
        </Stack>
      </Container>
    )
  }

  return (
    <Container size="xl" py="md">
      <Stack gap="lg">
        {/* Header */}
        <div>
          <Group gap="sm" align="center">
            <IconTestPipe size={28} />
            <Title order={2}>暗室首测 (Sandbox)</Title>
          </Group>
          <Text size="sm" c="dimmed" mt={4}>
            3GPP Static MIMO OTA 调试专区 - 基于 UMa CDL-C 模型与 CTIA 门限
          </Text>
        </div>

        {/* 引擎模式 + Lab 选择 */}
        <Paper withBorder p="md" radius="md">
          <Group justify="space-between" align="flex-end">
            <Group align="flex-end">
              <Select
                label="信道生成引擎"
                description="选择波形合成的计算引擎"
                data={[
                  { value: 'mimo_first_asc', label: '🧠 MIMO-First 自研引擎 (ASC Synthesis)' },
                  { value: 'keysight_gcm', label: '🔧 Keysight F64 原生 GCM (Native)' },
                  { value: 'external_asc', label: '📂 External ASC (operator-supplied, debug)' },
                ]}
                value={engineMode}
                onChange={(val) => val && setEngineMode(val)}
                w={360}
              />
              <TextInput
                label="LabProfile / 暗室"
                description="会话进行中锁定；切换请先点「结束会话」"
                value={selectedLabProfile
                  ? `${selectedLabProfile.name}${chamberName ? ` / ${chamberName}` : ''}`
                  : '未选择'}
                readOnly
                w={280}
              />
            </Group>
            <Group gap="xs">
              <Badge
                color={
                  engineMode === 'mimo_first_asc'
                    ? 'blue'
                    : engineMode === 'keysight_gcm'
                      ? 'orange'
                      : 'gray'
                }
                variant="light"
                size="lg"
              >
                {engineMode === 'mimo_first_asc'
                  ? '自研算力'
                  : engineMode === 'keysight_gcm'
                    ? 'F64 原生'
                    : 'External ASC (调试)'}
              </Badge>
              {Boolean(session?.config?.engine_mode) && (
                <Badge color="gray" variant="outline" size="lg">
                  会话锁定: {
                    session.config.engine_mode === 'mimo_first_asc'
                      ? 'MIMO-First'
                      : session.config.engine_mode === 'keysight_gcm'
                        ? 'GCM'
                        : 'External ASC'
                  }
                </Badge>
              )}
            </Group>
          </Group>

          {frozenCmwApproval && (
            <Alert color={frozenCmwApprovalDrift ? 'yellow' : 'blue'} variant="light">
              本次执行冻结的 CMW500 LTE 2×2 正式能力：
              {frozenCmwApproval.enabled ? '已启用' : '未启用'}
              {frozenCmwApproval.updated_at
                ? ` · 授权时间 ${frozenCmwApproval.updated_at}`
                : ''}
              {frozenCmwApprovalDrift ? `。${frozenCmwApprovalDrift}` : ''}
            </Alert>
          )}
          {session?.execution_qualification && (
            <Alert color={session.execution_qualification.classification === 'formal' ? 'green' : 'yellow'} variant="light">
              本次执行冻结资格：{session.execution_qualification.classification === 'formal'
                ? 'Formal（正式）'
                : 'Diagnostic（仅可诊断）'}
              {session.execution_qualification.reasons.length > 0
                ? ` · ${session.execution_qualification.reasons.join(', ')}`
                : ''}
            </Alert>
          )}

          <Divider my="sm" />
          <Switch
            checked={diagnosticMode}
            onChange={(e) => setDiagnosticMode(e.currentTarget.checked)}
            label="Diagnostic（仅可诊断）"
            description="切换后重置会话；本次冻结结果以黄色展示，后续认证变化只影响下一次执行。"
          />
          <Switch
            checked={labSmoke}
            onChange={(e) => setLabSmoke(e.currentTarget.checked)}
            label="强制跳过严格 DUT / 校准门（real 模式 override）"
            description="mock 模式已自动跳过严格门，无需开此开关。仅真实仪表 + 无 DUT/校准空跑时才需要；切换后点「重置会话」生效。默认关闭以保留 fail-loud 保护。"
          />
          {(diagnosticMode || labSmoke) && (
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput required label="操作人" value={diagnosticOperator} onChange={(e) => setDiagnosticOperator(e.currentTarget.value)} />
              <TextInput required label="诊断原因" value={diagnosticReason} onChange={(e) => setDiagnosticReason(e.currentTarget.value)} />
            </SimpleGrid>
          )}

          <Divider my={4} />
          <Group justify="space-between" align="center">
            <div>
              <Text size="sm" fw={500}>设备自检（首测前）</Text>
              <Text size="xs" c="dimmed">
                先单独验各仪表连接 + 响应, 不在首测中途撞设备问题（借鉴转台/EMCenter standalone 验证）
              </Text>
            </div>
            <Button
              size="xs"
              variant="light"
              loading={selfcheckLoading}
              onClick={async () => {
                const releaseWork = beginWork('commissioning', '设备自检正在驱动硬件')
                setSelfcheckLoading(true)
                try {
                  const res = await api.deviceSelfcheck()
                  setSelfcheck(res.data)
                } catch {
                  setSelfcheck(null)
                } finally {
                  releaseWork()
                  setSelfcheckLoading(false)
                }
              }}
            >
              运行设备自检
            </Button>
          </Group>
          {selfcheck && (
            <Alert color={selfcheck.all_ready ? 'green' : 'orange'} variant="light">
              <Text size="sm" fw={500} mb={4}>
                {selfcheck.message}
              </Text>
              <Stack gap={2}>
                {selfcheck.devices.map((d) => (
                  <Group key={d.category} gap="xs">
                    <Badge
                      color={d.connected && d.responsive ? 'green' : 'red'}
                      variant="light"
                      size="sm"
                    >
                      {d.connected && d.responsive ? '✓' : '✗'} {d.category}
                    </Badge>
                    {d.detail && (
                      <Text size="xs" c="dimmed">
                        {d.detail}
                      </Text>
                    )}
                  </Group>
                ))}
              </Stack>
            </Alert>
          )}

          <Divider my={4} />
          {/* DUT 身份元数据登记（可选）。正式连接由 MEASURE 在按 TestCase
              初始化后自动确认。⚠ session.session_id **就是** execution_id。 */}
          <div>
            <Text size="sm" fw={500}>DUT 身份登记（可选）</Text>
            <Text size="xs" c="dimmed" mb="xs">
              可提前登记 IMSI 和型号用于防插错卡及报告追溯；此处读取的当前 UE 状态
              只作参考。<strong>正式连接由执行器在按 TestCase 初始化后确认</strong>，
              不依赖仪表上一轮遗留状态。
            </Text>
            <Group align="flex-end" gap="xs">
              <TextInput
                label="IMSI"
                placeholder="460xxxxxxxxxxxx"
                value={dutImsi}
                onChange={(e) => setDutImsi(e.currentTarget.value)}
                style={{ flex: 1 }}
                size="xs"
              />
              <TextInput
                label="DUT 型号（选填）"
                placeholder="例: Xiaomi 15"
                value={dutModel}
                onChange={(e) => setDutModel(e.currentTarget.value)}
                style={{ flex: 1 }}
                size="xs"
              />
              <Button
                size="xs"
                variant="light"
                loading={attachLoading}
                disabled={!dutImsi.trim()}
                onClick={async () => {
                  const releaseWork = beginWork('commissioning', 'DUT 登记正在读写 UXM')
                  setAttachLoading(true)
                  setAttachError(null)
                  try {
                    // session_id === execution_id, 见上方注释
                    const res = await api.attachDut(session.session_id, {
                      imsi: dutImsi.trim(),
                      dut_model: dutModel.trim() || null,
                    })
                    setAttachResult(res.data)
                  } catch (e: unknown) {
                    setAttachResult(null)
                    const detail =
                      (e as { response?: { data?: { detail?: string } } })?.response
                        ?.data?.detail
                    setAttachError(detail || (e as Error)?.message || '登记失败')
                  } finally {
                    releaseWork()
                    setAttachLoading(false)
                  }
                }}
              >
                登记 DUT
              </Button>
            </Group>
          </div>
          {attachError && (
            <Alert color="red" variant="light" mt="xs" title="登记失败">
              <Text size="sm">{attachError}</Text>
            </Alert>
          )}
          {attachResult && (
            /* ⚠ 颜色跟 rrc_connected 走, **不跟 success 走** —— 接口查不到 UE
               也会返回 success=true 并把原因塞进 warnings。拿 success 上色
               会让"记录写下了"看起来像"DUT 已就位", 那正是严格门要防的事。 */
            <Alert
              color={attachResult.rrc_connected ? 'green' : 'orange'}
              variant="light"
              mt="xs"
              title={
                attachResult.rrc_connected
                  ? '身份已登记；当前 UE 在线（仅供参考）'
                  : '身份已登记；当前 UE 未在线（正式流程会在初始化后重试）'
              }
            >
              <Group gap="xs" mb={4}>
                <Badge size="sm" variant="light" color="gray">
                  IMSI {attachResult.dut_imsi}
                </Badge>
                <Badge
                  size="sm"
                  variant="light"
                  color={attachResult.rrc_connected ? 'green' : 'orange'}
                >
                  rrc_connected={String(attachResult.rrc_connected)}
                </Badge>
              </Group>
              {attachResult.warnings.length > 0 && (
                <Stack gap={2}>
                  {attachResult.warnings.map((w, i) => (
                    <Text key={i} size="xs" c="dimmed">
                      · {w}
                    </Text>
                  ))}
                </Stack>
              )}
              {!attachResult.rrc_connected && (
                <Text size="xs" c="dimmed" mt={4}>
                  这不会让 PRECHECK 因“缺少登记”失败；MEASURE 会先配置本次
                  UXM/F64/开关状态，再等待并核对 CONN，失败才停止正式测量。
                </Text>
              )}
            </Alert>
          )}

          {/* External ASC 路径输入 (post-session). 当操作员在已有会话里把引擎切到
              external_asc 时, 需要在这里填 .asc 目录路径再「重置会话」—— 否则
              createSession 会因缺 asc_source_path 被后端 422。会话创建后路径锁进
              session.config (下方只读 Alert 显示). 早期 (PR #56) 这里没有可编辑
              输入是因为假定 external_asc 只在 pre-session 选; 但带 saved-lab 的
              操作员一进页面就 auto-fire 默认会话, 落到 post-session, 切 external_asc
              便无处填。 */}
          {engineMode === 'external_asc' && (
            <TextInput
              mt="sm"
              label="ASC 目录绝对路径"
              description="本机存放 channel_InX_OutY.asc 的目录 (ChannelEgine app.py 产出); 填好后点下方「重置会话」以 external_asc 重建会话"
              placeholder="/Users/yourname/asc_outputs/2026-05-19"
              value={ascSourcePath}
              onChange={(e) => setAscSourcePath(e.currentTarget.value)}
              error={
                session?.config?.engine_mode !== 'external_asc' && !ascSourcePath.trim()
                  ? '需填路径并「重置会话」才会生效'
                  : undefined
              }
            />
          )}

          {session?.config?.engine_mode === 'external_asc' &&
            typeof session?.config?.asc_source_path === 'string' &&
            session.config.asc_source_path.length > 0 && (
              <Alert color="gray" mt="md" title="当前会话锁定的 ASC 路径">
                <Text size="sm" ff="monospace">
                  {session.config.asc_source_path}
                </Text>
              </Alert>
            )}
        </Paper>

        {/* Stepper */}
        <Paper withBorder p="xl" radius="md">
          <Stepper active={activeStep} onStepClick={setActiveStep}>
            {PHASE_STEPS.map((step, idx) => {
              const status = session.phase_statuses[step.id]
              const hasError = status === 'failed'
              return (
                <Stepper.Step 
                  key={step.id} 
                  label={step.label} 
                  description={step.desc}
                  color={hasError ? 'red' : undefined}
                >
                  <Stack gap="xl" mt="xl">
                    <Text size="xl" fw={500}>阶段 {idx + 1}: {step.label}</Text>
                    
                    {/* Render Phase Content */}
                    {step.id === 'precheck' && <PrecheckPhase data={session.precheck} />}
                    {step.id === 'reference' && 
                      <ReferencePhase 
                        data={session.reference} 
                        status={session.phase_statuses['reference']} 
                        onConfirm={() => handleRunPhase('reference')}
                      />
                    }
                    {step.id === 'mimo_test' && <MIMOTestPhase data={session.mimo_test} config={session.config} />}
                    {step.id === 'analysis' && <AnalysisPhase data={session.analysis} />}
                    {step.id === 'report' && <ReportPhase data={session} />}

                    {/* Controls */}
                    <Divider />
                    <Group justify="right">
                      {step.id === 'reference' && status === 'waiting' ? (
                        <Text c="dimmed" size="sm">请确认天线安装后继续</Text>
                      ) : (
                        <Button 
                          loading={loading}
                          onClick={() => handleRunPhase(step.id === 'reference' ? 'reference_wait' : step.id)}
                          leftSection={<IconPlayerPlay size={16} />}
                          disabled={status === 'completed'}
                        >
                          {status === 'completed' ? '重新执行' : '执行此阶段'}
                        </Button>
                      )}
                      {(status === 'completed' || step.id === 'report') && idx < 4 && (
                        <Button 
                          variant="light" 
                          rightSection={<IconPlayerTrackNext size={16} />}
                          onClick={() => setActiveStep(idx + 1)}
                        >
                          下一步
                        </Button>
                      )}
                    </Group>
                  </Stack>
                </Stepper.Step>
              )
            })}
            
            <Stepper.Completed>
              <Stack gap="md" align="center" mt="xl" py="xl">
                <IconTestPipe size={48} color="teal" />
                <Title order={3}>首测全流程已完成</Title>
                <Text c="dimmed">测试数据已生成。您可以点击上方各个步骤的圆圈，查看详尽的测量数据、MIMO 吞吐量表格及分析结论。</Text>
                <Text fw={500}>Session: {session.session_id}</Text>
                <Group>
                  <Button variant="light" onClick={() => setActiveStep(2)}>查看 MIMO 吞吐量表格</Button>
                  <Button variant="light" color="grape" onClick={() => setActiveStep(3)}>查看 CTIA 分析结果</Button>
                </Group>
                <Button variant="outline" onClick={initSession} mt="md">开启新会话</Button>
              </Stack>
            </Stepper.Completed>
          </Stepper>
        </Paper>
        
        {/* Debug Controls */}
        <Group justify="space-between">
          <Group gap="xs">
          <Button
            variant="light"
            color="gray"
            onClick={initSession}
            loading={loading}
            disabled={engineMode === 'external_asc' && !ascSourcePath.trim()}
          >
            重置会话
          </Button>
          {/* 外审 R1：guard 要求「结束会话」，就必须真有这个出口 ——
              「重置会话」是立即重建（session 永不为 null），guard 永远解不开，
              操作员只能离开页面才能切 LabProfile。结束 = 回到会话前表单。 */}
          <Button
            variant="subtle"
            color="red"
            onClick={() => {
              setSession(null)
              setActiveStep(0)
              // 内审 F2：会话级展示状态一并清掉 —— 否则下一个 lab 的新会话
              // 会直接顶着上一个会话的 DUT 登记/自检结论
              setAttachResult(null)
              setAttachError(null)
              setSelfcheck(null)
            }}
            disabled={hardwareBusy}
            title={hardwareBusy ? '有请求仍在驱动硬件 —— 等它结束再退出会话' : undefined}
          >
            结束会话
          </Button>
          </Group>
          <Button variant="light" color="grape" onClick={handleRunAll} disabled={hardwareBusy}>一键执行全流程(Mock)</Button>
        </Group>

      </Stack>
    </Container>
  )
}
