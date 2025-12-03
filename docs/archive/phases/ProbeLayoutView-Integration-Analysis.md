# 现有探头界面与OTA映射器集成方案

## 📋 现有"探头与暗室配置"界面分析

### 当前实现概述

**位置**: `gui/src/App.tsx` → Section: `probeManager`
**核心组件**: `ProbeLayoutView.tsx`

### 组件架构

```typescript
// 现有数据模型 (gui/src/types/api.ts)
export type Probe = {
  id: string           // 'P-01' 到 'P-32'
  ring: string         // '上层'/'中层'/'下层'
  polarization: string // 'V/H' (双极化)
  position: string     // '(x, y, z)m' - 笛卡尔坐标字符串
}
```

### 现有功能清单

#### 1. **ProbeLayoutView 组件**

**可视化能力**:
```typescript
ProbeLayoutView({
  probes: Probe[],
  selectedId: string,
  onSelect: (id: string) => void
})
```

**特性**:
- ✅ **俯视图** (Top View): X-Y 平面投影，显示水平分布
- ✅ **侧视图** (Side View): X-Z 平面投影，显示垂直分布
- ✅ **颜色编码**: 按层级着色（上层=青色，中层=紫色，下层=橙色）
- ✅ **交互选择**: 点击探头高亮显示
- ✅ **自动缩放**: 根据探头位置动态调整坐标轴

**坐标系统**:
```
笛卡尔坐标系 (X, Y, Z)
- 原点: 暗室中心
- X轴: 水平向右（正东）
- Y轴: 水平向前（正北）
- Z轴: 垂直向上
- 单位: 米 (m)
```

#### 2. **探头配置管理**

**CRUD 操作**:
```typescript
// Mock API (gui/src/api/mockDatabase.ts)
- getProbes(): ProbesResponse
- setProbes(probes: Probe[]): ProbesResponse
- createProbe(probe: Probe): Probe
- updateProbe(id: string, payload: Partial<Probe>): Probe | null
- deleteProbe(id: string): boolean
```

**导入/导出功能**:
```typescript
// App.tsx
- handleExportLayout(): 导出为JSON文件
- handleImportFile(file: File): 从JSON导入自定义布局
- handleReplaceLay out(): 替换当前布局
```

#### 3. **现有探头配置**

**默认32探头配置**:
```typescript
const probes: Probe[] = [
  // 上层 (z=1.0m): 8个探头，均匀分布在圆周
  { id: 'P-01', ring: '上层', polarization: 'V/H', position: '(2.50, 0.00, 1.00)m' },
  { id: 'P-02', ring: '上层', polarization: 'V/H', position: '(1.77, 1.77, 1.00)m' },
  // ...

  // 中层 (z=0.0m): 16个探头，均匀分布在圆周
  { id: 'P-09', ring: '中层', polarization: 'V/H', position: '(2.50, 0.00, 0.00)m' },
  // ...

  // 下层 (z=-1.0m): 8个探头，部分分布
  { id: 'P-25', ring: '下层', polarization: 'V/H', position: '(2.31, 0.96, -1.00)m' },
  // ...
]
```

**几何特征**:
- **阵列类型**: 球形（近似）
- **半径**: 约2.5米
- **总探头数**: 32
- **极化**: 全部为V/H双极化
- **分布**: 3层（上、中、下）

#### 4. **校准任务队列**

**功能**:
```typescript
const calibrationTasks = [
  { title: 'S参数全频段扫描', status: 'waiting' },
  { title: '探头间互耦测量', status: 'waiting' },
  { title: '相位一致性校准', status: 'waiting' },
  { title: '静区均匀性验证', status: 'waiting' },
]
```

---

## 🔗 OTA映射器集成策略

### 数据模型对比

| 维度 | 现有模型 (Probe) | OTA映射器输出 (ProbeConfig) | 需要转换 |
|------|------------------|------------------------------|----------|
| **坐标系** | 笛卡尔 (x, y, z) | 球坐标 (θ, φ, r) | ✅ 是 |
| **位置表示** | 字符串 `"(x, y, z)m"` | 对象 `{theta, phi, r}` | ✅ 是 |
| **极化** | 字符串 `"V/H"` | 枚举 `'V' \| 'H'` | ⚠️ 需拆分 |
| **权重** | ❌ 无 | ✅ `{magnitude, phase}` | ✅ 扩展 |
| **使能状态** | ❌ 无 | ✅ `enabled: boolean` | ✅ 扩展 |

### 转换方案

#### 方案 1: 扩展现有 Probe 类型（推荐）

```typescript
// gui/src/types/api.ts

// 保持向后兼容的基础类型
export type Probe = {
  id: string
  ring: string
  polarization: string
  position: string
}

// 扩展类型 - 包含OTA权重信息
export type ProbeWithOTA = Probe & {
  // OTA特有字段
  weight?: {
    magnitude: number  // 幅度 (0-1)
    phase: number      // 相位 (度)
  }
  enabled?: boolean    // 是否启用

  // 球坐标（备用）
  sphericalPosition?: {
    theta: number      // 方位角 (度)
    phi: number        // 仰角 (度)
    r: number          // 半径 (米)
  }
}
```

**优点**:
- ✅ 向后兼容现有代码
- ✅ 可选字段，不影响现有功能
- ✅ 类型安全

**缺点**:
- ⚠️ 数据模型略显冗余

#### 方案 2: 创建独立的 OTAProbe 类型

```typescript
// gui/src/types/roadTest/otaMapper.ts (已有)

export interface ProbeConfig {
  id: number
  position: {
    theta: number
    phi: number
    r: number
  }
  polarization: 'V' | 'H' | 'LHCP' | 'RHCP'
  weight: {
    magnitude: number
    phase: number
  }
  enabled: boolean
}

// 转换函数
export function convertOTAProbeToLegacyProbe(
  otaProbe: ProbeConfig
): ProbeWithOTA {
  const cartesian = sphericalToCartesian(
    otaProbe.position.theta,
    otaProbe.position.phi,
    otaProbe.position.r
  )

  return {
    id: `P-${String(otaProbe.id).padStart(2, '0')}`,
    ring: determineRing(cartesian.z),
    polarization: otaProbe.polarization,
    position: `(${cartesian.x.toFixed(2)}, ${cartesian.y.toFixed(2)}, ${cartesian.z.toFixed(2)})m`,
    weight: otaProbe.weight,
    enabled: otaProbe.enabled,
    sphericalPosition: otaProbe.position,
  }
}
```

---

## 🔧 坐标转换实现

### 球坐标 ↔ 笛卡尔坐标转换

```typescript
// gui/src/utils/coordinateConverter.ts

/**
 * 球坐标系定义（ISO 80000-2标准）
 * - theta (θ): 方位角，从+X轴逆时针旋转，范围 [0, 360)°
 * - phi (φ): 仰角，从+Z轴向下，范围 [0, 180]°
 * - r: 半径，范围 [0, ∞)
 */

export interface SphericalCoordinates {
  theta: number  // 方位角 (degrees)
  phi: number    // 仰角 (degrees)
  r: number      // 半径 (meters)
}

export interface CartesianCoordinates {
  x: number      // 米
  y: number      // 米
  z: number      // 米
}

/**
 * 球坐标转笛卡尔坐标
 */
export function sphericalToCartesian(
  theta: number,
  phi: number,
  r: number
): CartesianCoordinates {
  const thetaRad = (theta * Math.PI) / 180
  const phiRad = (phi * Math.PI) / 180

  return {
    x: r * Math.sin(phiRad) * Math.cos(thetaRad),
    y: r * Math.sin(phiRad) * Math.sin(thetaRad),
    z: r * Math.cos(phiRad),
  }
}

/**
 * 笛卡尔坐标转球坐标
 */
export function cartesianToSpherical(
  x: number,
  y: number,
  z: number
): SphericalCoordinates {
  const r = Math.sqrt(x * x + y * y + z * z)

  if (r === 0) {
    return { theta: 0, phi: 0, r: 0 }
  }

  const phi = Math.acos(z / r) * (180 / Math.PI)
  let theta = Math.atan2(y, x) * (180 / Math.PI)

  // 确保theta在[0, 360)范围
  if (theta < 0) {
    theta += 360
  }

  return { theta, phi, r }
}

/**
 * 解析位置字符串
 */
export function parsePosition(position: string): CartesianCoordinates | null {
  const match = position.match(/\(([^,]+),\s*([^,]+),\s*([^)]+)\)/)
  if (!match) return null

  return {
    x: parseFloat(match[1]),
    y: parseFloat(match[2]),
    z: parseFloat(match[3]),
  }
}

/**
 * 格式化位置字符串
 */
export function formatPosition(coords: CartesianCoordinates): string {
  return `(${coords.x.toFixed(2)}, ${coords.y.toFixed(2)}, ${coords.z.toFixed(2)})m`
}

/**
 * 根据Z坐标确定层级
 */
export function determineRing(z: number): string {
  if (z > 0.5) return '上层'
  if (z < -0.5) return '下层'
  return '中层'
}
```

---

## 🎨 UI 增强方案

### 1. ProbeLayoutView 扩展 - 权重可视化

```typescript
// gui/src/components/ProbeLayoutView.tsx (扩展版本)

import { useMemo } from 'react'
import type { ProbeWithOTA } from '../types/api'
import './ProbeLayoutView.css'

type Props = {
  probes: ProbeWithOTA[]
  selectedId: string
  onSelect: (id: string) => void
  showWeights?: boolean  // 新增：是否显示权重
}

export default function ProbeLayoutView({
  probes,
  selectedId,
  onSelect,
  showWeights = false
}: Props) {
  // ... 现有代码 ...

  // 新增：权重可视化
  const getProbeOpacity = (probe: ProbeWithOTA): number => {
    if (!showWeights || !probe.weight) return 1.0
    // 根据权重幅度调整透明度
    return 0.3 + probe.weight.magnitude * 0.7
  }

  const getProbeStroke = (probe: ProbeWithOTA): string => {
    if (!showWeights || !probe.weight) return 'none'
    // 根据相位显示边框颜色
    const hue = (probe.weight.phase + 180) % 360  // -180~180° → 0~360°
    return `hsl(${hue}, 100%, 50%)`
  }

  return (
    <div className="probe-layout">
      {/* 俯视图 */}
      <div className="probe-layout__canvas">
        <h3>俯视图 {showWeights && '(权重可视化)'}</h3>
        <svg viewBox="0 0 320 320" className="probe-layout__svg">
          {/* ... 现有网格代码 ... */}

          {parsed.map((probe) => {
            const { x, y } = probe.pos
            const cx = scalePoint(x, maxHorizontal, 320)
            const cy = scalePoint(y, maxHorizontal, 320)
            const color = getRingColor(probe.ringNormalized)
            const isSelected = probe.id === selectedId
            const opacity = getProbeOpacity(probe)
            const stroke = getProbeStroke(probe)

            return (
              <g
                key={probe.id}
                className={isSelected ? 'probe-layout__point--selected' : 'probe-layout__point'}
                transform={`translate(${cx}, ${cy})`}
                onClick={() => onSelect(probe.id)}
              >
                <circle
                  r={12}
                  fill={color}
                  opacity={opacity}
                  stroke={stroke}
                  strokeWidth={stroke !== 'none' ? 3 : 0}
                />
                <text y={4} className="probe-layout__label">
                  {probe.id.replace('P-', '')}
                </text>

                {/* 新增：权重数值显示 */}
                {showWeights && probe.weight && (
                  <text y={20} fontSize="8" textAnchor="middle" fill="#666">
                    {probe.weight.magnitude.toFixed(2)}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>

      {/* 侧视图 - 类似修改 */}
      {/* ... */}

      {/* 新增：权重图例 */}
      {showWeights && (
        <div className="probe-layout__legend">
          <h4>权重可视化说明</h4>
          <ul>
            <li>透明度 = 权重幅度 (0-1)</li>
            <li>边框颜色 = 相位角 (-180° 到 +180°)</li>
          </ul>
          <div className="probe-layout__phase-gradient">
            <div style={{ background: 'linear-gradient(to right, hsl(0, 100%, 50%), hsl(180, 100%, 50%), hsl(360, 100%, 50%))' }} />
            <div className="probe-layout__phase-labels">
              <span>-180°</span>
              <span>0°</span>
              <span>+180°</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

### 2. 探头详情面板扩展

```typescript
// gui/src/components/ProbeDetailPanel.tsx (新组件)

import { Card, Stack, Text, Group, Badge, Table } from '@mantine/core'
import type { ProbeWithOTA } from '../types/api'
import { parsePosition, cartesianToSpherical } from '../utils/coordinateConverter'

type Props = {
  probe: ProbeWithOTA | null
}

export function ProbeDetailPanel({ probe }: Props) {
  if (!probe) {
    return (
      <Card withBorder>
        <Text c="dimmed">请选择一个探头查看详情</Text>
      </Card>
    )
  }

  const cartesian = parsePosition(probe.position)
  const spherical = cartesian ? cartesianToSpherical(cartesian.x, cartesian.y, cartesian.z) : null

  return (
    <Card withBorder>
      <Stack gap="md">
        <Group justify="space-between">
          <Text fw={600} size="lg">{probe.id}</Text>
          {probe.enabled !== undefined && (
            <Badge color={probe.enabled ? 'green' : 'gray'}>
              {probe.enabled ? '已启用' : '已禁用'}
            </Badge>
          )}
        </Group>

        <Table>
          <Table.Tbody>
            <Table.Tr>
              <Table.Td fw={500}>层级</Table.Td>
              <Table.Td>{probe.ring}</Table.Td>
            </Table.Tr>
            <Table.Tr>
              <Table.Td fw={500}>极化</Table.Td>
              <Table.Td>{probe.polarization}</Table.Td>
            </Table.Tr>

            {/* 笛卡尔坐标 */}
            <Table.Tr>
              <Table.Td fw={500}>笛卡尔坐标</Table.Td>
              <Table.Td>
                <Text size="sm" c="dimmed">{probe.position}</Text>
              </Table.Td>
            </Table.Tr>

            {/* 球坐标 */}
            {spherical && (
              <Table.Tr>
                <Table.Td fw={500}>球坐标</Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    θ={spherical.theta.toFixed(1)}°,
                    φ={spherical.phi.toFixed(1)}°,
                    r={spherical.r.toFixed(2)}m
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}

            {/* OTA权重（如果有）*/}
            {probe.weight && (
              <>
                <Table.Tr>
                  <Table.Td fw={500}>权重幅度</Table.Td>
                  <Table.Td>
                    <Text fw={600}>{probe.weight.magnitude.toFixed(3)}</Text>
                  </Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td fw={500}>权重相位</Table.Td>
                  <Table.Td>
                    <Text fw={600}>{probe.weight.phase.toFixed(1)}°</Text>
                  </Table.Td>
                </Table.Tr>
                <Table.Tr>
                  <Table.Td fw={500}>复数形式</Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed" ff="monospace">
                      {formatComplexNumber(probe.weight.magnitude, probe.weight.phase)}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              </>
            )}
          </Table.Tbody>
        </Table>
      </Stack>
    </Card>
  )
}

function formatComplexNumber(magnitude: number, phaseDeg: number): string {
  const phaseRad = (phaseDeg * Math.PI) / 180
  const real = magnitude * Math.cos(phaseRad)
  const imag = magnitude * Math.sin(phaseRad)
  const sign = imag >= 0 ? '+' : ''
  return `${real.toFixed(3)} ${sign} ${imag.toFixed(3)}j`
}
```

---

## 🔄 完整集成流程

### Scenario → OTA Config → Probe Visualization

```typescript
// gui/src/components/VirtualRoadTest/OTATestFlow.tsx

import { useState, useEffect } from 'react'
import { Stack, Button, Stepper, Alert } from '@mantine/core'
import { OTAScenarioMapper } from '../../services/roadTest/OTAScenarioMapper'
import ProbeLayoutView from '../ProbeLayoutView'
import { ProbeDetailPanel } from '../ProbeDetailPanel'
import { convertOTAProbeToLegacyProbe } from '../../utils/coordinateConverter'

export function OTATestFlow({ scenario }: { scenario: RoadTestScenarioDetail }) {
  const [active, setActive] = useState(0)
  const [otaConfig, setOtaConfig] = useState<OTATestConfiguration | null>(null)
  const [probes, setProbes] = useState<ProbeWithOTA[]>([])
  const [selectedProbeId, setSelectedProbeId] = useState<string>('')

  const mapper = new OTAScenarioMapper()

  const handleGenerateOTAConfig = async () => {
    try {
      // 1. 调用OTA映射器（内部会调用ChannelEngine服务）
      const config = await mapper.map(scenario)
      setOtaConfig(config)

      // 2. 转换探头配置为可视化格式
      const convertedProbes = config.probeArray.probes.map(convertOTAProbeToLegacyProbe)
      setProbes(convertedProbes)

      setActive(1)
    } catch (error) {
      console.error('OTA配置生成失败:', error)
    }
  }

  return (
    <Stack gap="xl">
      <Stepper active={active} onStepClick={setActive}>
        <Stepper.Step label="步骤1" description="生成OTA配置">
          <Stack gap="md">
            <Alert>
              场景: {scenario.name}
            </Alert>
            <Button onClick={handleGenerateOTAConfig}>
              生成OTA配置
            </Button>
          </Stack>
        </Stepper.Step>

        <Stepper.Step label="步骤2" description="探头权重可视化">
          {otaConfig && (
            <Stack gap="md">
              <ProbeLayoutView
                probes={probes}
                selectedId={selectedProbeId}
                onSelect={setSelectedProbeId}
                showWeights={true}  // 启用权重可视化
              />
              <ProbeDetailPanel
                probe={probes.find(p => p.id === selectedProbeId) || null}
              />
            </Stack>
          )}
        </Stepper.Step>

        <Stepper.Step label="步骤3" description="下载配置文件">
          {otaConfig && (
            <Button onClick={() => exportOTAConfig(otaConfig)}>
              导出OTA配置 (JSON)
            </Button>
          )}
        </Stepper.Step>
      </Stepper>
    </Stack>
  )
}

function exportOTAConfig(config: OTATestConfiguration) {
  const json = JSON.stringify(config, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `ota-config-${config.metadata.scenarioId}.json`
  a.click()
  URL.revokeObjectURL(url)
}
```

---

## 📊 数据流图

```
┌─────────────────────────────────────────────────────────────┐
│  1. 用户选择场景                                             │
│     RoadTestScenarioDetail (场景001: 北京CBD)                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  2. OTA Scenario Mapper                                     │
│     - 调用 ChannelEngine 服务 (Python)                      │
│     - 输入: scenario, frequency, MIMO config                │
│     - 输出: ProbeConfig[] (球坐标 + 权重)                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 坐标转换层                                               │
│     ProbeConfig → ProbeWithOTA                              │
│     - 球坐标 → 笛卡尔坐标                                    │
│     - 保留权重信息                                           │
│     - 确定层级 (上/中/下层)                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 现有 UI 组件复用                                         │
│     ┌─────────────────────────────────────┐                 │
│     │ ProbeLayoutView (扩展版)            │                 │
│     │ - 俯视图 + 侧视图                   │                 │
│     │ - 权重透明度可视化                  │                 │
│     │ - 相位颜色编码                      │                 │
│     └─────────────────────────────────────┘                 │
│     ┌─────────────────────────────────────┐                 │
│     │ ProbeDetailPanel (新组件)           │                 │
│     │ - 笛卡尔 + 球坐标显示                │                 │
│     │ - 权重幅度 + 相位                    │                 │
│     │ - 复数形式                           │                 │
│     └─────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ 实施计划

### Phase 1: 坐标转换工具 (1天)
- [ ] 创建 `coordinateConverter.ts`
- [ ] 实现球坐标 ↔ 笛卡尔转换
- [ ] 单元测试验证精度

### Phase 2: 数据模型扩展 (1天)
- [ ] 扩展 `Probe` 类型为 `ProbeWithOTA`
- [ ] 创建 `convertOTAProbeToLegacyProbe` 函数
- [ ] 更新 TypeScript 类型定义

### Phase 3: UI 组件增强 (2-3天)
- [ ] 扩展 `ProbeLayoutView` 支持权重可视化
- [ ] 创建 `ProbeDetailPanel` 组件
- [ ] 添加权重图例和说明

### Phase 4: 集成测试 (1天)
- [ ] 端到端流程测试
- [ ] 坐标转换精度验证
- [ ] 权重可视化效果验证

---

## 🎯 总结

### 关键优势

1. ✅ **零重复开发**: 完全复用现有 ProbeLayoutView 组件
2. ✅ **向后兼容**: 扩展数据模型不影响现有功能
3. ✅ **双坐标系支持**: 同时提供球坐标和笛卡尔坐标
4. ✅ **权重可视化**: 直观展示探头激励强度和相位
5. ✅ **无缝集成**: 与OTA映射器完美配合

### 技术亮点

- **坐标转换**: 高精度球坐标 ↔ 笛卡尔转换
- **权重编码**: 透明度 + 颜色双重可视化
- **类型安全**: TypeScript 全程类型保护
- **渐进增强**: 可选字段不破坏现有功能

### 最终用户体验

```
用户操作流程:
1. 选择虚拟路测场景（如"北京CBD早高峰"）
2. 点击"生成OTA配置"按钮
3. 系统自动调用ChannelEngine计算探头权重
4. 实时显示探头空间布局（俯视图 + 侧视图）
5. 透明度表示权重幅度，边框颜色表示相位
6. 点击探头查看详细参数（坐标、权重、复数形式）
7. 导出OTA配置文件供测试执行
```

这个方案充分利用了现有的探头界面，只需少量扩展即可支持OTA权重可视化！
