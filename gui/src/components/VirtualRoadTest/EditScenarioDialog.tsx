/**
 * Edit Scenario Dialog
 *
 * Form for editing existing test scenarios
 */

import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Modal,
  Button,
  Stack,
  TextInput,
  Textarea,
  Select,
  NumberInput,
  Group,
  Alert,
  Loader,
  SimpleGrid,
  Card,
  Text,
  Badge,
  Tabs,
} from '@mantine/core'
import {
  IconAlertCircle,
  IconCheck,
  IconSettings,
} from '@tabler/icons-react'
import { updateScenario } from '../../api/roadTestService'
import type { ScenarioSummary, RoadTestScenario, StepConfiguration, TestMode } from '../../types/roadTest'
import { StepConfigurationEditor } from './StepConfigurationEditor'

interface Props {
  opened: boolean
  onClose: () => void
  scenario: ScenarioSummary | null
  testMode?: TestMode
}

const CATEGORIES = [
  { value: 'standard', label: '⭐ Standard (3GPP/CTIA)' },
  { value: 'functional', label: '🔧 Functional' },
  { value: 'performance', label: '🚀 Performance' },
  { value: 'environment', label: '🌍 Environment' },
  { value: 'extreme', label: '⚠️ Extreme' },
  { value: 'custom', label: '✏️ Custom' },
]

const NETWORK_TYPES = [
  { value: 'LTE', label: 'LTE' },
  { value: '5G_NR', label: '5G NR' },
]

const CHANNEL_MODELS = [
  { value: 'UMa', label: 'UMa (Urban Macro)' },
  { value: 'UMi', label: 'UMi (Urban Micro)' },
  { value: 'RMa', label: 'RMa (Rural Macro)' },
  { value: 'InH', label: 'InH (Indoor Hotspot)' },
  { value: 'CDL-A', label: 'CDL-A' },
  { value: 'CDL-B', label: 'CDL-B' },
]

export function EditScenarioDialog({ opened, onClose, scenario, testMode }: Props) {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<string | null>('basic')

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    category: 'custom',
    networkType: '5G_NR',
    band: 'n78',
    bandwidth: 100,
    channelModel: 'UMa',
    speed: 50,
    duration: 60,
    stepConfiguration: undefined as StepConfiguration | undefined,
  })

  // Initialize form data when scenario changes
  useEffect(() => {
    if (scenario) {
      setFormData({
        name: scenario.name || '',
        description: scenario.description || '',
        category: scenario.category || 'custom',
        networkType: scenario.network_type || '5G_NR',
        band: scenario.band || 'n78',
        bandwidth: scenario.bandwidth_mhz || 100,
        channelModel: scenario.channel_model || 'UMa',
        speed: scenario.avg_speed_kmh || 50,
        duration: scenario.duration_s || 60,
        stepConfiguration: scenario.step_configuration,
      })
    }
  }, [scenario])

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!scenario) throw new Error('No scenario to update')

      const updates: Partial<RoadTestScenario> = {
        name: formData.name,
        description: formData.description,
        category: formData.category as any,
        tags: [formData.category, formData.channelModel],
        network: {
          type: formData.networkType as any,
          band: formData.band,
          bandwidth_mhz: formData.bandwidth,
          duplex_mode: 'TDD',
          scs_khz: 30,
        },
        route: {
          type: 'generated',
          waypoints: [],
          duration_s: formData.duration,
          total_distance_m: formData.speed * formData.duration,
        },
        environment: {
          type: 'urban_street',
          channel_model: formData.channelModel as any,
          weather: 'clear',
          traffic_density: 'medium',
        },
        // Always send step_configuration (even if empty or null)
        step_configuration: formData.stepConfiguration || {},
      }
      return updateScenario(scenario.id, updates)
    },
    onSuccess: (savedScenario) => {
      queryClient.invalidateQueries({ queryKey: ['scenarios'] })
      // If editing a standard scenario created a new custom scenario,
      // the savedScenario will have a different ID
      if (savedScenario && savedScenario.id !== scenario?.id) {
        console.log(`Created new custom scenario: ${savedScenario.id}`)
      }
      handleClose()
    },
  })

  const handleClose = () => {
    setActiveTab('basic')
    onClose()
  }

  const isFormValid = formData.name.trim().length > 0

  // Check if this is a standard scenario (shouldn't be editable in production)
  const isStandardScenario = scenario?.source === 'standard'

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={`编辑场景: ${scenario?.name || ''}`}
      size="lg"
      centered
    >
      <Stack gap="md">
        {isStandardScenario && (
          <Alert color="yellow" icon={<IconAlertCircle size={16} />}>
            这是一个标准场景。修改后将保存为自定义版本。
          </Alert>
        )}

        {updateMutation.isPending && (
          <Alert color="blue">
            <Group gap="xs">
              <Loader size="sm" />
              <Text>正在保存...</Text>
            </Group>
          </Alert>
        )}

        {updateMutation.isError && (
          <Alert
            icon={<IconAlertCircle size={16} />}
            title="错误"
            color="red"
          >
            保存失败: {(updateMutation.error as Error).message}
          </Alert>
        )}

        {updateMutation.isSuccess && (
          <Alert
            icon={<IconCheck size={16} />}
            title="成功"
            color="green"
          >
            场景已更新！
          </Alert>
        )}

        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="basic">基本信息</Tabs.Tab>
            <Tabs.Tab value="network">网络配置</Tabs.Tab>
            <Tabs.Tab value="environment">环境设置</Tabs.Tab>
            <Tabs.Tab value="steps" leftSection={<IconSettings size={14} />}>
              测试步骤配置
            </Tabs.Tab>
            <Tabs.Tab value="preview">预览</Tabs.Tab>
          </Tabs.List>

          {/* Basic Information Tab */}
          <Tabs.Panel value="basic" pt="md">
            <Stack gap="md">
              <TextInput
                label="场景名称"
                placeholder="输入场景名称"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.currentTarget.value })
                }
                required
              />

              <Textarea
                label="场景描述"
                placeholder="输入场景描述"
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.currentTarget.value })
                }
                minRows={3}
              />

              <Select
                label="场景分类"
                placeholder="选择场景分类"
                value={formData.category}
                onChange={(value) =>
                  setFormData({ ...formData, category: value || 'custom' })
                }
                data={CATEGORIES}
              />
            </Stack>
          </Tabs.Panel>

          {/* Network Configuration Tab */}
          <Tabs.Panel value="network" pt="md">
            <Stack gap="md">
              <SimpleGrid cols={2} spacing="md">
                <Select
                  label="网络类型"
                  placeholder="选择网络类型"
                  value={formData.networkType}
                  onChange={(value) =>
                    setFormData({ ...formData, networkType: value || '5G_NR' })
                  }
                  data={NETWORK_TYPES}
                />

                <TextInput
                  label="频段"
                  placeholder="例如: n78"
                  value={formData.band}
                  onChange={(e) =>
                    setFormData({ ...formData, band: e.currentTarget.value })
                  }
                />

                <NumberInput
                  label="带宽 (MHz)"
                  placeholder="例如: 100"
                  value={formData.bandwidth}
                  onChange={(value) =>
                    setFormData({
                      ...formData,
                      bandwidth: typeof value === 'number' ? value : 100,
                    })
                  }
                  min={5}
                  max={400}
                />

                <Select
                  label="信道模型"
                  placeholder="选择信道模型"
                  value={formData.channelModel}
                  onChange={(value) =>
                    setFormData({
                      ...formData,
                      channelModel: value || 'UMa',
                    })
                  }
                  data={CHANNEL_MODELS}
                />
              </SimpleGrid>
            </Stack>
          </Tabs.Panel>

          {/* Environment Tab */}
          <Tabs.Panel value="environment" pt="md">
            <Stack gap="md">
              <SimpleGrid cols={2} spacing="md">
                <NumberInput
                  label="速度 (km/h)"
                  placeholder="例如: 50"
                  value={formData.speed}
                  onChange={(value) =>
                    setFormData({ ...formData, speed: typeof value === 'number' ? value : 50 })
                  }
                  min={0}
                  max={500}
                />

                <NumberInput
                  label="测试时长 (秒)"
                  placeholder="例如: 60"
                  value={formData.duration}
                  onChange={(value) =>
                    setFormData({ ...formData, duration: typeof value === 'number' ? value : 60 })
                  }
                  min={10}
                  max={3600}
                />
              </SimpleGrid>

              <Card withBorder p="md" bg="blue.0">
                <Text fw={500} mb="xs">
                  计算的测试参数:
                </Text>
                <SimpleGrid cols={2} spacing="md">
                  <div>
                    <Text size="xs" c="dimmed">
                      总距离
                    </Text>
                    <Text size="sm">
                      {Math.round((formData.speed * formData.duration) / 3.6)} m (~{((formData.speed * formData.duration) / 3600).toFixed(2)} km)
                    </Text>
                  </div>
                  <div>
                    <Text size="xs" c="dimmed">
                      估计数据量
                    </Text>
                    <Text size="sm">
                      {Math.round((50 * formData.duration) / 8)} MB
                    </Text>
                  </div>
                </SimpleGrid>
              </Card>
            </Stack>
          </Tabs.Panel>

          {/* Test Steps Configuration Tab */}
          <Tabs.Panel value="steps" pt="md">
            <Stack gap="md">
              <Alert color="blue">
                <Stack gap="xs">
                  <Text size="sm" fw={500}>
                    📋 测试步骤配置
                  </Text>
                  <Text size="sm">
                    配置虚拟路测的8个标准步骤参数（如暗室ID、频率、KPI阈值等）。
                  </Text>
                </Stack>
              </Alert>
              <StepConfigurationEditor
                value={formData.stepConfiguration}
                onChange={(config) =>
                  setFormData({ ...formData, stepConfiguration: config })
                }
                testMode={testMode}
                scenarioDefaults={{
                  band: formData.band,
                  bandwidth_mhz: formData.bandwidth,
                  channel_model: formData.channelModel,
                }}
              />
            </Stack>
          </Tabs.Panel>

          {/* Preview Tab */}
          <Tabs.Panel value="preview" pt="md">
            <Stack gap="md">
              <Card withBorder p="md">
                <Stack gap="sm">
                  <Group justify="space-between">
                    <Text fw={500}>{formData.name || '未命名场景'}</Text>
                    <Badge color={isStandardScenario ? 'blue' : 'violet'}>
                      {isStandardScenario ? 'Standard' : 'Custom'}
                    </Badge>
                  </Group>

                  <Text size="sm" c="dimmed">
                    {formData.description || '无描述'}
                  </Text>

                  <SimpleGrid cols={2} spacing="md" mt="md">
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        分类
                      </Text>
                      <Text size="sm">{formData.category}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        网络类型
                      </Text>
                      <Text size="sm">{formData.networkType}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        频段
                      </Text>
                      <Text size="sm">{formData.band}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        信道模型
                      </Text>
                      <Text size="sm">{formData.channelModel}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        速度
                      </Text>
                      <Text size="sm">{formData.speed} km/h</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        时长
                      </Text>
                      <Text size="sm">{formData.duration}s</Text>
                    </div>
                  </SimpleGrid>
                </Stack>
              </Card>

              {formData.stepConfiguration && Object.keys(formData.stepConfiguration).length > 0 && (
                <Alert color="green" icon={<IconCheck size={16} />}>
                  已配置 {Object.keys(formData.stepConfiguration).length} 个测试步骤的参数
                </Alert>
              )}
            </Stack>
          </Tabs.Panel>
        </Tabs>

        {/* Action Buttons */}
        <Group justify="flex-end">
          <Button
            variant="light"
            onClick={handleClose}
            disabled={updateMutation.isPending}
          >
            取消
          </Button>
          <Button
            onClick={() => updateMutation.mutate()}
            disabled={!isFormValid || updateMutation.isPending}
            loading={updateMutation.isPending}
          >
            保存更改
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
