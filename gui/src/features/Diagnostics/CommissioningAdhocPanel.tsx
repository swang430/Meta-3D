/**
 * P3 Phase 3: ad-hoc single-phase commissioning + HAL trace tail.
 *
 * Lets operators run ONE MIMO_OTA executor (precheck / reference / measure /
 * analysis / report) against a synthetic session — useful when the formal
 * 5-phase flow stalls and you want to bisect which phase is actually broken.
 *
 * Right-side panel tails logs/measurement.log so SCPI traffic shows up in the
 * same window. Beats ssh+tail; refresh button fetches the latest 200 lines.
 *
 * Tagged 'diagnostic_ad_hoc' on the backend so it doesn't pollute the
 * regular commissioning sessions list.
 */
import { useEffect, useMemo, useState } from 'react'
import { useOperationalLab } from '../OperationalLab'
import {
  Stack,
  Paper,
  Title,
  Text,
  Select,
  TextInput,
  Textarea,
  Button,
  Group,
  Alert,
  Badge,
  Code,
  Loader,
  Center,
  Divider,
  ScrollArea,
} from '@mantine/core'
import {
  IconAlertCircle,
  IconAlertTriangle,
  IconCheck,
  IconPlayerPlay,
  IconRefresh,
  IconTerminal2,
  IconX,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'

import {
} from '../../api/labProfileService'
import {
  fetchHALTraceTail,
  runAdhocPhase,
  type AdhocPhaseResponse,
  type CommissioningPhaseName,
  type HALTraceTailResponse,
} from '../../api/diagnosticService'
import { logFrontendEvent } from '../../observability/frontendLogger'

const PHASE_OPTIONS: Array<{ value: CommissioningPhaseName; label: string; description: string }> = [
  { value: 'precheck', label: 'precheck', description: '校验 lab + 仪表 + 校准证书有效期' },
  { value: 'reference', label: 'reference', description: '参考站位 / 信号源校准设置' },
  { value: 'mimo_test', label: 'mimo_test (measure)', description: '转台 + 信道仿真 + 吞吐量测量' },
  { value: 'analysis', label: 'analysis', description: 'KPI 计算 + pass/fail' },
  { value: 'report', label: 'report', description: '生成 PDF 报告 (调试一般跳过)' },
]

// Common phase_override hints — surfaced as a JSON template the operator
// can paste over instead of remembering the keys. Not a complete schema;
// the executor reads context.parameters at runtime so unknown keys are
// silently ignored, which is exactly what we want for a debug tool.
const PHASE_OVERRIDE_TEMPLATES: Record<CommissioningPhaseName, string> = {
  precheck: JSON.stringify(
    { skip_calibration_age_check: true, skip_dut_attach_check: true },
    null, 2,
  ),
  reference: '{}',
  mimo_test: JSON.stringify(
    { num_samples_per_azimuth: 1, settling_time_s: 0.5 },
    null, 2,
  ),
  analysis: '{}',
  report: '{}',
}

export function CommissioningAdhocPanel() {
  // P1-57：LabProfile 由全局上下文提供，本面板只读（header 唯一选择器）。
  const { selectedLabProfileId, selectedLabProfile, chamberName, loading: labsLoading } = useOperationalLab()
  const selectedLabId = selectedLabProfileId ?? ''

  const [phase, setPhase] = useState<CommissioningPhaseName>('precheck')
  const [phaseOverridesText, setPhaseOverridesText] = useState<string>(
    PHASE_OVERRIDE_TEMPLATES['precheck'],
  )
  const [overridesError, setOverridesError] = useState<string | null>(null)
  const [runBy, setRunBy] = useState<string>('')

  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AdhocPhaseResponse | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const [trace, setTrace] = useState<HALTraceTailResponse | null>(null)
  const [traceLoading, setTraceLoading] = useState(false)

  useEffect(() => {
    setPhaseOverridesText(PHASE_OVERRIDE_TEMPLATES[phase])
    setOverridesError(null)
  }, [phase])

  const parsedOverrides = useMemo(() => {
    if (!phaseOverridesText.trim()) return {}
    try {
      const v = JSON.parse(phaseOverridesText)
      if (typeof v !== 'object' || v === null || Array.isArray(v)) {
        throw new Error('phase_overrides 必须是 JSON 对象')
      }
      return v as Record<string, unknown>
    } catch (e) {
      throw e
    }
  }, [phaseOverridesText])

  const handleOverridesChange = (text: string) => {
    setPhaseOverridesText(text)
    if (!text.trim()) {
      setOverridesError(null)
      return
    }
    try {
      const v = JSON.parse(text)
      if (typeof v !== 'object' || v === null || Array.isArray(v)) {
        setOverridesError('phase_overrides 必须是 JSON 对象')
      } else {
        setOverridesError(null)
      }
    } catch (e) {
      setOverridesError(`JSON 错误: ${(e as Error).message}`)
    }
  }

  const refreshTrace = () => {
    setTraceLoading(true)
    fetchHALTraceTail(200)
      .then(setTrace)
      .catch(() => {
        /* file may not exist yet — silent */
      })
      .finally(() => setTraceLoading(false))
  }

  const handleRun = async () => {
    if (overridesError) return
    setRunning(true)
    setRunError(null)
    setResult(null)
    try {
      const overrides = phaseOverridesText.trim() ? parsedOverrides : {}
      const resp = await runAdhocPhase({
        lab_profile_id: selectedLabId || undefined,
        phase_name: phase,
        phase_overrides: overrides,
        run_by: runBy || undefined,
      })
      setResult(resp)
      notifications.show({
        title: resp.status === 'success' ? '阶段执行成功' : `阶段 ${resp.status}`,
        message: resp.error_message || `${resp.phase} (${resp.duration_ms} ms)`,
        color: resp.status === 'success' ? 'green' : 'orange',
        icon: resp.status === 'success' ? <IconCheck size={18} /> : <IconAlertTriangle size={18} />,
      })
      logFrontendEvent({
        action: 'commissioning.adhoc_phase.run',
        component: 'CommissioningAdhocPanel',
        message: `phase=${resp.phase} status=${resp.status} duration=${resp.duration_ms}ms`,
      })
      // Auto-refresh trace after run so the SCPI lines from this phase show.
      refreshTrace()
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e as Error)?.message ||
        '执行失败'
      setRunError(typeof detail === 'string' ? detail : JSON.stringify(detail))
      notifications.show({
        title: '执行失败',
        message: typeof detail === 'string' ? detail : JSON.stringify(detail),
        color: 'red',
        icon: <IconX size={18} />,
      })
    } finally {
      setRunning(false)
    }
  }

  return (
    <Stack gap="md">
      <Paper p="md" withBorder>
        <Stack gap="xs">
          <Group gap="xs">
            <Title order={4}>Commissioning 单阶段 ad-hoc</Title>
            <Badge color="orange" variant="light" size="sm">workshop tier</Badge>
          </Group>
          <Text size="sm" c="dimmed">
            跑单个 MIMO_OTA executor (而非 5 阶段全跑通) 用来定位"哪一步坏了"。
            phase_overrides 让你跳过已知失效但无关本次调试的检查 (例如校准过期但
            当前只想验 measure 路径). 运行结果记入 diagnostic_runs 审计表 + 创建
            tagged 'diagnostic_ad_hoc' 的 TestExecution; 不进正规 commissioning
            session 列表, 不出 cert.
          </Text>
        </Stack>
      </Paper>

      <Group align="flex-start" gap="md" grow>
        {/* Left: form */}
        <Paper p="md" withBorder>
          <Stack gap="md">
            <Group grow>
              {labsLoading ? (
                <Group gap="xs"><Loader size="xs" /><Text size="sm" c="dimmed">加载...</Text></Group>
              ) : (
                <TextInput
                  label="LabProfile"
                  description="来自顶部全局选择器"
                  value={selectedLabProfile
                    ? (chamberName ? `${selectedLabProfile.name} — ${chamberName}` : selectedLabProfile.name)
                    : '未选择'}
                  readOnly
                />
              )}
              <Select
                label="阶段"
                data={PHASE_OPTIONS.map((p) => ({ value: p.value, label: p.label }))}
                value={phase}
                onChange={(v) => v && setPhase(v as CommissioningPhaseName)}
                required
                allowDeselect={false}
              />
            </Group>

            <Text size="xs" c="dimmed">
              {PHASE_OPTIONS.find((p) => p.value === phase)?.description}
            </Text>

            <Textarea
              label="phase_overrides (JSON)"
              description="覆盖该阶段 descriptor.parameters; 未识别的 key 被静默忽略 (debug 友好)"
              value={phaseOverridesText}
              onChange={(e) => handleOverridesChange(e.currentTarget.value)}
              minRows={4}
              autosize
              styles={{ input: { fontFamily: 'monospace', fontSize: 12 } }}
              error={overridesError || undefined}
            />

            <TextInput
              label="操作员"
              placeholder="工号 / 姓名"
              value={runBy}
              onChange={(e) => setRunBy(e.currentTarget.value)}
            />

            <Group justify="flex-end">
              <Button
                leftSection={<IconPlayerPlay size={16} />}
                onClick={handleRun}
                disabled={running || !!overridesError || !selectedLabId}
                loading={running}
              >
                运行阶段
              </Button>
            </Group>
          </Stack>
        </Paper>

        {/* Right: HAL trace tail */}
        <Paper p="md" withBorder>
          <Group justify="space-between" mb="xs">
            <Group gap="xs">
              <IconTerminal2 size={16} />
              <Title order={5}>HAL / SCPI Trace</Title>
              {trace && <Code style={{ fontSize: 10 }}>{trace.log_path}</Code>}
            </Group>
            <Button
              variant="subtle"
              size="xs"
              leftSection={<IconRefresh size={14} />}
              onClick={refreshTrace}
              loading={traceLoading}
            >
              刷新尾部 200 行
            </Button>
          </Group>
          {!trace ? (
            <Center py="xl">
              <Text c="dimmed" size="sm">
                点"刷新"读取 logs/measurement.log 尾部. 调试时让它跟你的 SCPI 流量在一个屏幕。
              </Text>
            </Center>
          ) : trace.lines.length === 0 ? (
            <Text c="dimmed" size="sm">日志文件存在但目前没有内容。</Text>
          ) : (
            <ScrollArea h={360}>
              <Code block style={{ fontSize: 11, whiteSpace: 'pre' }}>
                {trace.lines.join('\n')}
              </Code>
            </ScrollArea>
          )}
        </Paper>
      </Group>

      {/* Result panel */}
      {(result || runError) && (
        <Paper p="md" withBorder>
          {runError ? (
            <Alert color="red" icon={<IconAlertCircle size={18} />} title="执行失败 (HTTP)">
              {runError}
            </Alert>
          ) : result && (
            <Stack gap="sm">
              <Group>
                <Title order={5}>结果</Title>
                <Badge color={result.status === 'success' ? 'green' : 'orange'}>
                  {result.status}
                </Badge>
                <Badge variant="light">{result.duration_ms} ms</Badge>
                <Code>diag={result.diagnostic_run_id.slice(0, 8)}…</Code>
                <Code>exec={result.test_execution_id.slice(0, 8)}…</Code>
              </Group>
              {result.error_message && (
                <Alert color="red" variant="light">
                  {result.error_message}
                </Alert>
              )}
              <Divider label="executor payload" labelPosition="left" />
              <ScrollArea h={Math.min(400, Object.keys(result.result).length * 40 + 60)}>
                <Code block style={{ fontSize: 11 }}>
                  {JSON.stringify(result.result, null, 2)}
                </Code>
              </ScrollArea>
            </Stack>
          )}
        </Paper>
      )}
    </Stack>
  )
}
