/**
 * P1-1 PR B — pre-flight gap check modal.
 *
 * Operator picks a LabProfile (defaults to the last one used via
 * localStorage), hits "运行预检", and sees the typed result from
 * POST /test-plans/{id}/preflight:
 *   - ready=true → green Alert "可以运行"
 *   - gaps → one Paper card per gap, with step name + missing token
 *     badge + actionable reason. Sorted by step execution order so
 *     the operator sees failures in the order they'd hit them.
 *   - not_loaded_categories → yellow Alert distinct from gaps,
 *     because the remedy is different ("重新加载 HAL" vs "缺许可/硬件")
 *   - unknown_tokens → gray Alert (typo warning, doesn't block)
 *   - lab_capabilities → collapsible "lab 提供的能力", for context
 *
 * Why ask the operator to pick a lab every time (no auto-resolve):
 * the backend endpoint requires `lab_profile_id` explicitly because
 * the commissioning factory's auto-resolve trip-wired a 500 storm
 * during P2-2 smoke when multiple active labs existed. Forcing the
 * GUI to be explicit pushes the choice up to the operator instead
 * of burying it in server logic that can silently pick wrong.
 * Default-to-last-used keeps the click count low in the common case.
 */
import { useEffect, useState } from 'react'
import {
  Modal,
  Stack,
  Group,
  Select,
  Button,
  Alert,
  Paper,
  Text,
  Badge,
  Loader,
  Center,
  Collapse,
  Code,
  ScrollArea,
} from '@mantine/core'
import {
  IconCheck,
  IconAlertTriangle,
  IconBan,
  IconChevronDown,
  IconChevronRight,
  IconPlayerPlay,
} from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { useQuery } from '@tanstack/react-query'

import { fetchLabProfiles } from '../../../../api/labProfileService'
import {
  runPreflight,
  type PreflightResult,
} from '../../../../api/preflightService'

// Remember the operator's last selection so the next plan they
// preflight defaults to the same lab. Scope key per-browser; not
// per-user (no auth context in this app yet).
const LAST_LAB_LS_KEY = 'mimo.preflight.lastLabId'

interface PreflightModalProps {
  opened: boolean
  onClose: () => void
  planId: string | null
  planName: string | null
}

export function PreflightModal({
  opened,
  onClose,
  planId,
  planName,
}: PreflightModalProps) {
  const [labId, setLabId] = useState<string | null>(null)
  const [result, setResult] = useState<PreflightResult | null>(null)
  const [showCapabilities, setShowCapabilities] = useState(false)

  // Load active labs once the modal opens. `enabled: opened` avoids
  // a fetch when the modal is closed but the component is mounted.
  const { data: labs = [], isLoading: labsLoading } = useQuery({
    queryKey: ['preflight', 'labs'],
    queryFn: () => fetchLabProfiles(true),
    enabled: opened,
  })

  // Restore last-used lab when the modal opens or the lab list arrives.
  // Only auto-pick if the saved lab is still in the active list — a
  // stale id would 422 on submit and surprise the operator.
  useEffect(() => {
    if (!opened) return
    if (labId) return
    const saved = localStorage.getItem(LAST_LAB_LS_KEY)
    if (saved && labs.some((l) => l.id === saved)) {
      setLabId(saved)
    }
  }, [opened, labs, labId])

  const preflightMutation = useMutation({
    mutationFn: ({ planId, labId }: { planId: string; labId: string }) =>
      runPreflight(planId, labId),
    onSuccess: (data, { labId }) => {
      setResult(data)
      localStorage.setItem(LAST_LAB_LS_KEY, labId)
    },
    onError: (err: Error) => {
      setResult(null)
      notifications.show({
        title: '预检失败',
        message: err.message || '未能调用预检端点',
        color: 'red',
      })
    },
  })

  // Reset transient state on close so the next open is clean.
  const handleClose = () => {
    setResult(null)
    preflightMutation.reset()
    onClose()
  }

  const handleRun = () => {
    if (!planId || !labId) return
    preflightMutation.mutate({ planId, labId })
  }

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={
        <Group gap="xs">
          <Text fw={600}>预检</Text>
          {planName && (
            <Text c="dimmed" size="sm">
              — {planName}
            </Text>
          )}
        </Group>
      }
      size="lg"
    >
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          检查这个计划的每个步骤是否在选定 Lab 的已加载驱动上都有所需能力 (
          <Code>step.needs</Code> vs <Code>driver.capabilities</Code>)。
          运行前发现 license 缺失 / 硬件没接 / HAL 没加载，避免在第 4 步才失败。
        </Text>

        <Group align="flex-end" grow>
          {labsLoading ? (
            <Group gap="xs">
              <Loader size="xs" />
              <Text size="sm" c="dimmed">
                加载 LabProfile...
              </Text>
            </Group>
          ) : (
            <Select
              label="LabProfile"
              description="预检会按此 lab 的 instrument_bindings 限定能力检查"
              placeholder="选择 LabProfile..."
              data={labs.map((l) => ({
                value: l.id,
                label: l.chamber_name ? `${l.name} — ${l.chamber_name}` : l.name,
              }))}
              value={labId}
              onChange={setLabId}
              required
            />
          )}
          <Button
            leftSection={<IconPlayerPlay size={16} />}
            onClick={handleRun}
            loading={preflightMutation.isPending}
            disabled={!planId || !labId}
          >
            运行预检
          </Button>
        </Group>

        {result && <PreflightResultView result={result} showCapabilities={showCapabilities} setShowCapabilities={setShowCapabilities} />}

        <Group justify="flex-end">
          <Button variant="default" onClick={handleClose}>
            关闭
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

interface ResultViewProps {
  result: PreflightResult
  showCapabilities: boolean
  setShowCapabilities: (v: boolean) => void
}

function PreflightResultView({
  result,
  showCapabilities,
  setShowCapabilities,
}: ResultViewProps) {
  return (
    <Stack gap="sm">
      {result.ready ? (
        <Alert
          color="green"
          icon={<IconCheck size={18} />}
          title="可以运行"
        >
          所有步骤的能力需求都在此 Lab 的已加载驱动中找到。
          {result.unknown_tokens.length > 0 &&
            ' (但有未知 token，见下方警告)'}
        </Alert>
      ) : (
        <Alert
          color="red"
          icon={<IconBan size={18} />}
          title={`${result.gaps.length} 个能力缺口阻止运行`}
        >
          下方列出每个 gap 对应的步骤和缺失 token。运行前修复才能放行。
        </Alert>
      )}

      {/* not_loaded_categories — distinct remedy from gaps, so a
          distinct visual. Even when this is non-empty the gaps list
          above already captures the impact; this Alert is the
          "operator: probably need to reload HAL" hint. */}
      {result.not_loaded_categories.length > 0 && (
        <Alert
          color="yellow"
          icon={<IconAlertTriangle size={18} />}
          title="部分绑定类别 HAL 未加载"
        >
          <Text size="sm" mb="xs">
            此 Lab 绑定了以下类别，但 HAL 当前没有加载对应驱动：
          </Text>
          <Group gap="xs">
            {result.not_loaded_categories.map((c) => (
              <Badge key={c} color="yellow" variant="light">
                {c}
              </Badge>
            ))}
          </Group>
          <Text size="xs" c="dimmed" mt="xs">
            通常表示连接没起来或 LabProfile 切换后未重载 HAL。先尝试在仪器面板重载，再重跑预检。
          </Text>
        </Alert>
      )}

      {result.gaps.length > 0 && (
        <Stack gap="xs">
          <Text size="sm" fw={500}>
            能力缺口 ({result.gaps.length})
          </Text>
          <ScrollArea.Autosize mah={300}>
            <Stack gap="xs">
              {result.gaps.map((gap) => (
                <Paper key={`${gap.step_id}-${gap.missing_token}`} withBorder p="sm">
                  <Stack gap={4}>
                    <Group justify="space-between" align="flex-start">
                      <Group gap="xs">
                        <Badge size="sm" variant="outline">
                          步骤 #{gap.step_order}
                        </Badge>
                        <Text fw={500} size="sm">
                          {gap.step_name}
                        </Text>
                      </Group>
                      <Badge color="red" variant="light">
                        缺: <Code>{gap.missing_token}</Code>
                      </Badge>
                    </Group>
                    <Text size="xs" c="dimmed">
                      {gap.reason}
                    </Text>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          </ScrollArea.Autosize>
        </Stack>
      )}

      {result.unknown_tokens.length > 0 && (
        <Alert
          color="gray"
          icon={<IconAlertTriangle size={18} />}
          title="未知能力 token (可能是 typo)"
        >
          <Text size="sm" mb="xs">
            以下 token 不在 <Code>KNOWN_CAPABILITIES</Code> 词表中，预检按"警告"处理 — 不会阻止运行，但建议修正：
          </Text>
          <Group gap="xs">
            {result.unknown_tokens.map((t) => (
              <Code key={t}>{t}</Code>
            ))}
          </Group>
        </Alert>
      )}

      {/* Collapsible — context info, not actionable. */}
      <Group
        gap={4}
        onClick={() => setShowCapabilities(!showCapabilities)}
        style={{ cursor: 'pointer' }}
      >
        {showCapabilities ? (
          <IconChevronDown size={14} />
        ) : (
          <IconChevronRight size={14} />
        )}
        <Text size="xs" c="dimmed">
          此 Lab 提供的能力 ({result.lab_capabilities.length})
        </Text>
      </Group>
      <Collapse in={showCapabilities}>
        {result.lab_capabilities.length === 0 ? (
          <Text size="xs" c="dimmed">
            (空 — 此 lab 的 instrument_bindings 中没有任何 HAL-loaded 驱动)
          </Text>
        ) : (
          <Group gap="xs">
            {result.lab_capabilities.map((t) => (
              <Badge key={t} variant="light" size="sm">
                {t}
              </Badge>
            ))}
          </Group>
        )}
      </Collapse>
    </Stack>
  )
}
