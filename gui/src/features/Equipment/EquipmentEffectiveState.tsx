import { Alert, Card, Stack, Text, Title } from '@mantine/core'
import type { HALCategoryActivationResult, HALReadinessResponse, InstrumentCategory } from '../../types/api'

export type EquipmentOperationReceipt = {
  phase: 'saving' | 'activating' | 'finished' | 'save_failed'
  activation?: HALCategoryActivationResult
  error?: string
}

/** Recent operation receipts are not current HAL truth or execution qualification. */
export function EquipmentEffectiveState({ category, dirty, savedAvailable, receipt, labId, readiness }: {
  category: InstrumentCategory
  dirty: boolean
  savedAvailable: boolean
  receipt?: EquipmentOperationReceipt
  labId: string | null
  readiness?: HALReadinessResponse
}) {
  const binding = category.key === 'baseStation' ? readiness?.base_station_binding
    : category.key === 'channelEmulator' ? readiness?.channel_emulator_binding : null
  const sameLab = Boolean(labId && readiness?.lab_profile.profile_id === labId)
  const driver = sameLab ? readiness?.drivers.find(row => row.category === category.key) : undefined
  const message = !receipt ? '尚未取得本页操作回执'
    : receipt.phase === 'saving' ? '正在保存；尚未尝试HAL激活'
    : receipt.phase === 'save_failed' ? '保存失败；未尝试HAL激活'
    : receipt.phase === 'activating' ? '已保存；正在激活HAL'
    : receipt.error ? '已保存，但HAL激活失败'
    : receipt.activation?.status === 'inactive' ? '已保存；类别未启用，未加载驱动'
    : receipt.activation?.simulated ? '已保存；HAL模拟激活回执，仅诊断'
    : receipt.activation ? `已保存；HAL操作回执：${receipt.activation.status}` : '已保存；未取得HAL回执'
  return <Card withBorder data-testid="equipment-effective-state">
    <Stack gap="xs">
      <Title order={4}>配置生效状态</Title>
      <Text>{dirty ? '草稿尚未保存' : '草稿与当前保存值一致'}</Text>
      {savedAvailable ? <>
        <Text>已保存端点：{category.connection.endpoint || '未设置'}</Text>
        <Text>已保存型号：{category.models.find(model => model.id === category.selectedModelId)?.model ?? '未选择'}</Text>
        <Text>已保存驱动模式：{category.driverMode}</Text>
      </> : <Alert color="yellow">保存值读取中或不可用；不以旧目录宣称当前已保存。</Alert>}
      <Text>{message}</Text>
      {receipt?.error && <Text c="red">{receipt.error}</Text>}
      <Text size="sm">最近操作回执仅属于本页、本类别，不等于当前HAL快照或正式执行资格。</Text>
      <Text>HAL当前快照：{driver ? `${driver.status} · ${driver.endpoint} · ${driver.detail}` : '未取得'}</Text>
      <Text>LabProfile绑定：{!labId ? '未选择LabProfile' : sameLab && binding?.lab_profile_id === labId
        ? `${binding.status} · ${binding.execution_mode ?? '未知模式'}${binding.execution_mode === 'simulated' ? ' · 仅诊断' : ''} · ${binding.detail}` : '未取得该类别权威投影'}</Text>
      <Text size="sm">LabProfile未自动同步；用例兼容性与正式资格仍需服务器独立评估。</Text>
    </Stack>
  </Card>
}
