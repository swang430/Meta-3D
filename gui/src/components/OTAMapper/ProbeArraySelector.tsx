/**
 * ProbeArraySelector Component
 * 探头阵列配置选择器
 */

import { Stack, Title, Select, NumberInput, Group, Text, Badge } from '@mantine/core'
import type { ProbeArrayConfig } from '../../types/channelEngine'
import { PROBE_ARRAY_TEMPLATES } from '../../types/channelEngine'
import {
  generateRingProbeArray,
  generateThreeRingProbeArray
} from '../../services/channelEngine'

interface ProbeArraySelectorProps {
  value: ProbeArrayConfig | null
  onChange: (config: ProbeArrayConfig | null) => void
}

export function ProbeArraySelector({ value, onChange }: ProbeArraySelectorProps) {
  // 模板选项
  const templateOptions = PROBE_ARRAY_TEMPLATES.map(template => ({
    value: template.id,
    label: template.name
  }))

  // 极化选项
  const polarizationOptions = [
    { value: 'V', label: 'V - 垂直极化' },
    { value: 'H', label: 'H - 水平极化' },
    { value: 'LHCP', label: 'LHCP - 左旋圆极化' },
    { value: 'RHCP', label: 'RHCP - 右旋圆极化' }
  ]

  // 应用模板
  const applyTemplate = (templateId: string | null) => {
    if (!templateId) {
      onChange(null)
      return
    }

    const template = PROBE_ARRAY_TEMPLATES.find(t => t.id === templateId)
    if (!template) return

    let config: ProbeArrayConfig

    // 根据模板生成探头阵列
    switch (templateId) {
      case '8-probe-ring':
        config = generateRingProbeArray(8, template.radius)
        break
      case '16-probe-ring':
        config = generateRingProbeArray(16, template.radius)
        break
      case '32-probe-3ring':
        config = generateThreeRingProbeArray(template.radius)
        break
      default:
        config = generateRingProbeArray(8, 3.0)
    }

    onChange(config)
  }

  // 更新探头数量（仅适用于单环）
  const updateProbeCount = (count: number) => {
    if (!value) return

    const newConfig = generateRingProbeArray(
      count,
      value.radius,
      90,  // 默认水平环
      value.probe_positions[0]?.polarization || 'V'
    )
    onChange(newConfig)
  }

  // 更新半径
  const updateRadius = (radius: number) => {
    if (!value) return

    // 保持现有探头位置的角度，只更新半径
    const updatedPositions = value.probe_positions.map(pos => ({
      ...pos,
      r: radius
    }))

    onChange({
      ...value,
      radius,
      probe_positions: updatedPositions
    })
  }

  // 更新极化
  const updatePolarization = (pol: string) => {
    if (!value) return

    const updatedPositions = value.probe_positions.map(pos => ({
      ...pos,
      polarization: pol as 'V' | 'H' | 'LHCP' | 'RHCP'
    }))

    onChange({
      ...value,
      probe_positions: updatedPositions
    })
  }

  return (
    <Stack gap="md">
      <Title order={4}>2. 探头阵列配置</Title>

      {/* 快速模板 */}
      <Select
        label="快速模板 *"
        placeholder="选择探头阵列模板"
        data={templateOptions}
        onChange={applyTemplate}
        required
        description="选择预定义的探头阵列配置"
      />

      {value && (
        <>
          {/* 配置摘要 */}
          <Group gap="xs">
            <Text size="sm" c="dimmed">当前配置:</Text>
            <Badge color="blue">{value.num_probes} 个探头</Badge>
            <Badge color="green">半径 {value.radius.toFixed(2)}m</Badge>
            <Badge color="orange">
              {value.probe_positions[0]?.polarization || 'V'} 极化
            </Badge>
          </Group>

          {/* 探头数量（仅单环） */}
          <NumberInput
            label="探头数量"
            value={value.num_probes}
            onChange={(val) => updateProbeCount(Number(val) || 8)}
            min={4}
            max={64}
            step={4}
            description="注意：修改数量将重新生成为单环配置"
          />

          {/* 暗室半径 */}
          <NumberInput
            label="暗室半径 (meters)"
            value={value.radius}
            onChange={(val) => updateRadius(Number(val) || 3.0)}
            min={1.0}
            max={10.0}
            step={0.1}
            decimalScale={2}
            description="MPAC暗室的半径"
          />

          {/* 极化方式 */}
          <Select
            label="极化方式"
            data={polarizationOptions}
            value={value.probe_positions[0]?.polarization || 'V'}
            onChange={(val) => updatePolarization(val || 'V')}
            description="所有探头使用相同极化"
          />
        </>
      )}

      {!value && (
        <Text size="sm" c="dimmed">
          请选择一个探头阵列模板开始配置
        </Text>
      )}
    </Stack>
  )
}
