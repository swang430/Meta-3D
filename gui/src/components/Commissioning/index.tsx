import { useState, useEffect } from 'react'
import { Container, Title, Text, Stepper, Group, Button, Paper, Stack, Divider, Loader, Select, Badge, Alert, TextInput, Switch, NumberInput, SimpleGrid } from '@mantine/core'
import { IconTestPipe, IconPlayerPlay, IconPlayerTrackNext, IconAlertTriangle } from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import { PrecheckPhase, ReferencePhase, MIMOTestPhase, AnalysisPhase, ReportPhase } from './Phases'
import * as api from './api'
import type { SessionResponse, LabResolutionDetail } from './api'
import { fetchLabProfiles, type LabProfileSummary } from '../../api/labProfileService'
import { fetchChannelAssets, type ChannelAsset } from '../../api/channelAssetService'

// Remember the operator's last commissioning-lab choice so the next
// session-create defaults to it. Per-browser; not per-user (no auth
// context in this app yet). Same namespace pattern as the P1-1
// preflight modal's `mimo.preflight.lastLabId`.
const LAST_LAB_LS_KEY = 'mimo.commissioning.lastLabId'

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
  // ⚠ 必须跟后端 `CreateSessionRequest.engine_mode` / `MIMOOTAConfiguration.engine_mode`
  //   保持一致（三处同步）。2026-08-07 现场一度三处都改成 'keysight_gcm'，
  //   2026-08-08 后端两处撤回 'mimo_first_asc' 时**漏了这里**（Antigravity 异源审查
  //   Finding 1 抓出）：GCM 路必须配 .smu，而 emulation_file 已撤回成 None ——
  //   GUI 默认建的会话会被 emulation_file 严格门在 precheck/measure 阶段拒掉。
  //   现场要走 GCM 时在界面上显式选，别靠默认值。
  const [engineMode, setEngineMode] = useState<string>('mimo_first_asc')
  // RF 冷启动工作点：2026-08-07 现场已验证的基线。它们不是共享 schema
  // 默认，而是本次 session 的显式输入；创建后会固定进 execution.config。
  const [frequencyMhz, setFrequencyMhz] = useState(3549.99)
  const [bandwidthMhz, setBandwidthMhz] = useState(40)
  const [uxmPowerDbmPerBw, setUxmPowerDbmPerBw] = useState(-15)
  const [f64InputRefDbm, setF64InputRefDbm] = useState(-17)
  const [f64CrestDb, setF64CrestDb] = useState(15)
  const [f64OutputLevelDbm, setF64OutputLevelDbm] = useState(-52)
  const [f64BypassAssist, setF64BypassAssist] = useState(true)
  const [emulationFile, setEmulationFile] = useState('')
  const [channelAssetId, setChannelAssetId] = useState<string | null>(null)
  const [channelAssets, setChannelAssets] = useState<ChannelAsset[]>([])
  // Lab-smoke: relax strict precheck gates (P1-8 cal / P1-9 DUT) for local
  // rehearsal without a real DUT / calibration. Default OFF = strict ON, so
  // on-site real first-call keeps the fail-loud protection (P1-9 intent).
  const [labSmoke, setLabSmoke] = useState(false)
  // 2026-08-07 现场: 只放过校准证书那一道门。跟 labSmoke 分开是因为 labSmoke
  // 一开就废掉全部 8 道 —— 为了绕开"证书未绑"而开它, 会把 DUT 门也一起废掉,
  // 「登记 DUT」按钮就白点了。校准没做完 vs DUT 能不能 attach 是两件事。
  const [calBypass, setCalBypass] = useState(false)
  // U-5: 暗室首测前逐设备自检 (借鉴转台/EMCenter standalone 验证, 首测前先单独验各仪表通)
  const [selfcheck, setSelfcheck] = useState<api.DeviceSelfcheckResult | null>(null)
  const [selfcheckLoading, setSelfcheckLoading] = useState(false)
  // DUT attach 登记 —— 严格门要的那条记录, 在此之前 GUI 无入口 (只有 Phases.tsx
  // 一段"自己去 POST"的提示文字)。2026-08-07 现场实证: precheck 死在
  // "DUT attach record missing", 操作员只能手敲 curl。
  const [dutImsi, setDutImsi] = useState<string>('')
  const [dutModel, setDutModel] = useState<string>('')
  const [attachResult, setAttachResult] = useState<api.AttachDutResponse | null>(null)
  const [attachError, setAttachError] = useState<string | null>(null)
  const [attachLoading, setAttachLoading] = useState(false)
  // 2026-05-18 P0-7: only meaningful when engineMode==='external_asc'.
  // Operator-supplied absolute path of a local directory of channel_InX_OutY.asc
  // files (typically produced by ChannelEgine app.py Streamlit on the same host).
  const [ascSourcePath, setAscSourcePath] = useState<string>('')

  // Lab-resolution state — see api.ts LabResolutionDetail.
  // `labId` is the currently selected lab (sent on session create);
  // `pickerLabs` holds the candidate list when backend returns 422
  // kind="ambiguous", so the operator can pick without leaving the page;
  // `noActiveLab` flips true on kind="none" so we route the operator
  // to the LabProfile wizard instead of looping init forever.
  const [labId, setLabId] = useState<string | null>(
    () => localStorage.getItem(LAST_LAB_LS_KEY),
  )
  const [pickerLabs, setPickerLabs] = useState<Array<{ id: string; name: string }>>([])
  const [noActiveLab, setNoActiveLab] = useState(false)
  const [labChoiceMade, setLabChoiceMade] = useState(false)
  // Bumped on every explicit retry attempt (button click) so the init
  // effect re-fires even when labChoiceMade and labId haven't changed.
  // Without this, a transient failure (500, network blip, explicit lab
  // rejected by backend) would leave the page stuck — labChoiceMade
  // stays true, the button's setLabChoiceMade(true) is a no-op, and
  // the effect's deps don't change so nothing re-runs. Codex P2 on PR #27.
  const [initAttempt, setInitAttempt] = useState(0)

  // Pre-load active labs so the Select can render its options even
  // before a 422 surfaces a candidate list (single-active case still
  // benefits from showing the operator which lab they're targeting).
  useEffect(() => {
    fetchLabProfiles(true)
      .then((labs: LabProfileSummary[]) => {
        setPickerLabs(labs.map((l) => ({ id: l.id, name: l.name })))
        if (labs.length === 0) {
          setNoActiveLab(true)
        }
        // Drop a stale localStorage selection if the lab is no longer active.
        if (labId && !labs.some((l) => l.id === labId)) {
          setLabId(null)
        }
      })
      .catch(() => {
        // Lab fetch failure is non-fatal — the create call will still
        // surface the right error if needed.
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
    try {
      setLoading(true)
      const res = await api.createSession({
        engineMode,
        labProfileId: labId || undefined,
        ascSourcePath: engineMode === 'external_asc' ? ascSourcePath : undefined,
        channelAssetId: channelAssetId || undefined,
        frequencyHz: frequencyMhz * 1e6,
        bandwidthMhz,
        uxmDlPowerDbmPerBw: uxmPowerDbmPerBw,
        f64InputRefDbm,
        f64CrestDb,
        f64OutputLevelDbm,
        emulationFile: emulationFile.trim() || undefined,
        f64BypassMode: f64BypassAssist ? 2 : undefined,
        labSmoke,
        calBypass,
      })
      setSession(res.data)
      setActiveStep(0)
      setPickerLabs([])
      setNoActiveLab(false)
      if (labId) {
        localStorage.setItem(LAST_LAB_LS_KEY, labId)
      }
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
          setPickerLabs(lrd.active_labs)
          setNoActiveLab(false)
          notifications.show({
            title: '请选择 LabProfile',
            message: `当前 DB 有 ${lrd.active_labs.length} 个活动 LabProfile，请选定一个再继续`,
            color: 'yellow',
          })
        } else if (lrd.kind === 'none') {
          setNoActiveLab(true)
          setPickerLabs([])
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
      setLoading(false)
    }
  }

  useEffect(() => {
    // RF 工作点现在是会话创建前的必审输入，因此不再因“已有默认 lab / 切换
    // engine”自动创建。只有操作员点击「启动首测会话」使 initAttempt 递增才执行。
    if (initAttempt === 0) return
    if (!labChoiceMade && !labId) return
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

  const handleLabSelect = (value: string | null) => {
    setLabId(value)
    setLabChoiceMade(true)
  }

  const handleRunPhase = async (phaseId: string) => {
    if (!session) return
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
      setLoading(false)
    }
  }

  const handleRunAll = async () => {
    if (!session) return
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

          {!noActiveLab && pickerLabs.length > 1 && !labChoiceMade && (
            <Alert color="yellow" icon={<IconAlertTriangle size={18} />} title="请选择 LabProfile">
              当前 DB 有 {pickerLabs.length} 个活动 LabProfile —— 后端无法自动判定本次首测对应哪一个，请显式选择。
            </Alert>
          )}

          <Paper withBorder p="md" radius="md">
            <Stack gap="md">
              <Group align="flex-end">
                <Select
                  label="LabProfile"
                  description="本次首测会话绑定到这个 lab；默认取上次选择"
                  placeholder="选择 LabProfile..."
                  data={pickerLabs.map((l) => ({ value: l.id, label: l.name }))}
                  value={labId}
                  onChange={handleLabSelect}
                  disabled={pickerLabs.length === 0}
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
                    (!labId && pickerLabs.length !== 1) ||
                    // 2026-05-18 P0-7: external_asc 必须给路径才能启动会话
                    (engineMode === 'external_asc' && !ascSourcePath.trim()) ||
                    // GCM 冷启动必须能解析本次 .smu；不能再借用 F64 遗留场景。
                    (engineMode === 'keysight_gcm' && !channelAssetId && !emulationFile.trim()) ||
                    !Number.isFinite(frequencyMhz) || frequencyMhz <= 0 ||
                    !Number.isFinite(bandwidthMhz) || bandwidthMhz <= 0
                  }
                  onClick={() => {
                    // If exactly one lab and operator hasn't picked, auto-fill.
                    if (!labId && pickerLabs.length === 1) {
                      setLabId(pickerLabs[0].id)
                    }
                    setLabChoiceMade(true)
                    // Bump the attempt counter so the init effect re-fires
                    // even when labChoiceMade is already true and labId hasn't
                    // changed — i.e., retry after a transient failure on the
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
                  const multiSnapshotRt =
                    asset.source_type === 'rt_dynamic' &&
                    Array.isArray((asset.payload as { snapshots?: unknown[] }).snapshots) &&
                    ((asset.payload as { snapshots?: unknown[] }).snapshots?.length ?? 0) > 1
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
                  if (asset?.center_frequency_hz != null) {
                    setFrequencyMhz(asset.center_frequency_hz / 1e6)
                  }
                  if (asset?.bandwidth_mhz != null) {
                    setBandwidthMhz(asset.bandwidth_mhz)
                  }
                }}
              />

              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
                <NumberInput
                  label="中心频率 (MHz)"
                  value={frequencyMhz}
                  decimalScale={3}
                  onChange={(value) => setFrequencyMhz(Number(value))}
                  min={1}
                />
                <NumberInput
                  label="UXM 带宽 (MHz)"
                  value={bandwidthMhz}
                  onChange={(value) => setBandwidthMhz(Number(value))}
                  min={1}
                />
                <NumberInput
                  label="UXM 整带宽功率 (dBm)"
                  value={uxmPowerDbmPerBw}
                  onChange={(value) => setUxmPowerDbmPerBw(Number(value))}
                  decimalScale={1}
                />
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
                checked={calBypass}
                onChange={(e) => setCalBypass(e.currentTarget.checked)}
                label="只跳过校准证书门（其余 7 道照常守着）"
                description="lab 未绑校准证书（P0-3 未做完）但 DUT 能真 attach 时用这个 —— DUT 门 / 频率门 / .smu 门等仍然生效。别为了绕证书去开下面那个总开关，那会把 DUT 门一起废掉。"
              />
              <Switch
                checked={labSmoke}
                onChange={(e) => setLabSmoke(e.currentTarget.checked)}
                label="强制跳过严格 DUT / 校准门（real 模式 override）"
                description="mock 模式（无真实仪表）已自动跳过严格门，无需开此开关。仅当你接了真实仪表、但想在没有 DUT / 校准的情况下空跑预检时才打开。默认关闭，以保留 P1-8/P1-9 fail-loud 保护。"
              />
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
              <Select
                label="LabProfile"
                description="切换需重置会话"
                data={pickerLabs.map((l) => ({ value: l.id, label: l.name }))}
                value={labId}
                onChange={(v) => {
                  setLabId(v)
                  if (v) localStorage.setItem(LAST_LAB_LS_KEY, v)
                }}
                disabled={pickerLabs.length === 0}
                w={260}
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

          <Divider my="sm" />
          <Switch
            checked={calBypass}
            onChange={(e) => setCalBypass(e.currentTarget.checked)}
            label="只跳过校准证书门（其余 7 道照常守着）"
            description="lab 未绑校准证书（P0-3 未做完）但 DUT 能真 attach 时用这个 —— DUT 门 / 频率门 / .smu 门等仍然生效。切换后点「重置会话」生效。别为了绕证书去开下面那个总开关，那会把 DUT 门一起废掉，「登记 DUT」就白点了。"
          />
          <Switch
            checked={labSmoke}
            onChange={(e) => setLabSmoke(e.currentTarget.checked)}
            label="强制跳过严格 DUT / 校准门（real 模式 override）"
            description="mock 模式已自动跳过严格门，无需开此开关。仅真实仪表 + 无 DUT/校准空跑时才需要；切换后点「重置会话」生效。默认关闭以保留 fail-loud 保护。"
          />

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
                setSelfcheckLoading(true)
                try {
                  const res = await api.deviceSelfcheck()
                  setSelfcheck(res.data)
                } catch {
                  setSelfcheck(null)
                } finally {
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
          {/* DUT attach 登记 —— precheck §5b 严格门要的那条记录。
              ⚠ session.session_id **就是** execution_id (后端
              _execution_to_session_response 写的 session_id=str(execution.id))。 */}
          <div>
            <Text size="sm" fw={500}>DUT attach 登记（严格门必需）</Text>
            <Text size="xs" c="dimmed" mb="xs">
              把 DUT 的 IMSI 登记到本次执行，并<strong>当场向 UXM 查一次 UE 状态</strong>。
              先把手机放进静区、插好 SIM、确认已 attach 到 UXM 再点。
              不登记则真仪表下 precheck 必 FAIL（“DUT attach record missing”）。
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
                  ? '已登记，UE 在线'
                  : '已登记，但 UE 未确认在线 —— 严格门仍会 FAIL'
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
                  严格门要三个条件同时成立：记录存在 + rrc_connected=true +
                  precheck 当下再查 UE 仍在线。只写记录不够。
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
          <Button
            variant="light"
            color="gray"
            onClick={initSession}
            loading={loading}
            disabled={engineMode === 'external_asc' && !ascSourcePath.trim()}
          >
            重置会话
          </Button>
          <Button variant="light" color="grape" onClick={handleRunAll}>一键执行全流程(Mock)</Button>
        </Group>

      </Stack>
    </Container>
  )
}
