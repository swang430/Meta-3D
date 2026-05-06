/**
 * P3 Phase 2: Sequence runner — list + parameterise + execute + show result.
 *
 * Operators picked a sequence (.py file under app/diagnostics/sequences/),
 * pick a LabProfile, fill the metadata-declared params, hit Run. Result
 * panel shows live log + per-step ✓/✗ + summary, plus a Recent Runs feed
 * (last 20 in this kind) so re-running yesterday's diagnostic is one click.
 *
 * Intentionally not a TestPlan replacement — every run lands in
 * diagnostic_runs but never as TestExecution / cert.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Stack,
  Paper,
  Title,
  Text,
  Select,
  TextInput,
  NumberInput,
  Switch,
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
  IconAlertTriangle,
  IconAlertCircle,
  IconCheck,
  IconHistory,
  IconPlayerPlay,
  IconRefresh,
  IconTerminal,
  IconX,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'

import {
  fetchLabProfiles,
  type LabProfileSummary,
} from '../../api/labProfileService'
import {
  listDiagnosticSequences,
  runDiagnosticSequence,
  listDiagnosticRuns,
  type DiagnosticSequenceMetadata,
  type SequenceRunResponse,
  type DiagnosticRunSummary,
} from '../../api/diagnosticService'
import { logFrontendEvent } from '../../observability/frontendLogger'

type ParamValue = number | string | boolean

export function SequenceRunnerPanel() {
  const [labs, setLabs] = useState<LabProfileSummary[]>([])
  const [labsLoading, setLabsLoading] = useState(true)
  const [selectedLabId, setSelectedLabId] = useState<string>('')

  const [sequences, setSequences] = useState<DiagnosticSequenceMetadata[]>([])
  const [seqLoading, setSeqLoading] = useState(true)
  const [selectedKey, setSelectedKey] = useState<string>('')

  // Params form state — keyed by param name, reset when sequence changes.
  const [paramValues, setParamValues] = useState<Record<string, ParamValue>>({})
  const [runBy, setRunBy] = useState<string>('')

  const [running, setRunning] = useState(false)
  const [lastResult, setLastResult] = useState<SequenceRunResponse | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)

  const [recentRuns, setRecentRuns] = useState<DiagnosticRunSummary[]>([])
  const [recentLoading, setRecentLoading] = useState(false)

  const selectedSequence = useMemo(
    () => sequences.find((s) => s.key === selectedKey) || null,
    [sequences, selectedKey],
  )

  // Initial load: labs + sequences in parallel.
  useEffect(() => {
    setLabsLoading(true)
    fetchLabProfiles()
      .then((data) => {
        setLabs(data)
        if (data.length > 0) setSelectedLabId(data[0].id)
      })
      .catch((e: unknown) => {
        notifications.show({
          title: '加载 LabProfile 失败',
          message: (e as Error)?.message || String(e),
          color: 'red',
        })
      })
      .finally(() => setLabsLoading(false))

    setSeqLoading(true)
    listDiagnosticSequences()
      .then((data) => {
        setSequences(data)
        if (data.length > 0) setSelectedKey(data[0].key)
      })
      .catch((e: unknown) => {
        notifications.show({
          title: '加载序列失败',
          message: (e as Error)?.message || String(e),
          color: 'red',
        })
      })
      .finally(() => setSeqLoading(false))
  }, [])

  // Reset param form whenever the selected sequence changes — defaults
  // come from the metadata-declared schema.
  useEffect(() => {
    if (!selectedSequence) {
      setParamValues({})
      return
    }
    const next: Record<string, ParamValue> = {}
    for (const p of selectedSequence.params_schema) {
      if (p.default !== undefined && p.default !== null) {
        next[p.name] = p.default as ParamValue
      } else if (p.type === 'number') {
        next[p.name] = 0
      } else if (p.type === 'boolean') {
        next[p.name] = false
      } else {
        next[p.name] = ''
      }
    }
    setParamValues(next)
  }, [selectedSequence])

  const refreshRecent = () => {
    setRecentLoading(true)
    listDiagnosticRuns({ kind: 'scpi_sequence', limit: 20 })
      .then((res) => setRecentRuns(res.items))
      .catch(() => {
        /* recent list is best-effort; don't notify */
      })
      .finally(() => setRecentLoading(false))
  }

  useEffect(refreshRecent, [])

  const handleRun = async () => {
    if (!selectedKey) return
    setRunning(true)
    setLastError(null)
    setLastResult(null)
    try {
      const resp = await runDiagnosticSequence(selectedKey, {
        lab_profile_id: selectedLabId || undefined,
        params: paramValues,
        run_by: runBy || undefined,
      })
      setLastResult(resp)
      notifications.show({
        title: resp.success ? '序列执行成功' : '序列报告失败',
        message: resp.summary,
        color: resp.success ? 'green' : 'orange',
        icon: resp.success ? <IconCheck size={18} /> : <IconAlertTriangle size={18} />,
      })
      logFrontendEvent({
        action: 'diagnostic_sequence.run',
        component: 'SequenceRunnerPanel',
        message: `key=${selectedKey} success=${resp.success} duration=${resp.duration_ms}ms lab=${selectedLabId || '-'}`,
      })
      refreshRecent()
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e as Error)?.message ||
        '执行失败'
      setLastError(typeof detail === 'string' ? detail : JSON.stringify(detail))
      notifications.show({
        title: '执行失败',
        message: typeof detail === 'string' ? detail : JSON.stringify(detail),
        color: 'red',
        icon: <IconX size={18} />,
      })
      logFrontendEvent({
        level: 'ERROR',
        action: 'diagnostic_sequence.run_failed',
        component: 'SequenceRunnerPanel',
        error: typeof detail === 'string' ? detail : JSON.stringify(detail),
      })
    } finally {
      setRunning(false)
    }
  }

  const renderParamField = (spec: DiagnosticSequenceMetadata['params_schema'][number]) => {
    const value = paramValues[spec.name]
    if (spec.type === 'number') {
      return (
        <NumberInput
          key={spec.name}
          label={spec.label}
          description={`参数: ${spec.name}`}
          value={typeof value === 'number' ? value : 0}
          onChange={(v) => setParamValues((p) => ({ ...p, [spec.name]: Number(v) }))}
        />
      )
    }
    if (spec.type === 'boolean') {
      return (
        <Switch
          key={spec.name}
          label={spec.label}
          description={`参数: ${spec.name}`}
          checked={Boolean(value)}
          onChange={(e) =>
            setParamValues((p) => ({ ...p, [spec.name]: e.currentTarget.checked }))
          }
        />
      )
    }
    return (
      <TextInput
        key={spec.name}
        label={spec.label}
        description={`参数: ${spec.name}`}
        value={typeof value === 'string' ? value : ''}
        onChange={(e) =>
          setParamValues((p) => ({ ...p, [spec.name]: e.currentTarget.value }))
        }
      />
    )
  }

  return (
    <Stack gap="md">
      <Paper p="md" withBorder>
        <Stack gap="xs">
          <Group gap="xs">
            <IconTerminal size={18} />
            <Title order={4}>调试序列 (Sequence Runner)</Title>
            <Badge color="orange" variant="light" size="sm">workshop tier</Badge>
          </Group>
          <Text size="sm" c="dimmed">
            序列代码活在{' '}
            <Code>api-service/app/diagnostics/sequences/</Code>{' '}
            目录下,改完重启就能用. 这里所有运行都记入{' '}
            <Code>diagnostic_runs</Code>{' '}
            审计表 (查"昨天打通的命令")  —  但不进 TestPlan 链路, 不出正式 cert.
          </Text>
        </Stack>
      </Paper>

      <Paper p="md" withBorder>
        <Stack gap="md">
          <Group grow align="flex-end">
            {labsLoading ? (
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="sm" c="dimmed">加载 LabProfile...</Text>
              </Group>
            ) : (
              <Select
                label="LabProfile"
                description="多数序列需要绑定 lab 才能找到仪器 endpoint; 直连 IP 类可留空"
                data={labs.map((l) => ({
                  value: l.id,
                  label: l.chamber_name ? `${l.name} — ${l.chamber_name}` : l.name,
                }))}
                value={selectedLabId || null}
                onChange={(v) => setSelectedLabId(v || '')}
                placeholder="选择 LabProfile..."
                clearable
              />
            )}
            {seqLoading ? (
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="sm" c="dimmed">加载序列...</Text>
              </Group>
            ) : (
              <Select
                label="序列"
                data={sequences.map((s) => ({ value: s.key, label: s.name }))}
                value={selectedKey || null}
                onChange={(v) => v && setSelectedKey(v)}
                required
                allowDeselect={false}
              />
            )}
          </Group>

          {selectedSequence && (
            <Alert color={selectedSequence.safe_during_test ? 'blue' : 'yellow'} variant="light"
              icon={selectedSequence.safe_during_test ? <IconCheck size={18} /> : <IconAlertTriangle size={18} />}
              title={selectedSequence.safe_during_test ? '可在测试运行中执行' : '会改变仪器状态 — 不要在正式测试中跑'}
            >
              <Stack gap={4}>
                <Text size="sm">{selectedSequence.description}</Text>
                {selectedSequence.required_categories.length > 0 && (
                  <Text size="xs" c="dimmed">
                    需要 lab 绑定: {selectedSequence.required_categories.join(', ')}
                  </Text>
                )}
              </Stack>
            </Alert>
          )}

          {selectedSequence && selectedSequence.params_schema.length > 0 && (
            <>
              <Divider label="参数" labelPosition="left" />
              <Group grow align="flex-end" wrap="wrap">
                {selectedSequence.params_schema.map(renderParamField)}
              </Group>
            </>
          )}

          <TextInput
            label="操作员"
            placeholder="工号 / 姓名 (审计行)"
            value={runBy}
            onChange={(e) => setRunBy(e.currentTarget.value)}
          />

          <Group justify="flex-end">
            <Button
              leftSection={<IconPlayerPlay size={16} />}
              onClick={handleRun}
              disabled={!selectedKey || running}
              loading={running}
            >
              运行序列
            </Button>
          </Group>
        </Stack>
      </Paper>

      {/* Result panel */}
      {(lastResult || lastError) && (
        <Paper p="md" withBorder>
          {lastError ? (
            <Alert color="red" icon={<IconAlertCircle size={18} />} title="执行失败 (HTTP)">
              {lastError}
            </Alert>
          ) : lastResult && (
            <Stack gap="sm">
              <Group gap="sm">
                <Title order={5}>结果</Title>
                <Badge color={lastResult.success ? 'green' : 'orange'}>
                  {lastResult.success ? 'success' : 'failure'}
                </Badge>
                <Badge variant="light">{lastResult.duration_ms} ms</Badge>
                <Code>{lastResult.diagnostic_run_id.slice(0, 8)}...</Code>
              </Group>
              <Text size="sm">{lastResult.summary}</Text>
              {lastResult.steps.length > 0 && (
                <Stack gap={4}>
                  {lastResult.steps.map((s, i) => (
                    <Group key={i} gap="xs" wrap="nowrap" align="flex-start">
                      <Badge color={s.success ? 'green' : 'red'} size="sm" variant="filled">
                        {s.success ? '✓' : '✗'}
                      </Badge>
                      <Text size="xs" fw={500} style={{ flexShrink: 0 }}>{s.label}</Text>
                      <Text size="xs" c="dimmed" style={{ wordBreak: 'break-all' }}>
                        {s.detail}
                      </Text>
                      {s.duration_ms !== undefined && s.duration_ms !== null && (
                        <Text size="xs" c="dimmed" ml="auto">{s.duration_ms} ms</Text>
                      )}
                    </Group>
                  ))}
                </Stack>
              )}
              {lastResult.log.length > 0 && (
                <>
                  <Divider label="日志" labelPosition="left" />
                  <ScrollArea h={150}>
                    <Code block style={{ fontSize: 12 }}>
                      {lastResult.log.join('\n')}
                    </Code>
                  </ScrollArea>
                </>
              )}
            </Stack>
          )}
        </Paper>
      )}

      {/* Recent runs */}
      <Paper p="md" withBorder>
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <IconHistory size={16} />
            <Title order={5}>最近运行 (本类型)</Title>
            <Badge variant="light">{recentRuns.length}</Badge>
          </Group>
          <Button
            variant="subtle"
            size="xs"
            leftSection={<IconRefresh size={14} />}
            onClick={refreshRecent}
            loading={recentLoading}
          >
            刷新
          </Button>
        </Group>

        {recentLoading ? (
          <Center py="md"><Loader size="sm" /></Center>
        ) : recentRuns.length === 0 ? (
          <Text size="sm" c="dimmed">还没有运行历史</Text>
        ) : (
          <ScrollArea h={Math.min(280, 40 + recentRuns.length * 28)}>
            <Stack gap={4}>
              {recentRuns.map((r) => (
                <Group key={r.id} gap="xs" wrap="nowrap">
                  <Badge color={r.success ? 'green' : 'red'} size="xs" variant="filled">
                    {r.success ? '✓' : '✗'}
                  </Badge>
                  <Code style={{ flexShrink: 0 }}>{r.target_name}</Code>
                  {r.duration_ms != null && (
                    <Badge variant="light" size="xs">{r.duration_ms} ms</Badge>
                  )}
                  <Text size="xs" c="dimmed" style={{ flexShrink: 0 }}>
                    {new Date(r.run_at).toLocaleString()}
                  </Text>
                  {r.run_by && (
                    <Text size="xs" c="dimmed" ml="auto">@ {r.run_by}</Text>
                  )}
                </Group>
              ))}
            </Stack>
          </ScrollArea>
        )}
      </Paper>
    </Stack>
  )
}
