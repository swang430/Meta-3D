import { useState, useEffect } from 'react'
import { Container, Title, Text, Stepper, Group, Button, Paper, Stack, Divider, Loader, Select, Badge, Alert, TextInput, Switch } from '@mantine/core'
import { IconTestPipe, IconPlayerPlay, IconPlayerTrackNext, IconAlertTriangle } from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import { PrecheckPhase, ReferencePhase, MIMOTestPhase, AnalysisPhase, ReportPhase } from './Phases'
import * as api from './api'
import type { SessionResponse, LabResolutionDetail } from './api'
import { fetchLabProfiles, type LabProfileSummary } from '../../api/labProfileService'

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

export function CommissioningSandbox() {
  const [session, setSession] = useState<SessionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  const [engineMode, setEngineMode] = useState<string>('mimo_first_asc')
  // Lab-smoke: relax strict precheck gates (P1-8 cal / P1-9 DUT) for local
  // rehearsal without a real DUT / calibration. Default OFF = strict ON, so
  // on-site real first-call keeps the fail-loud protection (P1-9 intent).
  const [labSmoke, setLabSmoke] = useState(false)
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

  // Initialization
  const initSession = async () => {
    try {
      setLoading(true)
      const res = await api.createSession(
        engineMode,
        labId || undefined,
        engineMode === 'external_asc' ? ascSourcePath : undefined,
        labSmoke,
      )
      setSession(res.data)
      setActiveStep(0)
      setPickerLabs([])
      setNoActiveLab(false)
      if (labId) {
        localStorage.setItem(LAST_LAB_LS_KEY, labId)
      }
      notifications.show({ title: '首测会话已创建', message: `ID: ${res.data.session_id}`, color: 'blue' })
    } catch (err: any) {
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
      const msg = typeof detail === 'string' ? detail : err.message
      notifications.show({ title: '初始化失败', message: String(msg), color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // Wait until the operator either has a saved/default lab or has
    // explicitly chosen one — otherwise re-entering the page would
    // immediately fire init with no lab and bounce to the 422 picker
    // before the lab list has even loaded.
    if (!labChoiceMade && !labId) return
    // external_asc 必须先有 ASC 路径才能建会话 (后端校验)。engineMode 在 deps 里,
    // 切到 external_asc 会触发本 effect; 若此时路径还没填, 不要 auto-fire 一个注定
    // 422 的 createSession。等操作员填好路径点「启动」(bump initAttempt) 再建。
    if (engineMode === 'external_asc' && !ascSourcePath.trim()) return
    initSession()
    // labId in deps so that switching labs after a failed create
    // re-fires init. initAttempt in deps so that re-clicking the
    // "启动首测会话" button (same lab) is a valid retry path.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engineMode, labChoiceMade, labId, initAttempt])

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
    } catch (err: any) {
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
    } catch (err: any) {
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
                  onChange={(val) => val && setEngineMode(val)}
                  w={360}
                />
                <Button
                  loading={loading}
                  disabled={
                    (!labId && pickerLabs.length !== 1) ||
                    // 2026-05-18 P0-7: external_asc 必须给路径才能启动会话
                    (engineMode === 'external_asc' && !ascSourcePath.trim())
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
                checked={labSmoke}
                onChange={(e) => setLabSmoke(e.currentTarget.checked)}
                label="Lab smoke（本地彩排，跳过严格 DUT / 校准门）"
                description="打开后本次会话以 precheck_strict_dut=False + precheck_strict_cal=False 创建，无需真实 DUT / 校准即可走完预检。现场真测请保持关闭（默认），以保留 P1-8/P1-9 fail-loud 保护。"
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
              {session?.config?.engine_mode && (
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
            checked={labSmoke}
            onChange={(e) => setLabSmoke(e.currentTarget.checked)}
            label="Lab smoke（本地彩排，跳过严格 DUT / 校准门）"
            description="切换后点「重置会话」生效。打开则以 precheck_strict_dut/cal=False 重建会话，本地无 DUT / 校准也能过预检；现场真测请关闭以保留 fail-loud 保护。"
          />

          {/* 2026-05-18 P0-7: External ASC 模式的路径输入在 pre-session UI
              (L260+) 里, 这一块是 post-session, 只显示 read-only 锁定路径.
              Codex P2 on PR #56 — 早期版本在这里放 TextInput 但 !session 永远
              false (component 在 L187 已经按 !session 提前 return), 不可达. */}
          {session?.config?.engine_mode === 'external_asc' &&
            session?.config?.asc_source_path && (
              <Alert color="gray" mt="md" title="External ASC 锁定路径">
                <Text size="sm" ff="monospace">
                  {session.config.asc_source_path as string}
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
          <Button variant="light" color="gray" onClick={initSession}>重置会话</Button>
          <Button variant="light" color="grape" onClick={handleRunAll}>一键执行全流程(Mock)</Button>
        </Group>

      </Stack>
    </Container>
  )
}
