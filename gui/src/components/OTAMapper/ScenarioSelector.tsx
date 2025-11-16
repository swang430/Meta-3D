/**
 * ScenarioSelector Component
 * 场景配置选择器
 */

import { Stack, Title, Select, NumberInput, Switch } from '@mantine/core'
import type { ScenarioConfig, ScenarioType, ClusterModel } from '../../types/channelEngine'
import { SCENARIO_PRESETS } from '../../types/channelEngine'

interface ScenarioSelectorProps {
  value: ScenarioConfig
  onChange: (config: ScenarioConfig) => void
}

export function ScenarioSelector({ value, onChange }: ScenarioSelectorProps) {
  // 场景类型选项
  const scenarioTypeOptions: { value: ScenarioType; label: string }[] = [
    { value: 'UMa', label: 'UMa - 城市宏蜂窝 (Urban Macro)' },
    { value: 'UMi', label: 'UMi - 城市微蜂窝 (Urban Micro)' },
    { value: 'RMa', label: 'RMa - 乡村宏蜂窝 (Rural Macro)' },
    { value: 'InH', label: 'InH - 室内热点 (Indoor Hotspot)' }
  ]

  // 簇模型选项（可选）
  const clusterModelOptions: { value: ClusterModel; label: string }[] = [
    { value: 'CDL-A', label: 'CDL-A - LOS (低时延扩展)' },
    { value: 'CDL-B', label: 'CDL-B - NLOS (中等时延扩展)' },
    { value: 'CDL-C', label: 'CDL-C - NLOS (高时延扩展)' },
    { value: 'CDL-D', label: 'CDL-D - LOS (低时延扩展，低角度扩展)' },
    { value: 'CDL-E', label: 'CDL-E - NLOS (中等时延扩展)' },
    { value: 'TDL-A', label: 'TDL-A - Tapped Delay Line A' },
    { value: 'TDL-B', label: 'TDL-B - Tapped Delay Line B' },
    { value: 'TDL-C', label: 'TDL-C - Tapped Delay Line C' }
  ]

  // 预设场景选项
  const presetOptions = SCENARIO_PRESETS.map(preset => ({
    value: preset.id,
    label: preset.name
  }))

  // 应用预设
  const applyPreset = (presetId: string | null) => {
    if (!presetId) return

    const preset = SCENARIO_PRESETS.find(p => p.id === presetId)
    if (preset) {
      onChange(preset.config)
    }
  }

  return (
    <Stack gap="md">
      <Title order={4}>1. 测试场景配置</Title>

      {/* 快速预设 */}
      <Select
        label="快速预设"
        placeholder="选择预设场景配置"
        data={presetOptions}
        onChange={applyPreset}
        clearable
        description="快速应用常用场景配置"
      />

      {/* 场景类型 */}
      <Select
        label="场景类型 *"
        placeholder="选择3GPP场景"
        data={scenarioTypeOptions}
        value={value.scenario_type}
        onChange={(val) =>
          onChange({ ...value, scenario_type: val as ScenarioType })
        }
        required
        description="3GPP TR 38.901 定义的传播场景"
      />

      {/* 簇模型（可选） */}
      <Select
        label="簇模型（可选）"
        placeholder="选择簇模型进行混合建模"
        data={clusterModelOptions}
        value={value.cluster_model || null}
        onChange={(val) =>
          onChange({
            ...value,
            cluster_model: val as ClusterModel | undefined
          })
        }
        clearable
        description="混合模型：结合环境LSP和确定性簇模型"
      />

      {/* 中心频率 */}
      <NumberInput
        label="中心频率 (MHz) *"
        placeholder="例如: 3500"
        value={value.frequency_mhz}
        onChange={(val) =>
          onChange({ ...value, frequency_mhz: Number(val) || 3500 })
        }
        min={450}
        max={100000}
        step={100}
        required
        description="测试频率，常用: 2600MHz (n7), 3500MHz (n78), 4900MHz (n79)"
      />

      {/* 使用中值LSP */}
      <Switch
        label="使用中值LSP（确定性测试）"
        description="使用中值大尺度参数而非随机采样，获得可重复的测试结果"
        checked={value.use_median_lsps || false}
        onChange={(event) =>
          onChange({
            ...value,
            use_median_lsps: event.currentTarget.checked
          })
        }
      />
    </Stack>
  )
}
