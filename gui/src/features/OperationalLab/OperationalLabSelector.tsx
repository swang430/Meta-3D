/**
 * P1-57：header 上的唯一「当前 LabProfile / 暗室」选择器。
 * 同时展示 LabProfile 与派生暗室；loading / error / 未绑定三种状态分开。
 */
import { Badge, Group, Select, Text, Tooltip } from '@mantine/core'
import { notifications } from '@mantine/notifications'

import { useOperationalLab } from './OperationalLabContext'

export function OperationalLabSelector() {
  const {
    activeLabs,
    loading,
    error,
    selectedLabProfileId,
    selectedLabProfile,
    chamberName,
  } = useOperationalLab()
  const { requestLabChange } = useOperationalLab()

  if (loading) {
    return <Badge variant="light" color="gray">LabProfile 加载中…</Badge>
  }
  if (error) {
    // 设计 §8：加载失败保留当前已解析上下文，但禁止切换；不当成 0 个
    return (
      <Tooltip label={`LabProfile 列表加载失败：${error}`} position="bottom">
        <Badge variant="light" color="red">
          {selectedLabProfile
            ? `当前：${selectedLabProfile.name}（列表加载失败，切换已禁用）`
            : 'LabProfile 列表加载失败'}
        </Badge>
      </Tooltip>
    )
  }

  return (
    <Group gap="xs" wrap="nowrap">
      <Text size="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
        当前：
      </Text>
      <Select
        size="sm"
        w={260}
        aria-label="当前 LabProfile"
        placeholder="请选择当前 LabProfile"
        data={activeLabs.map((l) => ({
          value: l.id,
          label: l.chamber_name ? `${l.name} / ${l.chamber_name}` : `${l.name}（未绑定暗室）`,
        }))}
        value={selectedLabProfileId}
        onChange={(next) => {
          if (!next || next === selectedLabProfileId) return
          const r = requestLabChange(next)
          if (!r.ok) {
            notifications.show({
              color: 'orange',
              title: 'LabProfile 切换被阻止',
              message: r.blockers.join('；'),
            })
          }
        }}
        allowDeselect={false}
      />
      {selectedLabProfile && !chamberName && (
        <Tooltip
          label="该 LabProfile 未绑定暗室 —— 暗室相关页面不会加载数据。请到 LabProfile 管理里绑定。"
          position="bottom"
        >
          <Badge variant="light" color="orange">未绑定暗室</Badge>
        </Tooltip>
      )}
    </Group>
  )
}
