/**
 * Create Scenario Dialog
 *
 * Form for creating custom test scenarios
 */

import { useState } from 'react'
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
import { createScenario } from '../../api/roadTestService'
import type { RoadTestScenario, StepConfiguration, TestMode } from '../../types/roadTest'
import { StepConfigurationEditor } from './StepConfigurationEditor'

interface Props {
  opened: boolean
  onClose: () => void
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

export function CreateScenarioDialog({ opened, onClose, testMode }: Props) {
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
    numBaseStations: 2,
    stepConfiguration: undefined as StepConfiguration | undefined,
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const scenario: Partial<RoadTestScenario> = {
        name: formData.name,
        description: formData.description,
        category: formData.category as any,
        source: 'custom',
        tags: [formData.category, formData.channelModel],
        network: {
          type: formData.networkType as any,
          band: formData.band,
          bandwidth_mhz: formData.bandwidth,
          duplex_mode: 'TDD',
          scs_khz: 30,
        },
        base_stations: Array.from({ length: formData.numBaseStations }).map((_, i) => ({
          bs_id: `BS${i + 1}`,
          name: `Custom Base Station ${i + 1}`,
          position: {
            lat: 31.23 + i * 0.005,
            lon: 121.47 + i * 0.005,
            alt: 30,
          },
          tx_power_dbm: 46,
          antenna_height_m: 25,
          antenna_config: '4T4R',
          azimuth_deg: i * (360 / formData.numBaseStations),
          tilt_deg: 10,
        })),
        route: {
          type: 'generated',
          waypoints: [],
          duration_s: formData.duration,
          total_distance_m: (formData.speed / 3.6) * formData.duration,
        },
        environment: {
          type: 'urban_street',
          channel_model: formData.channelModel as any,
          weather: 'clear',
          traffic_density: 'medium',
        },
        traffic: {
          type: 'ftp',
          direction: 'DL',
          data_rate_mbps: 50,
        },
        kpi_definitions: [
          {
            kpi_type: 'throughput',
            target_value: 45,
            unit: 'Mbps',
            percentile: 50,
            threshold_min: 30,
          },
          {
            kpi_type: 'latency',
            target_value: 20,
            unit: 'ms',
            percentile: 95,
            threshold_max: 50,
          },
        ],
        // Include step configuration if configured
        ...(formData.stepConfiguration && {
          step_configuration: formData.stepConfiguration,
        }),
      }
      return createScenario(scenario)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scenarios'] })
      handleClose()
    },
  })

  const handleClose = () => {
    // Reset form
    setFormData({
      name: '',
      description: '',
      category: 'custom',
      networkType: '5G_NR',
      band: 'n78',
      bandwidth: 100,
      channelModel: 'UMa',
      speed: 50,
      duration: 60,
      numBaseStations: 2,
      stepConfiguration: undefined,
    })
    setActiveTab('basic')
    onClose()
  }

  const isFormValid = formData.name.trim().length > 0

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title="创建自定义场景"
      size="lg"
      centered
    >
      <Stack gap="md">
        {createMutation.isPending && (
          <Alert color="blue">
            <Group gap="xs">
              <Loader size="sm" />
              <Text>正在创建场景...</Text>
            </Group>
          </Alert>
        )}

        {createMutation.isError && (
          <Alert
            icon={<IconAlertCircle size={16} />}
            title="错误"
            color="red"
          >
            创建场景失败: {(createMutation.error as Error).message}
          </Alert>
        )}

        {createMutation.isSuccess && (
          <Alert
            icon={<IconCheck size={16} />}
            title="成功"
            color="green"
          >
            场景创建成功！场景库已更新。
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
                      bandwidth: value || 100,
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

                <NumberInput
                  label="基站数量"
                  placeholder="例如: 2"
                  value={formData.numBaseStations}
                  onChange={(value) =>
                    setFormData({
                      ...formData,
                      numBaseStations: value || 2,
                    })
                  }
                  min={1}
                  max={8}
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
                    setFormData({ ...formData, speed: value || 50 })
                  }
                  min={0}
                  max={500}
                />

                <NumberInput
                  label="测试时长 (秒)"
                  placeholder="例如: 60"
                  value={formData.duration}
                  onChange={(value) =>
                    setFormData({ ...formData, duration: value || 60 })
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
                    📋 测试步骤预配置（可选）
                  </Text>
                  <Text size="sm">
                    虚拟路测包含固定的7个标准步骤。您可以在此预配置某些步骤的参数（如暗室ID、频率、KPI阈值等），未配置的步骤将使用系统默认值。
                  </Text>
                  <Text size="sm" c="dimmed">
                    注意：转换为测试计划后，所有7个步骤都会出现，但会应用您配置的参数。
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
                    <Badge color="violet">Custom</Badge>
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

              <Alert color="blue">
                <Stack gap="xs">
                  <Text size="sm">
                    ✓ 该场景将包含基本的网络配置、基站信息、路由和 KPI 定义。
                  </Text>
                  {formData.stepConfiguration && Object.keys(formData.stepConfiguration).length > 0 && (
                    <Text size="sm" fw={500}>
                      ✓ 已配置 {Object.keys(formData.stepConfiguration).length} 个测试步骤的预设参数
                    </Text>
                  )}
                </Stack>
              </Alert>
            </Stack>
          </Tabs.Panel>
        </Tabs>

        {/* Action Buttons */}
        <Group justify="flex-end">
          <Button
            variant="light"
            onClick={handleClose}
            disabled={createMutation.isPending}
          >
            取消
          </Button>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={!isFormValid || createMutation.isPending}
            loading={createMutation.isPending}
          >
            创建场景
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
