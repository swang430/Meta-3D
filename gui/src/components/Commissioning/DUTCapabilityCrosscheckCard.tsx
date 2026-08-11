/**
 * DUTProfile 阶段 4: 声明 vs 实测协商交叉核对结果卡片 + operator 显式反写。
 *
 * 后端把交叉核对写进阶段 measurements（旧流程在 PRECHECK，managed RF attach
 * 流程在 MEASURE.controlled_dut_attach）:
 *   - dut_capability_mismatch: { consistent, skipped, mismatches[{field, declared, observed}] }
 *   - dut_capability_observed: { dut_profile_id, dut_profile_name, source, max_* }
 *
 * 设计原则 (用户 2026-06-04): 声明 vs 实测不一致 = 有用发现, 不影响预检通过; observed
 * **不自动覆盖**声明; operator 在这里**显式**点「采纳实测值」才反写 (走 PUT /dut-profiles/{id})。
 */
import {
  Alert,
  Button,
  Card,
  Group,
  Table,
  Text,
  ThemeIcon,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import { IconArrowsExchange, IconCheck } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { updateDUTProfile, type DUTProfileUpdatePayload } from '../../api/dutProfileService'

interface MismatchItem {
  field: string
  declared: unknown
  observed: unknown
}
interface MismatchPayload {
  consistent: boolean
  skipped: boolean
  mismatches: MismatchItem[]
}
interface ObservedPayload {
  dut_profile_id?: string
  dut_profile_name?: string
  source?: string
  [k: string]: unknown
}

// 后端 mismatch field → DUTProfile 字段名一致 (max_dl_layers 等), 直接当 update payload key 用。
const FIELD_LABELS: Record<string, string> = {
  max_dl_layers: '最大 DL 层数',
  max_ul_layers: '最大 UL 层数',
  max_modulation_dl: '最大 DL 调制',
  max_modulation_ul: '最大 UL 调制',
}

interface CapabilityCrosscheckData {
  dut_capability_mismatch?: MismatchPayload
  dut_capability_observed?: ObservedPayload
}

export function DUTCapabilityCrosscheckCard({ data }: { data: CapabilityCrosscheckData | null | undefined }) {
  const queryClient = useQueryClient()
  const mismatch: MismatchPayload | undefined = data?.dut_capability_mismatch
  const observed: ObservedPayload | undefined = data?.dut_capability_observed

  const adoptMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: DUTProfileUpdatePayload }) =>
      updateDUTProfile(id, payload),
    onSuccess: (p) => {
      notifications.show({
        title: '已采纳实测值',
        message: `DUT 声明「${p.name}」已更新为实测协商能力`,
        color: 'green',
      })
      queryClient.invalidateQueries({ queryKey: ['dut-profiles'] })
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (e as Error)?.message ??
        '未知错误'
      notifications.show({ title: '采纳失败', message: String(detail), color: 'red' })
    },
  })

  // 没核对数据 / 无可比实测 (mock/未 attach skipped) → 不渲染
  if (!mismatch || mismatch.skipped) return null

  // 一致 → 绿色确认条 (让 operator 知道核对做了且通过)
  if (mismatch.consistent || mismatch.mismatches.length === 0) {
    return (
      <Alert color="green" variant="light" icon={<IconCheck />} title="DUT 能力交叉核对">
        DUT 声明跟实测协商能力一致
        {observed?.dut_profile_name ? `（${observed.dut_profile_name}）` : ''}。
      </Alert>
    )
  }

  const profileId = observed?.dut_profile_id
  const profileName = observed?.dut_profile_name ?? 'DUT'

  const confirmAdopt = () => {
    if (!profileId) return
    const payload: DUTProfileUpdatePayload = {}
    for (const m of mismatch.mismatches) {
      ;(payload as Record<string, unknown>)[m.field] = m.observed
    }
    modals.openConfirmModal({
      title: '采纳实测值更新声明',
      children: (
        <Text size="sm">
          将把 DUT 声明「{profileName}」的{' '}
          {mismatch.mismatches.map((m) => FIELD_LABELS[m.field] ?? m.field).join('、')}{' '}
          更新为实测协商值。声明是规划期 spec —— 这是你<strong>显式</strong>决定用实测覆盖, 确认?
        </Text>
      ),
      labels: { confirm: '采纳实测值', cancel: '取消' },
      confirmProps: { color: 'orange' },
      onConfirm: () => adoptMutation.mutate({ id: profileId, payload }),
    })
  }

  return (
    <Card withBorder bg="yellow.0">
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          <ThemeIcon color="orange" variant="light">
            <IconArrowsExchange size={16} />
          </ThemeIcon>
          <Text fw={600}>DUT 声明 vs 实测协商不一致</Text>
        </Group>
        {observed?.source ? (
          <Text size="xs" c="dimmed">
            实测源: {observed.source}
          </Text>
        ) : null}
      </Group>
      <Text size="sm" c="dimmed" mb="sm">
        DUT 实际协商能力跟它的声明 spec 不符（固件 / SIM / 声明过时）。这是有用发现，不单独改变本次测量判定。
        可「采纳实测值」把声明更新为实测, 或保留声明手动核查。
      </Text>
      <Table striped withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>能力项</Table.Th>
            <Table.Th>声明 (spec)</Table.Th>
            <Table.Th>实测协商 (actual)</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {mismatch.mismatches.map((m) => (
            <Table.Tr key={m.field}>
              <Table.Td>{FIELD_LABELS[m.field] ?? m.field}</Table.Td>
              <Table.Td>
                <Text c="blue">{String(m.declared)}</Text>
              </Table.Td>
              <Table.Td>
                <Text c="orange" fw={600}>
                  {String(m.observed)}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Group justify="flex-end" mt="sm">
        <Button
          variant="light"
          color="orange"
          size="sm"
          leftSection={<IconArrowsExchange size={16} />}
          onClick={confirmAdopt}
          loading={adoptMutation.isPending}
          disabled={!profileId}
        >
          采纳实测值更新声明
        </Button>
      </Group>
    </Card>
  )
}
