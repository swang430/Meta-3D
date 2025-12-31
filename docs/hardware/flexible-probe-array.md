# 灵活探头阵列配置设计方案

## 📋 需求分析

### 实际应用场景的多样性

MPAC暗室探头配置需要支持多种测试场景和预算约束：

| 配置类型 | 探头数 | 极化 | 分布 | 应用场景 |
|---------|-------|------|------|----------|
| **基础配置** | 8 | 双极化 | 单层水平环 | 基础覆盖测试、预算受限 |
| **标准配置** | 16 | 双极化 | 2层环形 | 标准MIMO OTA测试 |
| **高级配置** | 32 | 双极化 | 3层环形 | 高精度3D场景重建 |
| **定制配置** | 变化 | 混合 | 非均匀/3D | 特定场景优化 |

### 关键灵活性需求

1. **数量灵活性**: 8、16、32、48或自定义数量
2. **极化灵活性**: 单极化(V/H)、双极化(V+H)、圆极化(LHCP/RHCP)
3. **空间灵活性**:
   - 单层/多层环形
   - 均匀/非均匀分布
   - 球形/柱形/自由3D
4. **探头异构性**:
   - 不同功率等级
   - 不同天线增益
   - 不同方向图(pattern)
   - 不同频段特性

---

## 🏗️ 数据模型设计

### 1. 探头物理特性模型

```typescript
// gui/src/types/roadTest/probeArray.ts

/**
 * 探头物理特性
 */
export interface ProbePhysicalSpec {
  // 基本标识
  manufacturer: string           // 厂商: 'Rohde & Schwarz', 'Keysight', etc.
  model: string                  // 型号: 'HF906', 'N9311A', etc.
  serialNumber?: string          // 序列号

  // 频率特性
  frequencyRange: {
    min: number                  // 最低频率 (MHz)
    max: number                  // 最高频率 (MHz)
  }

  // 功率特性
  powerHandling: {
    maxInputPower: number        // 最大输入功率 (dBm)
    averagePower: number         // 平均功率 (dBm)
    peakPower: number            // 峰值功率 (dBm)
  }

  // 增益特性
  gain: {
    typical: number              // 典型增益 (dBi)
    min: number                  // 最小增益 (dBi)
    max: number                  // 最大增益 (dBi)
    frequencyDependent: boolean  // 是否随频率变化
    gainTable?: Array<{          // 增益-频率表
      frequency: number          // MHz
      gain: number               // dBi
    }>
  }

  // 方向图特性
  antennaPattern: {
    type: 'omnidirectional' | 'directional' | 'custom'
    beamwidth: {
      horizontal: number         // 水平波束宽度 (度)
      vertical: number           // 垂直波束宽度 (度)
    }
    frontToBackRatio?: number    // 前后比 (dB)
    crossPolarDiscrimination?: number  // 交叉极化鉴别度 (dB)
    patternFile?: string         // 方向图数据文件路径
  }

  // 极化特性
  polarization: {
    type: 'linear-vertical' | 'linear-horizontal' | 'dual-linear' | 'circular-left' | 'circular-right' | 'dual-circular'
    purity?: number              // 极化纯度 (dB)
    axialRatio?: number          // 轴比 (dB, 圆极化时)
  }

  // 物理尺寸
  dimensions: {
    length: number               // 长度 (mm)
    width: number                // 宽度 (mm)
    height: number               // 高度 (mm)
    weight: number               // 重量 (kg)
  }

  // VSWR
  vswr: {
    typical: number              // 典型VSWR
    max: number                  // 最大VSWR
    frequencyDependent: boolean
    vswrTable?: Array<{
      frequency: number
      vswr: number
    }>
  }
}

/**
 * 探头实例配置（单个探头在阵列中的配置）
 */
export interface ProbeInstanceConfig {
  // 标识
  id: string                     // 探头ID: 'P-01', 'P-02', etc.
  name?: string                  // 可选名称: '上层-东', '中层-北' etc.

  // 物理规格引用
  physicalSpec: ProbePhysicalSpec

  // 空间位置
  position: {
    // 笛卡尔坐标
    cartesian: {
      x: number                  // 米
      y: number                  // 米
      z: number                  // 米
    }
    // 球坐标
    spherical: {
      theta: number              // 方位角 (度)
      phi: number                // 仰角 (度)
      r: number                  // 半径 (米)
    }
  }

  // 方向（探头朝向）
  orientation: {
    azimuth: number              // 水平方位角 (度)
    elevation: number            // 垂直仰角 (度)
    roll: number                 // 滚转角 (度)
  }

  // 极化配置（实际使用的极化）
  activePolarization: 'V' | 'H' | 'LHCP' | 'RHCP' | 'V+H'

  // 使能状态
  enabled: boolean

  // 校准数据
  calibration?: {
    calibratedAt: string         // ISO timestamp
    calibratedBy: string         // 操作员
    s11: number                  // 反射系数 (dB)
    phaseOffset: number          // 相位偏移 (度)
    amplitudeError: number       // 幅度误差 (dB)
  }

  // OTA权重（由映射器生成）
  weight?: {
    magnitude: number            // 幅度 (0-1)
    phase: number                // 相位 (度)
  }

  // 分组标签
  tags: string[]                 // ['上层', '主环', '校准探头'] etc.
}

/**
 * 探头阵列配置
 */
export interface ProbeArrayConfiguration {
  // 元数据
  id: string
  name: string
  description: string
  version: string
  createdAt: string
  updatedAt: string
  author?: string

  // 阵列几何
  geometry: {
    type: 'spherical' | 'cylindrical' | 'planar' | 'custom'
    centerPoint: {
      x: number
      y: number
      z: number
    }
    // 球形/柱形阵列参数
    radius?: number              // 米
    height?: number              // 米（柱形）
    layers?: number              // 层数
  }

  // 探头列表
  probes: ProbeInstanceConfig[]

  // 阵列统计
  statistics: {
    totalProbes: number
    enabledProbes: number
    polarizationBreakdown: {
      vertical: number
      horizontal: number
      leftCircular: number
      rightCircular: number
      dual: number
    }
    layerBreakdown?: Array<{
      layer: string
      count: number
    }>
  }

  // 暗室环境
  chamberEnvironment?: {
    dimensions: {
      length: number             // 米
      width: number              // 米
      height: number             // 米
    }
    quietZone: {
      diameter: number           // 静区直径 (米)
      centerHeight: number       // 静区中心高度 (米)
    }
    absorberType: string         // 吸波材料类型
    shieldingEffectiveness: number  // 屏蔽效能 (dB)
  }
}
```

---

## 🎨 预定义阵列模板

### 模板系统设计

```typescript
// gui/src/data/probeArrayTemplates.ts

export interface ProbeArrayTemplate {
  id: string
  name: string
  description: string
  thumbnail?: string             // 可视化预览图
  category: 'basic' | 'standard' | 'advanced' | 'custom'
  probeCount: number
  layers: number
  recommendedFor: string[]       // 推荐应用场景
  configuration: Omit<ProbeArrayConfiguration, 'id' | 'createdAt' | 'updatedAt'>
}

/**
 * 模板1: 基础8探头单层双极化配置
 */
export const template8ProbeBasic: ProbeArrayTemplate = {
  id: 'template-8probe-basic',
  name: '8探头基础配置',
  description: '单层水平环，8个双极化探头，均匀分布',
  category: 'basic',
  probeCount: 8,
  layers: 1,
  recommendedFor: ['基础覆盖测试', '预算受限场景', '快速验证'],
  configuration: {
    name: '8探头基础阵列',
    version: '1.0',
    geometry: {
      type: 'cylindrical',
      centerPoint: { x: 0, y: 0, z: 0 },
      radius: 2.5,
      layers: 1
    },
    probes: generateUniformCircularArray({
      count: 8,
      radius: 2.5,
      zHeight: 0,
      startAngle: 0,
      polarization: 'dual'
    }),
    statistics: {
      totalProbes: 8,
      enabledProbes: 8,
      polarizationBreakdown: {
        vertical: 8,
        horizontal: 8,
        leftCircular: 0,
        rightCircular: 0,
        dual: 8
      }
    }
  }
}

/**
 * 模板2: 标准16探头双层配置
 */
export const template16ProbeStandard: ProbeArrayTemplate = {
  id: 'template-16probe-standard',
  name: '16探头标准配置',
  description: '2层环形，每层8个双极化探头',
  category: 'standard',
  probeCount: 16,
  layers: 2,
  recommendedFor: ['标准MIMO OTA', '3GPP符合性测试', '中等预算'],
  configuration: {
    name: '16探头标准阵列',
    version: '1.0',
    geometry: {
      type: 'cylindrical',
      centerPoint: { x: 0, y: 0, z: 0 },
      radius: 2.5,
      layers: 2
    },
    probes: [
      // 上层 (z=0.5m)
      ...generateUniformCircularArray({
        count: 8,
        radius: 2.5,
        zHeight: 0.5,
        startAngle: 0,
        polarization: 'dual',
        idPrefix: 'P-U'
      }),
      // 下层 (z=-0.5m)
      ...generateUniformCircularArray({
        count: 8,
        radius: 2.5,
        zHeight: -0.5,
        startAngle: 22.5,  // 错位22.5度
        polarization: 'dual',
        idPrefix: 'P-L'
      })
    ],
    statistics: {
      totalProbes: 16,
      enabledProbes: 16,
      polarizationBreakdown: {
        vertical: 16,
        horizontal: 16,
        leftCircular: 0,
        rightCircular: 0,
        dual: 16
      },
      layerBreakdown: [
        { layer: '上层', count: 8 },
        { layer: '下层', count: 8 }
      ]
    }
  }
}

/**
 * 模板3: 高级32探头三层配置
 */
export const template32ProbeAdvanced: ProbeArrayTemplate = {
  id: 'template-32probe-advanced',
  name: '32探头高级配置',
  description: '3层环形：上层8，中层16，下层8',
  category: 'advanced',
  probeCount: 32,
  layers: 3,
  recommendedFor: ['高精度3D场景重建', '复杂环境仿真', '研发验证'],
  configuration: {
    name: '32探头高级阵列',
    version: '1.0',
    geometry: {
      type: 'spherical',
      centerPoint: { x: 0, y: 0, z: 0 },
      radius: 2.5,
      layers: 3
    },
    probes: [
      // 上层 (z=1.0m, 8探头)
      ...generateUniformCircularArray({
        count: 8,
        radius: 2.5,
        zHeight: 1.0,
        startAngle: 0,
        polarization: 'dual',
        idPrefix: 'P-U',
        tags: ['上层']
      }),
      // 中层 (z=0.0m, 16探头)
      ...generateUniformCircularArray({
        count: 16,
        radius: 2.5,
        zHeight: 0.0,
        startAngle: 0,
        polarization: 'dual',
        idPrefix: 'P-M',
        tags: ['中层']
      }),
      // 下层 (z=-1.0m, 8探头)
      ...generateUniformCircularArray({
        count: 8,
        radius: 2.5,
        zHeight: -1.0,
        startAngle: 22.5,
        polarization: 'dual',
        idPrefix: 'P-L',
        tags: ['下层']
      })
    ],
    statistics: {
      totalProbes: 32,
      enabledProbes: 32,
      polarizationBreakdown: {
        vertical: 32,
        horizontal: 32,
        leftCircular: 0,
        rightCircular: 0,
        dual: 32
      },
      layerBreakdown: [
        { layer: '上层', count: 8 },
        { layer: '中层', count: 16 },
        { layer: '下层', count: 8 }
      ]
    }
  }
}

/**
 * 模板4: 非均匀分布（针对特定场景优化）
 */
export const templateNonUniform: ProbeArrayTemplate = {
  id: 'template-non-uniform-urban',
  name: '非均匀城市场景优化',
  description: '针对城市环境优化的非均匀探头分布',
  category: 'custom',
  probeCount: 24,
  layers: 3,
  recommendedFor: ['城市峡谷场景', '非对称传播环境', '特定AoA分布'],
  configuration: {
    name: '非均匀城市阵列',
    version: '1.0',
    geometry: {
      type: 'custom',
      centerPoint: { x: 0, y: 0, z: 0 },
      radius: 2.5,
      layers: 3
    },
    probes: [
      // 水平面密集分布（城市主要散射方向）
      ...generateNonUniformArray({
        positions: [
          { theta: 0, phi: 90, r: 2.5 },
          { theta: 30, phi: 90, r: 2.5 },
          { theta: 60, phi: 90, r: 2.5 },
          { theta: 90, phi: 90, r: 2.5 },
          { theta: 120, phi: 90, r: 2.5 },
          { theta: 150, phi: 90, r: 2.5 },
          { theta: 180, phi: 90, r: 2.5 },
          { theta: 210, phi: 90, r: 2.5 },
          { theta: 240, phi: 90, r: 2.5 },
          { theta: 270, phi: 90, r: 2.5 },
          { theta: 300, phi: 90, r: 2.5 },
          { theta: 330, phi: 90, r: 2.5 },
        ],
        polarization: 'dual',
        tags: ['水平主环']
      }),
      // 上方稀疏（较少天空散射）
      ...generateNonUniformArray({
        positions: [
          { theta: 0, phi: 45, r: 2.5 },
          { theta: 90, phi: 45, r: 2.5 },
          { theta: 180, phi: 45, r: 2.5 },
          { theta: 270, phi: 45, r: 2.5 },
        ],
        polarization: 'dual',
        tags: ['上层稀疏']
      }),
      // 下方稀疏（地面反射）
      ...generateNonUniformArray({
        positions: [
          { theta: 0, phi: 135, r: 2.5 },
          { theta: 90, phi: 135, r: 2.5 },
          { theta: 180, phi: 135, r: 2.5 },
          { theta: 270, phi: 135, r: 2.5 },
        ],
        polarization: 'dual',
        tags: ['下层稀疏']
      })
    ],
    statistics: {
      totalProbes: 24,
      enabledProbes: 24,
      polarizationBreakdown: {
        vertical: 24,
        horizontal: 24,
        leftCircular: 0,
        rightCircular: 0,
        dual: 24
      },
      layerBreakdown: [
        { layer: '水平主环', count: 12 },
        { layer: '上层稀疏', count: 4 },
        { layer: '下层稀疏', count: 4 }
      ]
    }
  }
}

/**
 * 辅助函数：生成均匀圆形阵列
 */
function generateUniformCircularArray(params: {
  count: number
  radius: number
  zHeight: number
  startAngle: number
  polarization: 'single-V' | 'single-H' | 'dual'
  idPrefix?: string
  tags?: string[]
}): ProbeInstanceConfig[] {
  const probes: ProbeInstanceConfig[] = []
  const angleStep = 360 / params.count

  for (let i = 0; i < params.count; i++) {
    const theta = params.startAngle + i * angleStep
    const thetaRad = (theta * Math.PI) / 180

    const x = params.radius * Math.cos(thetaRad)
    const y = params.radius * Math.sin(thetaRad)
    const z = params.zHeight

    const baseProbe: ProbeInstanceConfig = {
      id: `${params.idPrefix || 'P'}-${String(i + 1).padStart(2, '0')}`,
      physicalSpec: getDefaultProbeSpec(),
      position: {
        cartesian: { x, y, z },
        spherical: { theta, phi: 90, r: params.radius }
      },
      orientation: {
        azimuth: theta + 180,  // 指向中心
        elevation: 0,
        roll: 0
      },
      activePolarization: params.polarization === 'dual' ? 'V+H' : (params.polarization === 'single-V' ? 'V' : 'H'),
      enabled: true,
      tags: params.tags || []
    }

    probes.push(baseProbe)
  }

  return probes
}

/**
 * 辅助函数：生成非均匀阵列
 */
function generateNonUniformArray(params: {
  positions: Array<{ theta: number; phi: number; r: number }>
  polarization: 'single-V' | 'single-H' | 'dual'
  tags?: string[]
}): ProbeInstanceConfig[] {
  return params.positions.map((pos, i) => {
    const thetaRad = (pos.theta * Math.PI) / 180
    const phiRad = (pos.phi * Math.PI) / 180

    const x = pos.r * Math.sin(phiRad) * Math.cos(thetaRad)
    const y = pos.r * Math.sin(phiRad) * Math.sin(thetaRad)
    const z = pos.r * Math.cos(phiRad)

    return {
      id: `P-${String(i + 1).padStart(2, '0')}`,
      physicalSpec: getDefaultProbeSpec(),
      position: {
        cartesian: { x, y, z },
        spherical: pos
      },
      orientation: {
        azimuth: pos.theta + 180,
        elevation: 90 - pos.phi,
        roll: 0
      },
      activePolarization: params.polarization === 'dual' ? 'V+H' : (params.polarization === 'single-V' ? 'V' : 'H'),
      enabled: true,
      tags: params.tags || []
    }
  })
}

/**
 * 默认探头物理规格
 */
function getDefaultProbeSpec(): ProbePhysicalSpec {
  return {
    manufacturer: 'Generic',
    model: 'Dual-Pol-2.5GHz',
    frequencyRange: { min: 1700, max: 6000 },
    powerHandling: {
      maxInputPower: 30,
      averagePower: 27,
      peakPower: 33
    },
    gain: {
      typical: 5,
      min: 4,
      max: 6,
      frequencyDependent: false
    },
    antennaPattern: {
      type: 'omnidirectional',
      beamwidth: {
        horizontal: 360,
        vertical: 90
      }
    },
    polarization: {
      type: 'dual-linear',
      purity: 20
    },
    dimensions: {
      length: 150,
      width: 150,
      height: 200,
      weight: 0.5
    },
    vswr: {
      typical: 1.5,
      max: 2.0,
      frequencyDependent: false
    }
  }
}

/**
 * 模板注册表
 */
export const probeArrayTemplates: ProbeArrayTemplate[] = [
  template8ProbeBasic,
  template16ProbeStandard,
  template32ProbeAdvanced,
  templateNonUniform
]
```

---

## 🎛️ UI组件设计

### 1. 探头阵列选择器

```typescript
// gui/src/components/ProbeArraySelector.tsx

import { useState } from 'react'
import { Card, Stack, Group, Text, Badge, Button, Grid, Radio } from '@mantine/core'
import { IconCheck } from '@tabler/icons-react'
import { probeArrayTemplates, ProbeArrayTemplate } from '../data/probeArrayTemplates'

export function ProbeArraySelector({
  onSelect
}: {
  onSelect: (template: ProbeArrayTemplate) => void
}) {
  const [selected, setSelected] = useState<string | null>(null)

  const handleSelect = (templateId: string) => {
    setSelected(templateId)
    const template = probeArrayTemplates.find(t => t.id === templateId)
    if (template) {
      onSelect(template)
    }
  }

  return (
    <Stack gap="md">
      <Text fw={600} size="lg">选择探头阵列配置</Text>

      <Grid>
        {probeArrayTemplates.map(template => (
          <Grid.Col key={template.id} span={{ base: 12, md: 6, lg: 3 }}>
            <Card
              withBorder
              radius="md"
              padding="lg"
              style={{
                cursor: 'pointer',
                borderColor: selected === template.id ? 'var(--mantine-color-blue-6)' : undefined,
                borderWidth: selected === template.id ? 2 : 1
              }}
              onClick={() => handleSelect(template.id)}
            >
              <Stack gap="sm">
                <Group justify="space-between">
                  <Badge color={getCategoryColor(template.category)}>
                    {template.category}
                  </Badge>
                  {selected === template.id && <IconCheck size={20} color="var(--mantine-color-blue-6)" />}
                </Group>

                <Text fw={600}>{template.name}</Text>
                <Text size="sm" c="dimmed">{template.description}</Text>

                <Stack gap={4}>
                  <Group gap="xs">
                    <Text size="xs" c="dimmed">探头数:</Text>
                    <Text size="sm" fw={500}>{template.probeCount}</Text>
                  </Group>
                  <Group gap="xs">
                    <Text size="xs" c="dimmed">层数:</Text>
                    <Text size="sm" fw={500}>{template.layers}</Text>
                  </Group>
                </Stack>

                <Stack gap={2}>
                  <Text size="xs" c="dimmed">推荐场景:</Text>
                  {template.recommendedFor.slice(0, 2).map(scenario => (
                    <Text key={scenario} size="xs">• {scenario}</Text>
                  ))}
                </Stack>
              </Stack>
            </Card>
          </Grid.Col>
        ))}
      </Grid>

      {selected && (
        <Button size="lg" onClick={() => {
          const template = probeArrayTemplates.find(t => t.id === selected)
          if (template) onSelect(template)
        }}>
          应用此配置
        </Button>
      )}
    </Stack>
  )
}

function getCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    basic: 'green',
    standard: 'blue',
    advanced: 'purple',
    custom: 'orange'
  }
  return colors[category] || 'gray'
}
```

### 2. 探头配置编辑器

```typescript
// gui/src/components/ProbeConfigEditor.tsx

import { useState } from 'react'
import { Stack, Tabs, Table, Switch, NumberInput, Select } from '@mantine/core'
import { ProbeArrayConfiguration, ProbeInstanceConfig } from '../types/roadTest/probeArray'

export function ProbeConfigEditor({
  config,
  onChange
}: {
  config: ProbeArrayConfiguration
  onChange: (config: ProbeArrayConfiguration) => void
}) {
  const [activeTab, setActiveTab] = useState<string>('probes')

  const handleProbeToggle = (probeId: string, enabled: boolean) => {
    const updatedProbes = config.probes.map(p =>
      p.id === probeId ? { ...p, enabled } : p
    )
    onChange({ ...config, probes: updatedProbes })
  }

  const handleProbeUpdate = (probeId: string, field: string, value: any) => {
    const updatedProbes = config.probes.map(p =>
      p.id === probeId ? { ...p, [field]: value } : p
    )
    onChange({ ...config, probes: updatedProbes })
  }

  return (
    <Tabs value={activeTab} onChange={(v) => setActiveTab(v || 'probes')}>
      <Tabs.List>
        <Tabs.Tab value="probes">探头列表</Tabs.Tab>
        <Tabs.Tab value="geometry">阵列几何</Tabs.Tab>
        <Tabs.Tab value="physics">物理参数</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="probes" pt="md">
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>ID</Table.Th>
              <Table.Th>位置</Table.Th>
              <Table.Th>极化</Table.Th>
              <Table.Th>标签</Table.Th>
              <Table.Th>启用</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {config.probes.map(probe => (
              <Table.Tr key={probe.id}>
                <Table.Td>{probe.id}</Table.Td>
                <Table.Td>
                  <Text size="xs" ff="monospace">
                    θ={probe.position.spherical.theta.toFixed(1)}°,
                    φ={probe.position.spherical.phi.toFixed(1)}°
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Select
                    size="xs"
                    value={probe.activePolarization}
                    data={[
                      { value: 'V', label: 'V (垂直)' },
                      { value: 'H', label: 'H (水平)' },
                      { value: 'V+H', label: 'V+H (双极化)' },
                      { value: 'LHCP', label: 'LHCP (左旋圆)' },
                      { value: 'RHCP', label: 'RHCP (右旋圆)' }
                    ]}
                    onChange={(v) => handleProbeUpdate(probe.id, 'activePolarization', v)}
                  />
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{probe.tags.join(', ')}</Text>
                </Table.Td>
                <Table.Td>
                  <Switch
                    checked={probe.enabled}
                    onChange={(e) => handleProbeToggle(probe.id, e.currentTarget.checked)}
                  />
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Tabs.Panel>

      <Tabs.Panel value="geometry" pt="md">
        <Stack gap="md">
          <Select
            label="阵列类型"
            value={config.geometry.type}
            data={[
              { value: 'spherical', label: '球形' },
              { value: 'cylindrical', label: '柱形' },
              { value: 'planar', label: '平面' },
              { value: 'custom', label: '自定义' }
            ]}
            onChange={(v) => onChange({
              ...config,
              geometry: { ...config.geometry, type: v as any }
            })}
          />

          {(config.geometry.type === 'spherical' || config.geometry.type === 'cylindrical') && (
            <NumberInput
              label="半径 (米)"
              value={config.geometry.radius}
              decimalScale={2}
              onChange={(v) => onChange({
                ...config,
                geometry: { ...config.geometry, radius: Number(v) }
              })}
            />
          )}

          <NumberInput
            label="层数"
            value={config.geometry.layers}
            onChange={(v) => onChange({
              ...config,
              geometry: { ...config.geometry, layers: Number(v) }
            })}
          />
        </Stack>
      </Tabs.Panel>

      <Tabs.Panel value="physics" pt="md">
        <Text size="sm" c="dimmed">
          物理参数编辑功能开发中...
        </Text>
      </Tabs.Panel>
    </Tabs>
  )
}
```

---

## 🔗 与OTA映射器集成

### 更新 OTAScenarioMapper

```typescript
// gui/src/services/roadTest/OTAScenarioMapper.ts (更新版本)

export class OTAScenarioMapper implements IScenarioMapper {
  // 新增：支持自定义探头阵列配置
  private probeArrayConfig?: ProbeArrayConfiguration

  constructor(probeArrayConfig?: ProbeArrayConfiguration) {
    this.probeArrayConfig = probeArrayConfig
  }

  async map(scenario: RoadTestScenarioDetail): OTATestConfiguration {
    // 1. 确定使用的探头阵列配置
    const arrayConfig = this.probeArrayConfig || this.selectDefaultArrayForScenario(scenario)

    // 2. 提取启用的探头
    const enabledProbes = arrayConfig.probes.filter(p => p.enabled)

    // 3. 准备ChannelEngine请求
    const probePositions = enabledProbes.map(p => ({
      id: p.id,
      theta: p.position.spherical.theta,
      phi: p.position.spherical.phi,
      r: p.position.spherical.r
    }))

    // 4. 调用ChannelEngine
    const channelResponse = await this.channelEngine.generateProbeWeights({
      scenario: {
        type: this.mapEnvironmentToScenario(scenario.environment.type),
        clusterModel: this.selectClusterModel(scenario.environment.type),
        frequency: scenario.networkConfig.frequency.dl,
        useMedianLSPs: false
      },
      probeArray: {
        geometry: arrayConfig.geometry.type,
        numProbes: enabledProbes.length,
        radius: arrayConfig.geometry.radius || 2.5,
        probePositions
      },
      mimoConfig: {
        numTxAntennas: scenario.networkConfig.mimoConfig?.numTxAntennas || 2,
        numRxAntennas: scenario.networkConfig.mimoConfig?.numRxAntennas || 2,
        numLayers: scenario.networkConfig.mimoConfig?.numLayers || 1
      }
    })

    // 5. 应用权重到探头配置
    const probesWithWeights = this.applyWeightsToProbes(
      enabledProbes,
      channelResponse.data.probeWeights
    )

    // 6. 生成OTA配置
    return {
      channelEmulator: this.mapChannelEmulator(scenario, channelResponse.data),
      baseStationEmulator: this.mapBaseStationEmulator(scenario),
      probeArray: this.convertToProbeArrayConfig(probesWithWeights, arrayConfig),
      testSequence: this.generateTestSequence(scenario),
      kpiTargets: scenario.kpiTargets,
      metadata: {
        scenarioId: scenario.id,
        scenarioName: scenario.name,
        generatedAt: new Date().toISOString(),
        generatedBy: 'OTAScenarioMapper v2.0',
        estimatedDuration: this.estimate(scenario).estimatedDuration,
        requiredInstruments: ['Channel Emulator', 'Base Station Emulator'],
        mappingVersion: '2.0.0',
        probeArrayInfo: {
          templateId: arrayConfig.id,
          templateName: arrayConfig.name,
          totalProbes: arrayConfig.probes.length,
          enabledProbes: enabledProbes.length
        }
      }
    }
  }

  /**
   * 根据场景自动选择合适的探头阵列模板
   */
  private selectDefaultArrayForScenario(scenario: RoadTestScenarioDetail): ProbeArrayConfiguration {
    const complexity = scenario.taxonomy?.complexity

    switch (complexity) {
      case 'basic':
        return template8ProbeBasic.configuration
      case 'intermediate':
        return template16ProbeStandard.configuration
      case 'advanced':
      case 'extreme':
        return template32ProbeAdvanced.configuration
      default:
        return template16ProbeStandard.configuration
    }
  }

  /**
   * 应用权重到探头配置
   */
  private applyWeightsToProbes(
    probes: ProbeInstanceConfig[],
    weights: Array<{ probeId: string; polarization: string; weight: { magnitude: number; phase: number } }>
  ): ProbeInstanceConfig[] {
    return probes.map(probe => {
      // 为每个探头找到对应的权重
      const weight = weights.find(w => w.probeId === probe.id)

      return {
        ...probe,
        weight: weight ? weight.weight : undefined
      }
    })
  }
}
```

---

## 📊 实施计划

### Phase 1: 数据模型 (1周)
- [ ] 创建 `probeArray.ts` 类型定义
- [ ] 实现 `ProbePhysicalSpec` 完整定义
- [ ] 实现 `ProbeInstanceConfig` 配置模型
- [ ] 实现 `ProbeArrayConfiguration` 阵列配置

### Phase 2: 模板系统 (1周)
- [ ] 实现4个预定义模板
- [ ] 创建阵列生成辅助函数
- [ ] 默认探头物理规格数据库
- [ ] 模板注册表和查询API

### Phase 3: UI组件 (1-2周)
- [ ] `ProbeArraySelector` 选择器组件
- [ ] `ProbeConfigEditor` 编辑器组件
- [ ] 扩展 `ProbeLayoutView` 支持多种配置
- [ ] 探头物理参数展示面板

### Phase 4: OTA映射器集成 (1周)
- [ ] 更新 `OTAScenarioMapper` 支持灵活配置
- [ ] 自动模板选择逻辑
- [ ] 权重应用到探头实例
- [ ] 端到端测试

### Phase 5: 高级功能 (可选)
- [ ] 探头阵列优化算法
- [ ] 基于场景的自动配置推荐
- [ ] 探头性能仿真预测
- [ ] 阵列配置导入/导出

---

## ✅ 总结

### 核心设计原则

1. **灵活性优先**: 支持8-48+探头的任意配置
2. **模板化**: 提供4种开箱即用的模板
3. **可扩展性**: 物理参数完整建模，支持异构探头
4. **向后兼容**: 与现有ProbeLayoutView无缝集成

### 关键特性

- ✅ **多种阵列几何**: 球形、柱形、平面、自定义
- ✅ **灵活极化**: 单极化、双极化、圆极化混合
- ✅ **非均匀分布**: 支持针对特定场景优化
- ✅ **探头异构**: 不同功率、增益、方向图
- ✅ **模板系统**: 快速部署常用配置
- ✅ **可视化编辑**: UI直接配置和预览

这个设计完全满足了实际MPAC系统的灵活性需求！
