/**
 * ProbeArraySelector Component
 * 探头阵列配置选择器
 *
 * 支持两种数据源：
 * 1. 从预定义模板快速选择（硬编码）
 * 2. 从当前活跃暗室配置加载（DB 数据）★ Phase 2 新增
 */

import { useState } from 'react'
import { Stack, Title, Select, NumberInput, Group, Text, Badge, Button, Alert } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQuery } from '@tanstack/react-query'
import type { ProbeArrayConfig } from '../../types/channelEngine'
import { PROBE_ARRAY_TEMPLATES } from '../../types/channelEngine'
import {
  generateRingProbeArray,
  generateThreeRingProbeArray
} from '../../services/channelEngine'
import { fetchActiveChamber } from '../../api/service'
import { dbProbesToProbeArrayConfig, validateProbeInChamber } from '../../utils/probeConverter'

// 前端直接请求探头数据（按 chamber_id 过滤）
async function fetchChamberProbes(chamberId: string) {
  const { default: axios } = await import('axios')
  const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  const response = await axios.get(`${BASE_URL}/chambers/${chamberId}/probes`)
  return response.data as { total: number; probes: any[] }
}

interface ProbeArraySelectorProps {
  value: ProbeArrayConfig | null
  onChange: (config: ProbeArrayConfig | null) => void
}

export function ProbeArraySelector({ value, onChange }: ProbeArraySelectorProps) {
  const [dataSource, setDataSource] = useState<string | null>(null)
  const [loadingFromDB, setLoadingFromDB] = useState(false)

  // 获取当前激活暗室
  const { data: activeChamber } = useQuery({
    queryKey: ['chamber', 'active'],
    queryFn: fetchActiveChamber,
    retry: 1,
  })

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
    { value: 'RHCP', label: 'RHCP - 右旋圆极化' },
    { value: 'VH', label: 'VH - 双极化' }
  ]

  // 从当前暗室配置加载探头
  const loadFromActiveChamber = async () => {
    if (!activeChamber) {
      notifications.show({
        title: '无可用暗室',
        message: '请先在"暗室配置"中创建并激活一个暗室配置',
        color: 'orange',
      })
      return
    }

    setLoadingFromDB(true)
    try {
      const data = await fetchChamberProbes(activeChamber.id)

      if (!data.probes || data.probes.length === 0) {
        notifications.show({
          title: '无探头数据',
          message: `暗室 "${activeChamber.name}" 没有关联的探头，请先初始化探头数据`,
          color: 'orange',
        })
        return
      }

      // 使用坐标转换工具
      const config = dbProbesToProbeArrayConfig(data.probes, activeChamber.chamber_radius_m)

      // 校验
      const warnings: string[] = []
      for (const probe of data.probes) {
        const result = validateProbeInChamber(probe, activeChamber.chamber_radius_m)
        if (!result.valid && result.message) {
          warnings.push(result.message)
        }
      }

      if (warnings.length > 0) {
        notifications.show({
          title: '坐标校验告警',
          message: `${warnings.length} 个探头半径与暗室不一致`,
          color: 'yellow',
        })
      }

      onChange(config)
      setDataSource('active-chamber')

      notifications.show({
        title: '加载成功',
        message: `已从暗室 "${activeChamber.name}" 加载 ${config.num_probes} 个探头`,
        color: 'green',
      })
    } catch (error) {
      console.error('Failed to load probes from DB:', error)
      notifications.show({
        title: '加载失败',
        message: error instanceof Error ? error.message : '未知错误',
        color: 'red',
      })
    } finally {
      setLoadingFromDB(false)
    }
  }

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
    setDataSource(templateId)
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

      {/* 从当前暗室加载 — 推荐入口 */}
      {activeChamber && (
        <Alert variant="light" color="teal" title="推荐：从暗室配置加载">
          <Group justify="space-between" align="center">
            <Text size="sm">
              当前暗室: <strong>{activeChamber.name}</strong>
              ({activeChamber.num_probes} 探头, 半径 {activeChamber.chamber_radius_m}m)
            </Text>
            <Button
              size="xs"
              color="teal"
              onClick={loadFromActiveChamber}
              loading={loadingFromDB}
            >
              加载实际探头配置
            </Button>
          </Group>
        </Alert>
      )}

      {/* 快速模板 */}
      <Select
        label="快速模板"
        placeholder="或选择探头阵列模板"
        data={templateOptions}
        onChange={applyTemplate}
        description="选择预定义的探头阵列配置"
        clearable
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
            {dataSource === 'active-chamber' && (
              <Badge color="teal" variant="light">来自暗室配置</Badge>
            )}
          </Group>

          {/* 探头数量（仅单环） */}
          {dataSource !== 'active-chamber' && (
            <NumberInput
              label="探头数量"
              value={value.num_probes}
              onChange={(val) => updateProbeCount(Number(val) || 8)}
              min={4}
              max={64}
              step={4}
              description="注意：修改数量将重新生成为单环配置"
            />
          )}

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
            disabled={dataSource === 'active-chamber'}
          />

          {/* 极化方式 */}
          {dataSource !== 'active-chamber' && (
            <Select
              label="极化方式"
              data={polarizationOptions}
              value={value.probe_positions[0]?.polarization || 'V'}
              onChange={(val) => updatePolarization(val || 'V')}
              description="所有探头使用相同极化"
            />
          )}
        </>
      )}

      {!value && (
        <Text size="sm" c="dimmed">
          请从暗室配置加载或选择一个探头阵列模板开始配置
        </Text>
      )}
    </Stack>
  )
}
