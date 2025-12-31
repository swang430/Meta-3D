# 虚拟场景库设计文档

**文档编号**: DESIGN-005
**版本**: v1.0
**创建日期**: 2025-11-16
**所属子系统**: 虚拟测试子系统
**优先级**: P0

---

## 1. 概述

### 1.1 目标

虚拟场景库（Virtual Scenario Library）是Meta-3D系统的核心组件，提供标准化、可复用的测试场景管理能力。主要目标包括：

- ✅ **标准化场景管理**: 管理3GPP和行业标准测试场景
- ✅ **场景参数化**: 支持场景参数的灵活配置和变体管理
- ✅ **版本控制**: 场景的版本管理和历史追溯
- ✅ **导入导出**: 场景的跨系统共享和迁移
- ✅ **场景验证**: 自动验证场景配置的有效性

### 1.2 范围

**包含**:
- 3GPP TR 38.901标准场景（UMa/UMi/RMa/InH）
- CDL/TDL簇模型场景
- 行业标准场景（CTIA/GCF/NGMN）
- 自定义场景创建和管理
- 场景模板和变体

**不包含**:
- 自定义场景的图形化编辑器（见Custom-Scenario-Design.md）
- 场景的实时仿真执行（见ChannelEgine-Integration-Plan.md）

---

## 2. 架构设计

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────┐
│              Scenario Library UI Layer                  │
│  - ScenarioSelector  - ScenarioManager  - ScenarioEditor│
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│           Scenario Library Business Logic               │
│  - ScenarioService  - ValidationService  - VersionControl│
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│            Scenario Library Data Access                 │
│  - ScenarioRepository  - TemplateRepository             │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│                  Database Layer                         │
│  PostgreSQL: Metadata | File Storage: Scenario Data     │
└─────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 ScenarioService

**职责**: 场景的增删改查、验证、版本管理

```typescript
class ScenarioService {
  // CRUD操作
  async createScenario(scenario: ScenarioCreateRequest): Promise<Scenario>
  async getScenario(id: string): Promise<Scenario>
  async updateScenario(id: string, updates: ScenarioUpdateRequest): Promise<Scenario>
  async deleteScenario(id: string): Promise<void>
  async listScenarios(filter: ScenarioFilter): Promise<Scenario[]>

  // 版本管理
  async createVersion(scenarioId: string, version: string): Promise<ScenarioVersion>
  async getVersionHistory(scenarioId: string): Promise<ScenarioVersion[]>
  async rollbackToVersion(scenarioId: string, versionId: string): Promise<Scenario>

  // 验证
  async validateScenario(scenario: Scenario): Promise<ValidationResult>

  // 导入导出
  async exportScenario(id: string, format: 'json' | 'yaml'): Promise<string>
  async importScenario(data: string, format: 'json' | 'yaml'): Promise<Scenario>
}
```

#### 2.2.2 TemplateRepository

**职责**: 场景模板管理和复用

```typescript
interface TemplateRepository {
  // 标准模板
  getStandardTemplates(): Promise<ScenarioTemplate[]>
  getTemplateByType(type: ScenarioType): Promise<ScenarioTemplate[]>

  // 自定义模板
  createTemplate(template: ScenarioTemplate): Promise<ScenarioTemplate>
  updateTemplate(id: string, updates: Partial<ScenarioTemplate>): Promise<ScenarioTemplate>
  deleteTemplate(id: string): Promise<void>

  // 模板应用
  applyTemplate(templateId: string, params: TemplateParams): Promise<Scenario>
}
```

---

## 3. 数据模型

### 3.1 核心实体

#### Scenario (场景)

```typescript
interface Scenario {
  // 基础信息
  id: string                    // UUID
  name: string                  // 场景名称
  description?: string          // 场景描述
  type: ScenarioType           // 'standard' | 'custom' | 'template'
  category: ScenarioCategory   // '3gpp' | 'ctia' | 'gcf' | 'custom'

  // 版本信息
  version: string              // 语义化版本号 (e.g., "1.2.0")
  createdAt: Date
  updatedAt: Date
  createdBy: string            // 用户ID
  lastModifiedBy: string

  // 配置数据
  configuration: ScenarioConfiguration

  // 元数据
  tags: string[]               // 标签，用于搜索和分类
  status: 'draft' | 'published' | 'archived'
  isReadOnly: boolean          // 标准场景为只读

  // 关联信息
  parentTemplateId?: string    // 如果从模板创建
  derivedFromId?: string       // 如果从其他场景派生
}
```

#### ScenarioConfiguration (场景配置)

```typescript
interface ScenarioConfiguration {
  // 信道模型配置
  channelModel: {
    scenarioType: '3GPP-UMa' | '3GPP-UMi' | '3GPP-RMa' | '3GPP-InH'
    clusterModel?: 'CDL-A' | 'CDL-B' | 'CDL-C' | 'CDL-D' | 'CDL-E' |
                   'TDL-A' | 'TDL-B' | 'TDL-C'
    losCondition?: 'LOS' | 'NLOS' | 'auto'
  }

  // 环境参数
  environmentParams: {
    frequency: FrequencyRange         // 频率范围
    carrierFrequencyMHz: number       // 中心频率
    bandwidth: number                 // 带宽 (MHz)

    // 3GPP参数
    distance?: number                 // BS到UE距离 (m)
    height?: {
      bs: number                      // BS高度 (m)
      ue: number                      // UE高度 (m)
    }

    // 大尺度参数 (LSP)
    useDeterministicLSP: boolean      // 是否使用确定性LSP
    lspOverrides?: {
      delaySpread?: number            // RMS时延扩展覆盖值
      angularSpread?: number          // 角度扩展覆盖值
      shadowFading?: number           // 阴影衰落覆盖值
    }
  }

  // 运动配置
  motionProfile?: {
    enabled: boolean
    type: 'static' | 'linear' | 'circular' | 'custom'
    speed?: number                    // m/s
    trajectory?: TrajectoryPoint[]    // 自定义轨迹
  }

  // MIMO配置
  mimoConfig: {
    numTxAntennas: number
    numRxAntennas: number
    txAntennaConfig: AntennaConfiguration
    rxAntennaConfig: AntennaConfiguration
  }

  // 探头阵列配置（用于OTA测试）
  probeArrayConfig?: {
    numProbes: number
    probeLayout: 'ring' | 'multi-ring' | 'custom'
    probePositions: ProbePosition[]
  }

  // 校准参数
  calibrationRequirements?: {
    required: boolean
    calibrationType: 'probe' | 'channel' | 'system'[]
    maxCalibrationAge: number         // 天数
  }
}
```

#### ScenarioTemplate (场景模板)

```typescript
interface ScenarioTemplate {
  id: string
  name: string
  description: string
  category: ScenarioCategory

  // 模板配置（带参数占位符）
  configurationTemplate: ScenarioConfigurationTemplate

  // 参数定义
  parameters: TemplateParameter[]

  // 验证规则
  validationRules: ValidationRule[]

  // 元数据
  tags: string[]
  isBuiltIn: boolean               // 内置模板不可修改
  createdAt: Date
  updatedAt: Date
}

interface TemplateParameter {
  name: string                     // 参数名称
  type: 'number' | 'string' | 'enum' | 'boolean'
  defaultValue: any
  required: boolean

  // 验证约束
  constraints?: {
    min?: number
    max?: number
    step?: number
    enum?: any[]
    regex?: string
  }

  description: string
  unit?: string
}
```

#### ScenarioVersion (场景版本)

```typescript
interface ScenarioVersion {
  id: string
  scenarioId: string
  version: string                  // 版本号
  snapshot: Scenario               // 完整的场景快照

  // 变更信息
  changeLog: string
  changedBy: string
  changedAt: Date

  // 变更摘要
  changeSummary: {
    added: string[]
    modified: string[]
    removed: string[]
  }
}
```

### 3.2 数据库Schema

#### scenarios表

```sql
CREATE TABLE scenarios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  description TEXT,
  type VARCHAR(50) NOT NULL,
  category VARCHAR(50) NOT NULL,
  version VARCHAR(20) NOT NULL,

  configuration JSONB NOT NULL,

  tags TEXT[] DEFAULT '{}',
  status VARCHAR(20) DEFAULT 'draft',
  is_read_only BOOLEAN DEFAULT false,

  parent_template_id UUID REFERENCES scenario_templates(id),
  derived_from_id UUID REFERENCES scenarios(id),

  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_by VARCHAR(255) NOT NULL,
  last_modified_by VARCHAR(255) NOT NULL,

  -- 索引
  CONSTRAINT scenarios_name_version_unique UNIQUE (name, version)
);

-- 索引
CREATE INDEX idx_scenarios_category ON scenarios(category);
CREATE INDEX idx_scenarios_tags ON scenarios USING GIN(tags);
CREATE INDEX idx_scenarios_status ON scenarios(status);
```

#### scenario_templates表

```sql
CREATE TABLE scenario_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL UNIQUE,
  description TEXT,
  category VARCHAR(50) NOT NULL,

  configuration_template JSONB NOT NULL,
  parameters JSONB NOT NULL,
  validation_rules JSONB NOT NULL,

  tags TEXT[] DEFAULT '{}',
  is_built_in BOOLEAN DEFAULT false,

  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### scenario_versions表

```sql
CREATE TABLE scenario_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id UUID REFERENCES scenarios(id) ON DELETE CASCADE,
  version VARCHAR(20) NOT NULL,

  snapshot JSONB NOT NULL,
  change_log TEXT,

  changed_by VARCHAR(255) NOT NULL,
  changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  change_summary JSONB,

  CONSTRAINT scenario_versions_unique UNIQUE (scenario_id, version)
);

CREATE INDEX idx_scenario_versions_scenario_id ON scenario_versions(scenario_id);
```

---

## 4. API设计

### 4.1 RESTful API

#### 4.1.1 场景管理

```
# 创建场景
POST /api/v1/scenarios
Request Body: ScenarioCreateRequest
Response: Scenario

# 获取场景
GET /api/v1/scenarios/{id}
Response: Scenario

# 更新场景
PATCH /api/v1/scenarios/{id}
Request Body: ScenarioUpdateRequest
Response: Scenario

# 删除场景
DELETE /api/v1/scenarios/{id}
Response: 204 No Content

# 列出场景
GET /api/v1/scenarios
Query Parameters:
  - category: ScenarioCategory
  - type: ScenarioType
  - tags: string[]
  - status: string
  - search: string
  - page: number
  - limit: number
Response: PaginatedResponse<Scenario>
```

#### 4.1.2 版本管理

```
# 创建新版本
POST /api/v1/scenarios/{id}/versions
Request Body: { version: string, changeLog: string }
Response: ScenarioVersion

# 获取版本历史
GET /api/v1/scenarios/{id}/versions
Response: ScenarioVersion[]

# 回滚到指定版本
POST /api/v1/scenarios/{id}/rollback
Request Body: { versionId: string }
Response: Scenario
```

#### 4.1.3 模板管理

```
# 获取标准模板
GET /api/v1/scenario-templates/standard
Response: ScenarioTemplate[]

# 创建自定义模板
POST /api/v1/scenario-templates
Request Body: TemplateCreateRequest
Response: ScenarioTemplate

# 应用模板
POST /api/v1/scenario-templates/{id}/apply
Request Body: { params: TemplateParams }
Response: Scenario
```

#### 4.1.4 导入导出

```
# 导出场景
GET /api/v1/scenarios/{id}/export
Query Parameters:
  - format: 'json' | 'yaml'
Response: File Download

# 导入场景
POST /api/v1/scenarios/import
Request Body: FormData (file upload)
Response: Scenario
```

### 4.2 GraphQL API（可选）

```graphql
type Scenario {
  id: ID!
  name: String!
  description: String
  type: ScenarioType!
  category: ScenarioCategory!
  version: String!
  configuration: ScenarioConfiguration!
  tags: [String!]!
  status: ScenarioStatus!
  createdAt: DateTime!
  updatedAt: DateTime!
  createdBy: User!
  lastModifiedBy: User!
  versions: [ScenarioVersion!]!
}

type Query {
  scenario(id: ID!): Scenario
  scenarios(filter: ScenarioFilter!): ScenarioPaginatedResult!
  scenarioTemplates: [ScenarioTemplate!]!
}

type Mutation {
  createScenario(input: ScenarioCreateInput!): Scenario!
  updateScenario(id: ID!, input: ScenarioUpdateInput!): Scenario!
  deleteScenario(id: ID!): Boolean!

  createScenarioVersion(scenarioId: ID!, version: String!, changeLog: String!): ScenarioVersion!
  rollbackScenario(scenarioId: ID!, versionId: ID!): Scenario!
}
```

---

## 5. 标准场景库内容

### 5.1 3GPP标准场景

#### UMa (Urban Macro) 场景

```typescript
const UMa_3GPP_Scenarios: ScenarioTemplate[] = [
  {
    name: "3GPP UMa LOS - 3.5GHz",
    category: "3gpp",
    configurationTemplate: {
      channelModel: {
        scenarioType: "3GPP-UMa",
        losCondition: "LOS"
      },
      environmentParams: {
        carrierFrequencyMHz: 3500,
        bandwidth: 100,
        distance: { min: 35, max: 500 },
        height: { bs: 25, ue: 1.5 }
      }
    },
    parameters: [
      {
        name: "frequency",
        type: "number",
        defaultValue: 3500,
        constraints: { min: 2000, max: 6000 },
        unit: "MHz"
      },
      {
        name: "distance",
        type: "number",
        defaultValue: 100,
        constraints: { min: 35, max: 500 },
        unit: "m"
      }
    ]
  },

  {
    name: "3GPP UMa NLOS - 3.5GHz",
    category: "3gpp",
    configurationTemplate: {
      channelModel: {
        scenarioType: "3GPP-UMa",
        losCondition: "NLOS"
      },
      environmentParams: {
        carrierFrequencyMHz: 3500,
        bandwidth: 100,
        distance: { min: 35, max: 500 },
        height: { bs: 25, ue: 1.5 }
      }
    }
  }
]
```

#### CDL模型场景

```typescript
const CDL_Scenarios: ScenarioTemplate[] = [
  {
    name: "CDL-A - Low Delay Spread",
    description: "LOS scenario with low delay spread",
    category: "3gpp",
    configurationTemplate: {
      channelModel: {
        scenarioType: "3GPP-UMa",
        clusterModel: "CDL-A",
        losCondition: "LOS"
      },
      environmentParams: {
        carrierFrequencyMHz: 3500,
        useDeterministicLSP: true,
        lspOverrides: {
          delaySpread: 30e-9  // 30ns
        }
      }
    }
  },

  {
    name: "CDL-C - High Delay Spread NLOS",
    description: "NLOS scenario with high delay spread",
    category: "3gpp",
    configurationTemplate: {
      channelModel: {
        scenarioType: "3GPP-UMa",
        clusterModel: "CDL-C",
        losCondition: "NLOS"
      },
      environmentParams: {
        carrierFrequencyMHz: 3500,
        useDeterministicLSP: true,
        lspOverrides: {
          delaySpread: 370e-9  // 370ns
        }
      }
    }
  }
]
```

### 5.2 行业标准场景

#### CTIA标准

```typescript
const CTIA_OTA_Scenarios: ScenarioTemplate[] = [
  {
    name: "CTIA OTA TRP Test",
    category: "ctia",
    description: "Total Radiated Power measurement per CTIA v3.9",
    configurationTemplate: {
      channelModel: {
        scenarioType: "3GPP-UMi",
        losCondition: "LOS"
      },
      environmentParams: {
        carrierFrequencyMHz: 1900,  // PCS band
        bandwidth: 10
      },
      probeArrayConfig: {
        numProbes: 32,
        probeLayout: "multi-ring"
      },
      calibrationRequirements: {
        required: true,
        calibrationType: ["probe", "system"],
        maxCalibrationAge: 30
      }
    }
  }
]
```

---

## 6. 场景验证

### 6.1 验证规则

```typescript
interface ValidationRule {
  ruleId: string
  name: string
  severity: 'error' | 'warning' | 'info'
  validator: (scenario: Scenario) => ValidationResult
}

// 示例验证规则
const FrequencyRangeValidator: ValidationRule = {
  ruleId: "freq-range-check",
  name: "Frequency Range Validation",
  severity: "error",
  validator: (scenario) => {
    const freq = scenario.configuration.environmentParams.carrierFrequencyMHz

    if (freq < 450 || freq > 100000) {
      return {
        valid: false,
        errors: [{
          field: "environmentParams.carrierFrequencyMHz",
          message: `Frequency ${freq} MHz is out of valid range (450-100000 MHz)`
        }]
      }
    }

    return { valid: true, errors: [] }
  }
}

const ProbeCountValidator: ValidationRule = {
  ruleId: "probe-count-check",
  name: "Probe Count Validation",
  severity: "error",
  validator: (scenario) => {
    const probeConfig = scenario.configuration.probeArrayConfig

    if (!probeConfig) return { valid: true, errors: [] }

    if (probeConfig.numProbes < 8 || probeConfig.numProbes > 64) {
      return {
        valid: false,
        errors: [{
          field: "probeArrayConfig.numProbes",
          message: `Probe count ${probeConfig.numProbes} is out of range (8-64)`
        }]
      }
    }

    if (probeConfig.probePositions.length !== probeConfig.numProbes) {
      return {
        valid: false,
        errors: [{
          field: "probeArrayConfig.probePositions",
          message: `Probe positions count (${probeConfig.probePositions.length}) ` +
                   `does not match numProbes (${probeConfig.numProbes})`
        }]
      }
    }

    return { valid: true, errors: [] }
  }
}
```

### 6.2 验证流程

```typescript
class ScenarioValidator {
  private rules: ValidationRule[] = []

  registerRule(rule: ValidationRule): void {
    this.rules.push(rule)
  }

  async validate(scenario: Scenario): Promise<ValidationResult> {
    const errors: ValidationError[] = []
    const warnings: ValidationError[] = []
    const info: ValidationError[] = []

    for (const rule of this.rules) {
      const result = rule.validator(scenario)

      if (!result.valid) {
        switch (rule.severity) {
          case 'error':
            errors.push(...result.errors)
            break
          case 'warning':
            warnings.push(...result.errors)
            break
          case 'info':
            info.push(...result.errors)
            break
        }
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
      info
    }
  }
}
```

---

## 7. UI组件设计

### 7.1 场景选择器增强

```typescript
// 扩展现有的ScenarioSelector组件
interface ScenarioSelectorProps {
  // 现有props
  value: ScenarioConfig
  onChange: (config: ScenarioConfig) => void

  // 新增props
  enableLibrary?: boolean        // 启用场景库
  enableFavorites?: boolean      // 启用收藏功能
  onSaveAsTemplate?: () => void  // 保存为模板回调
}

function ScenarioSelector({
  value,
  onChange,
  enableLibrary = true,
  enableFavorites = false
}: ScenarioSelectorProps) {
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [scenarios, setScenarios] = useState<Scenario[]>([])

  // 从场景库加载
  const loadFromLibrary = async (scenarioId: string) => {
    const scenario = await scenarioService.getScenario(scenarioId)
    onChange(scenario.configuration)
    setLibraryOpen(false)
  }

  return (
    <Stack>
      {/* 现有的快速预设 */}
      <Select
        label="快速预设"
        data={SCENARIO_PRESETS}
        onChange={applyPreset}
      />

      {/* 新增：场景库按钮 */}
      {enableLibrary && (
        <Button
          leftSection={<IconFolder />}
          onClick={() => setLibraryOpen(true)}
        >
          从场景库选择
        </Button>
      )}

      {/* 场景库模态框 */}
      <Modal
        opened={libraryOpen}
        onClose={() => setLibraryOpen(false)}
        title="场景库"
        size="xl"
      >
        <ScenarioLibraryBrowser
          onSelect={loadFromLibrary}
        />
      </Modal>
    </Stack>
  )
}
```

### 7.2 场景库浏览器

```typescript
function ScenarioLibraryBrowser({ onSelect }: {
  onSelect: (scenarioId: string) => void
}) {
  const [filter, setFilter] = useState<ScenarioFilter>({})
  const [scenarios, setScenarios] = useState<Scenario[]>([])

  return (
    <Stack>
      {/* 过滤器 */}
      <Group>
        <Select
          label="分类"
          data={[
            { value: '3gpp', label: '3GPP标准' },
            { value: 'ctia', label: 'CTIA' },
            { value: 'gcf', label: 'GCF' },
            { value: 'custom', label: '自定义' }
          ]}
          onChange={(val) => setFilter({ ...filter, category: val })}
        />

        <TextInput
          label="搜索"
          placeholder="搜索场景名称或标签"
          onChange={(e) => setFilter({ ...filter, search: e.target.value })}
        />
      </Group>

      {/* 场景列表 */}
      <Table>
        <thead>
          <tr>
            <th>名称</th>
            <th>类型</th>
            <th>频率</th>
            <th>版本</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map(scenario => (
            <tr key={scenario.id}>
              <td>{scenario.name}</td>
              <td><Badge>{scenario.category}</Badge></td>
              <td>{scenario.configuration.environmentParams.carrierFrequencyMHz} MHz</td>
              <td>{scenario.version}</td>
              <td>
                <Button size="xs" onClick={() => onSelect(scenario.id)}>
                  选择
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Stack>
  )
}
```

---

## 8. 实现计划

### 8.1 Phase 1: 基础场景库 (1周)

**目标**: 建立基础的场景CRUD功能

- [ ] 数据库Schema设计和迁移
- [ ] ScenarioService实现（基础CRUD）
- [ ] RESTful API实现
- [ ] 基础UI集成（ScenarioSelector增强）

**验收标准**:
- 可以创建、读取、更新、删除场景
- UI可以从场景库选择场景

### 8.2 Phase 2: 标准场景和模板 (1周)

**目标**: 预置标准场景库

- [ ] 创建3GPP标准场景（UMa/UMi/RMa/InH + LOS/NLOS）
- [ ] 创建CDL/TDL场景
- [ ] 创建CTIA/GCF标准场景
- [ ] 模板系统实现
- [ ] 参数化场景支持

**验收标准**:
- 至少20个标准场景可用
- 模板系统可以正常工作

### 8.3 Phase 3: 版本控制和验证 (1周)

**目标**: 完善场景管理功能

- [ ] 版本控制实现
- [ ] 场景验证系统
- [ ] 导入导出功能
- [ ] 场景库浏览器UI

**验收标准**:
- 场景版本可追溯
- 无效场景被拒绝
- 可以导入导出场景

---

## 9. 测试策略

### 9.1 单元测试

```typescript
describe('ScenarioService', () => {
  let service: ScenarioService
  let repository: ScenarioRepository

  beforeEach(() => {
    repository = new MockScenarioRepository()
    service = new ScenarioService(repository)
  })

  describe('createScenario', () => {
    it('应该创建有效的场景', async () => {
      const request = {
        name: "Test Scenario",
        type: "custom",
        configuration: { /* ... */ }
      }

      const scenario = await service.createScenario(request)

      expect(scenario.id).toBeDefined()
      expect(scenario.name).toBe(request.name)
    })

    it('应该拒绝无效的场景', async () => {
      const request = {
        name: "",
        type: "custom",
        configuration: { /* invalid config */ }
      }

      await expect(service.createScenario(request)).rejects.toThrow()
    })
  })

  describe('validateScenario', () => {
    it('应该验证频率范围', async () => {
      const scenario = createTestScenario({
        environmentParams: { carrierFrequencyMHz: 999999 }
      })

      const result = await service.validateScenario(scenario)

      expect(result.valid).toBe(false)
      expect(result.errors).toHaveLength(1)
      expect(result.errors[0].field).toBe('environmentParams.carrierFrequencyMHz')
    })
  })
})
```

### 9.2 集成测试

```typescript
describe('Scenario Library Integration', () => {
  it('端到端：创建→保存→加载→应用场景', async () => {
    // 1. 创建场景
    const scenario = await scenarioService.createScenario({
      name: "E2E Test Scenario",
      type: "custom",
      configuration: testConfig
    })

    // 2. 验证已保存
    const loaded = await scenarioService.getScenario(scenario.id)
    expect(loaded).toMatchObject(scenario)

    // 3. 应用到测试
    const testPlan = await testPlanService.createTestPlan({
      scenario: loaded.configuration
    })

    expect(testPlan.scenarioId).toBe(scenario.id)
  })
})
```

---

## 10. 未来扩展

### 10.1 场景推荐系统

基于测试历史和DUT特性，推荐相关场景：

```typescript
interface ScenarioRecommendation {
  scenario: Scenario
  relevanceScore: number
  reason: string
}

class ScenarioRecommendationEngine {
  async getRecommendations(
    dutInfo: DUTInfo,
    testHistory: TestResult[]
  ): Promise<ScenarioRecommendation[]> {
    // 基于DUT频段推荐
    // 基于历史测试推荐
    // 基于相似DUT的测试推荐
  }
}
```

### 10.2 场景性能指标

记录和分析场景的测试性能：

```typescript
interface ScenarioMetrics {
  scenarioId: string
  usageCount: number
  averageExecutionTime: number
  successRate: number
  commonIssues: Issue[]
}
```

### 10.3 协作和分享

多用户协作编辑场景，场景社区分享：

```typescript
interface ScenarioCollaboration {
  shareScenario(scenarioId: string, users: string[]): Promise<void>
  forkScenario(scenarioId: string): Promise<Scenario>
  mergeChanges(scenarioId: string, changes: ScenarioChanges): Promise<Scenario>
}
```

---

## 11. 参考文献

- 3GPP TR 38.901 V19.0.0 - Study on channel model for frequencies from 0.5 to 100 GHz
- CTIA OTA Test Plan v3.9
- GCF CC Device Test Case Database
- NGMN 5G White Paper

---

**文档状态**: ✅ 已完成
**审核状态**: 待审核
**最后更新**: 2025-11-16
