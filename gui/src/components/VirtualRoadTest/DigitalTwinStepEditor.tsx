/**
 * Digital Twin Step Editor (Step 8)
 *
 * Deterministic Channel configuration:
 * - Channel Model Selection
 * - Ray Tracing
 * - Measured Channel
 * - Hybrid Model
 * - Dynamic Environment (Interference, Scatterers, Weather, Doppler)
 */

import {
  Stack,
  Paper,
  Text,
  Select,
  TextInput,
  NumberInput,
  Switch,
  Divider,
  SimpleGrid,
  Accordion,
  Group,
  Badge,
  Alert,
  SegmentedControl,
} from '@mantine/core'
import {
  IconCube,
  IconRoute,
  IconCloudRain,
  IconRadar,
  IconWind,
  IconFileAnalytics,
  IconInfoCircle,
} from '@tabler/icons-react'
import type { DigitalTwinStepConfig } from '../../types/roadTest'

interface Props {
  value?: DigitalTwinStepConfig
  onChange: (config: DigitalTwinStepConfig) => void
  scenarioChannelModel?: string  // e.g., "UMa", "UMi"
}

const DEFAULT_CONFIG: DigitalTwinStepConfig = {
  channel_model: {
    type: 'statistical',
    use_scenario_default: true,
  },
  validate_environment: true,
  export_channel_data: false,
  timeout_seconds: 600,
}

const CHANNEL_MODEL_TYPES = [
  { value: 'statistical', label: '3GPP统计模型', description: '使用场景定义的标准信道模型' },
  { value: 'ray-tracing', label: '射线追踪', description: '确定性3D电波传播仿真' },
  { value: 'measured', label: '实测信道', description: '回放实测CIR数据' },
  { value: 'hybrid', label: '混合模式', description: '射线追踪+统计模型结合' },
]

const MODEL_TYPES = [
  { value: 'simplified', label: '简化模型' },
  { value: 'detailed', label: '详细模型' },
  { value: 'point_cloud', label: '点云模型' },
]

const BUILDING_SOURCES = [
  { value: 'osm', label: 'OpenStreetMap' },
  { value: 'custom', label: '自定义模型' },
  { value: 'lidar', label: 'LiDAR扫描' },
]

const ACCELERATION_METHODS = [
  { value: 'sbr', label: 'SBR (射束弹跳)' },
  { value: 'image', label: '镜像法' },
  { value: 'hybrid', label: '混合方法' },
]

const CIR_FORMATS = [
  { value: 'matlab', label: 'MATLAB (.mat)' },
  { value: 'csv', label: 'CSV' },
  { value: 'hdf5', label: 'HDF5' },
  { value: 'sigmf', label: 'SigMF' },
]

const TIME_ALIGNMENTS = [
  { value: 'gps', label: 'GPS时间对齐' },
  { value: 'route_distance', label: '路径距离对齐' },
  { value: 'manual', label: '手动对齐' },
]

const INTERPOLATIONS = [
  { value: 'linear', label: '线性插值' },
  { value: 'spline', label: '样条插值' },
  { value: 'nearest', label: '最近邻' },
]

const WEATHER_CONDITIONS = [
  { value: 'clear', label: '晴朗' },
  { value: 'rain', label: '雨天' },
  { value: 'snow', label: '雪天' },
  { value: 'fog', label: '雾天' },
]

const DOPPLER_MODELS = [
  { value: 'jakes', label: 'Jakes模型' },
  { value: 'cluster_based', label: '簇状模型' },
  { value: 'measured', label: '实测模型' },
]

const EXPORT_FORMATS = [
  { value: 'matlab', label: 'MATLAB' },
  { value: 'hdf5', label: 'HDF5' },
  { value: 'csv', label: 'CSV' },
]

export function DigitalTwinStepEditor({ value, onChange, scenarioChannelModel }: Props) {
  const config = value || DEFAULT_CONFIG

  const updateConfig = <K extends keyof DigitalTwinStepConfig>(
    key: K,
    val: DigitalTwinStepConfig[K]
  ) => {
    onChange({ ...config, [key]: val })
  }

  const updateNested = <K extends keyof DigitalTwinStepConfig>(
    key: K,
    nestedKey: string,
    val: any
  ) => {
    onChange({
      ...config,
      [key]: {
        ...(config[key] as any),
        [nestedKey]: val,
      },
    })
  }

  return (
    <Stack gap="md">
      {/* Channel Model Type Selection */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Text fw={600}>信道模型类型</Text>
          <SegmentedControl
            fullWidth
            value={config.channel_model.type}
            onChange={(val) =>
              updateConfig('channel_model', {
                ...config.channel_model,
                type: val as any,
              })
            }
            data={CHANNEL_MODEL_TYPES.map(t => ({
              value: t.value,
              label: t.label,
            }))}
          />

          <Text size="sm" c="dimmed">
            {CHANNEL_MODEL_TYPES.find(t => t.value === config.channel_model.type)?.description}
          </Text>

          {config.channel_model.type === 'statistical' && (
            <Alert icon={<IconInfoCircle size={16} />} color="blue">
              <Group gap="xs">
                <Text size="sm">
                  使用场景定义的标准信道模型
                  {scenarioChannelModel && (
                    <Badge ml="xs" variant="light">{scenarioChannelModel}</Badge>
                  )}
                </Text>
              </Group>
            </Alert>
          )}
        </Stack>
      </Paper>

      <Accordion variant="separated" multiple>
        {/* Ray Tracing Section */}
        {(config.channel_model.type === 'ray-tracing' || config.channel_model.type === 'hybrid') && (
          <Accordion.Item value="ray-tracing">
            <Accordion.Control icon={<IconCube size={20} />}>
              <Group gap="xs">
                <Text fw={600}>射线追踪配置</Text>
                {config.ray_tracing?.enabled && (
                  <Badge size="sm" variant="light" color="green">已启用</Badge>
                )}
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              <Paper p="md" withBorder>
                <Stack gap="md">
                  <Switch
                    label="启用射线追踪"
                    checked={config.ray_tracing?.enabled || false}
                    onChange={(e) =>
                      updateConfig('ray_tracing', {
                        ...config.ray_tracing,
                        enabled: e.currentTarget.checked,
                        environment: config.ray_tracing?.environment || {
                          model_type: 'simplified',
                        },
                        parameters: config.ray_tracing?.parameters || {
                          max_reflections: 3,
                          max_diffractions: 1,
                          max_scattering: 2,
                          frequency_dependent_materials: true,
                        },
                        acceleration: config.ray_tracing?.acceleration || {
                          method: 'sbr',
                          gpu_enabled: true,
                          precompute: true,
                        },
                      })
                    }
                  />

                  {config.ray_tracing?.enabled && (
                    <>
                      <Divider label="3D环境" labelPosition="left" />
                      <SimpleGrid cols={2}>
                        <TextInput
                          label="模型文件"
                          description=".obj, .gltf, .osm 格式"
                          placeholder="/path/to/model.obj"
                          value={config.ray_tracing.environment.model_file || ''}
                          onChange={(e) =>
                            updateNested('ray_tracing', 'environment', {
                              ...config.ray_tracing?.environment,
                              model_file: e.currentTarget.value,
                            })
                          }
                        />

                        <Select
                          label="模型类型"
                          data={MODEL_TYPES}
                          value={config.ray_tracing.environment.model_type}
                          onChange={(val) =>
                            updateNested('ray_tracing', 'environment', {
                              ...config.ray_tracing?.environment,
                              model_type: val,
                            })
                          }
                        />

                        <Select
                          label="建筑物数据源"
                          data={BUILDING_SOURCES}
                          value={config.ray_tracing.environment.buildings?.source}
                          onChange={(val) =>
                            updateNested('ray_tracing', 'environment', {
                              ...config.ray_tracing?.environment,
                              buildings: {
                                ...config.ray_tracing?.environment.buildings,
                                source: val,
                              },
                            })
                          }
                        />
                      </SimpleGrid>

                      <Switch
                        label="启用地形"
                        checked={config.ray_tracing.environment.terrain?.enabled || false}
                        onChange={(e) =>
                          updateNested('ray_tracing', 'environment', {
                            ...config.ray_tracing?.environment,
                            terrain: {
                              ...config.ray_tracing?.environment.terrain,
                              enabled: e.currentTarget.checked,
                              resolution_m: config.ray_tracing?.environment.terrain?.resolution_m || 30,
                            },
                          })
                        }
                      />

                      <Divider label="射线追踪参数" labelPosition="left" />
                      <SimpleGrid cols={3}>
                        <NumberInput
                          label="最大反射次数"
                          value={config.ray_tracing.parameters.max_reflections}
                          onChange={(val) =>
                            updateNested('ray_tracing', 'parameters', {
                              ...config.ray_tracing?.parameters,
                              max_reflections: val,
                            })
                          }
                          min={0}
                          max={10}
                        />

                        <NumberInput
                          label="最大绕射次数"
                          value={config.ray_tracing.parameters.max_diffractions}
                          onChange={(val) =>
                            updateNested('ray_tracing', 'parameters', {
                              ...config.ray_tracing?.parameters,
                              max_diffractions: val,
                            })
                          }
                          min={0}
                          max={3}
                        />

                        <NumberInput
                          label="最大散射次数"
                          value={config.ray_tracing.parameters.max_scattering}
                          onChange={(val) =>
                            updateNested('ray_tracing', 'parameters', {
                              ...config.ray_tracing?.parameters,
                              max_scattering: val,
                            })
                          }
                          min={0}
                          max={5}
                        />
                      </SimpleGrid>

                      <Switch
                        label="频率相关材料特性"
                        checked={config.ray_tracing.parameters.frequency_dependent_materials}
                        onChange={(e) =>
                          updateNested('ray_tracing', 'parameters', {
                            ...config.ray_tracing?.parameters,
                            frequency_dependent_materials: e.currentTarget.checked,
                          })
                        }
                      />

                      <Divider label="加速配置" labelPosition="left" />
                      <SimpleGrid cols={2}>
                        <Select
                          label="加速方法"
                          data={ACCELERATION_METHODS}
                          value={config.ray_tracing.acceleration.method}
                          onChange={(val) =>
                            updateNested('ray_tracing', 'acceleration', {
                              ...config.ray_tracing?.acceleration,
                              method: val,
                            })
                          }
                        />
                      </SimpleGrid>

                      <Group>
                        <Switch
                          label="启用GPU加速"
                          checked={config.ray_tracing.acceleration.gpu_enabled}
                          onChange={(e) =>
                            updateNested('ray_tracing', 'acceleration', {
                              ...config.ray_tracing?.acceleration,
                              gpu_enabled: e.currentTarget.checked,
                            })
                          }
                        />

                        <Switch
                          label="预计算信道"
                          checked={config.ray_tracing.acceleration.precompute}
                          onChange={(e) =>
                            updateNested('ray_tracing', 'acceleration', {
                              ...config.ray_tracing?.acceleration,
                              precompute: e.currentTarget.checked,
                            })
                          }
                        />
                      </Group>
                    </>
                  )}
                </Stack>
              </Paper>
            </Accordion.Panel>
          </Accordion.Item>
        )}

        {/* Measured Channel Section */}
        {(config.channel_model.type === 'measured' || config.channel_model.type === 'hybrid') && (
          <Accordion.Item value="measured">
            <Accordion.Control icon={<IconFileAnalytics size={20} />}>
              <Group gap="xs">
                <Text fw={600}>实测信道配置</Text>
                {config.measured_channel?.enabled && (
                  <Badge size="sm" variant="light" color="cyan">已启用</Badge>
                )}
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              <Paper p="md" withBorder>
                <Stack gap="md">
                  <Switch
                    label="启用实测信道回放"
                    checked={config.measured_channel?.enabled || false}
                    onChange={(e) =>
                      updateConfig('measured_channel', {
                        ...config.measured_channel,
                        enabled: e.currentTarget.checked,
                        cir_file: config.measured_channel?.cir_file || '',
                        format: config.measured_channel?.format || 'matlab',
                        time_alignment: config.measured_channel?.time_alignment || 'gps',
                        interpolation: config.measured_channel?.interpolation || 'linear',
                        loop: config.measured_channel?.loop || false,
                      })
                    }
                  />

                  {config.measured_channel?.enabled && (
                    <>
                      <TextInput
                        label="CIR文件路径"
                        description="信道冲激响应文件"
                        placeholder="/path/to/channel_data.mat"
                        value={config.measured_channel.cir_file}
                        onChange={(e) =>
                          updateNested('measured_channel', 'cir_file', e.currentTarget.value)
                        }
                        required
                      />

                      <SimpleGrid cols={3}>
                        <Select
                          label="文件格式"
                          data={CIR_FORMATS}
                          value={config.measured_channel.format}
                          onChange={(val) =>
                            updateNested('measured_channel', 'format', val)
                          }
                        />

                        <Select
                          label="时间对齐方式"
                          data={TIME_ALIGNMENTS}
                          value={config.measured_channel.time_alignment}
                          onChange={(val) =>
                            updateNested('measured_channel', 'time_alignment', val)
                          }
                        />

                        <Select
                          label="插值方法"
                          data={INTERPOLATIONS}
                          value={config.measured_channel.interpolation}
                          onChange={(val) =>
                            updateNested('measured_channel', 'interpolation', val)
                          }
                        />
                      </SimpleGrid>

                      <Switch
                        label="循环播放"
                        description="到达文件末尾时从头开始"
                        checked={config.measured_channel.loop}
                        onChange={(e) =>
                          updateNested('measured_channel', 'loop', e.currentTarget.checked)
                        }
                      />
                    </>
                  )}
                </Stack>
              </Paper>
            </Accordion.Panel>
          </Accordion.Item>
        )}

        {/* Hybrid Model Section */}
        {config.channel_model.type === 'hybrid' && (
          <Accordion.Item value="hybrid">
            <Accordion.Control icon={<IconRoute size={20} />}>
              <Group gap="xs">
                <Text fw={600}>混合模型配置</Text>
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              <Paper p="md" withBorder>
                <Stack gap="md">
                  <Alert icon={<IconInfoCircle size={16} />} color="blue">
                    混合模型结合射线追踪的准确性和统计模型的效率
                  </Alert>

                  <Switch
                    label="启用混合模式"
                    checked={config.hybrid?.enabled || false}
                    onChange={(e) =>
                      updateConfig('hybrid', {
                        ...config.hybrid,
                        enabled: e.currentTarget.checked,
                        ray_tracing_for_los: true,
                        statistical_for_nlos: true,
                        cluster_generation: 'hybrid',
                      })
                    }
                  />

                  {config.hybrid?.enabled && (
                    <>
                      <Switch
                        label="LOS路径使用射线追踪"
                        checked={config.hybrid.ray_tracing_for_los}
                        onChange={(e) =>
                          updateNested('hybrid', 'ray_tracing_for_los', e.currentTarget.checked)
                        }
                      />

                      <Switch
                        label="NLOS路径使用统计模型"
                        checked={config.hybrid.statistical_for_nlos}
                        onChange={(e) =>
                          updateNested('hybrid', 'statistical_for_nlos', e.currentTarget.checked)
                        }
                      />

                      <Select
                        label="簇生成方式"
                        data={[
                          { value: 'rt_based', label: '基于射线追踪' },
                          { value: '3gpp', label: '3GPP标准' },
                          { value: 'hybrid', label: '混合' },
                        ]}
                        value={config.hybrid.cluster_generation}
                        onChange={(val) =>
                          updateNested('hybrid', 'cluster_generation', val)
                        }
                      />
                    </>
                  )}
                </Stack>
              </Paper>
            </Accordion.Panel>
          </Accordion.Item>
        )}

        {/* Interference Section */}
        <Accordion.Item value="interference">
          <Accordion.Control icon={<IconRadar size={20} />}>
            <Group gap="xs">
              <Text fw={600}>干扰配置</Text>
              {config.interference?.enabled && (
                <Badge size="sm" variant="light" color="red">
                  {config.interference.sources?.length || 0} 个干扰源
                </Badge>
              )}
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Switch
                  label="启用干扰仿真"
                  description="模拟同频/邻频干扰源"
                  checked={config.interference?.enabled || false}
                  onChange={(e) =>
                    updateConfig('interference', {
                      ...config.interference,
                      enabled: e.currentTarget.checked,
                      sources: config.interference?.sources || [],
                    })
                  }
                />

                {config.interference?.enabled && (
                  <Alert color="yellow" icon={<IconInfoCircle size={16} />}>
                    干扰源配置需要在高级编辑器中进行详细配置
                  </Alert>
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Scatterers Section */}
        <Accordion.Item value="scatterers">
          <Accordion.Control icon={<IconWind size={20} />}>
            <Group gap="xs">
              <Text fw={600}>移动散射体</Text>
              {config.scatterers?.enabled && (
                <Badge size="sm" variant="light" color="orange">
                  {config.scatterers.sources?.length || 0} 个散射体
                </Badge>
              )}
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Switch
                  label="启用移动散射体"
                  description="模拟车辆、行人等动态遮挡"
                  checked={config.scatterers?.enabled || false}
                  onChange={(e) =>
                    updateConfig('scatterers', {
                      ...config.scatterers,
                      enabled: e.currentTarget.checked,
                      sources: config.scatterers?.sources || [],
                    })
                  }
                />

                {config.scatterers?.enabled && (
                  <Alert color="yellow" icon={<IconInfoCircle size={16} />}>
                    散射体配置需要在高级编辑器中进行详细配置
                  </Alert>
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Weather Section */}
        <Accordion.Item value="weather">
          <Accordion.Control icon={<IconCloudRain size={20} />}>
            <Group gap="xs">
              <Text fw={600}>天气效应</Text>
              {config.weather?.enabled && (
                <Badge size="sm" variant="light" color="blue">
                  {WEATHER_CONDITIONS.find(w => w.value === config.weather?.condition)?.label}
                </Badge>
              )}
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Switch
                  label="启用天气效应"
                  description="模拟雨衰、雾衰减等"
                  checked={config.weather?.enabled || false}
                  onChange={(e) =>
                    updateConfig('weather', {
                      ...config.weather,
                      enabled: e.currentTarget.checked,
                      condition: config.weather?.condition || 'clear',
                    })
                  }
                />

                {config.weather?.enabled && (
                  <>
                    <Select
                      label="天气条件"
                      data={WEATHER_CONDITIONS}
                      value={config.weather.condition}
                      onChange={(val) =>
                        updateNested('weather', 'condition', val)
                      }
                    />

                    {config.weather.condition === 'rain' && (
                      <NumberInput
                        label="降雨率 (mm/h)"
                        description="影响高频段衰减"
                        value={config.weather.rain_rate_mmh}
                        onChange={(val) =>
                          updateNested('weather', 'rain_rate_mmh', val)
                        }
                        min={0}
                        max={150}
                      />
                    )}

                    {config.weather.condition === 'fog' && (
                      <NumberInput
                        label="能见度 (m)"
                        value={config.weather.visibility_m}
                        onChange={(val) =>
                          updateNested('weather', 'visibility_m', val)
                        }
                        min={10}
                        max={10000}
                      />
                    )}
                  </>
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Doppler Section */}
        <Accordion.Item value="doppler">
          <Accordion.Control icon={<IconRoute size={20} />}>
            <Group gap="xs">
              <Text fw={600}>多普勒效应</Text>
              {config.doppler?.enabled && (
                <Badge size="sm" variant="light" color="violet">已启用</Badge>
              )}
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Switch
                  label="启用多普勒效应"
                  description="模拟高速移动带来的频率偏移"
                  checked={config.doppler?.enabled || false}
                  onChange={(e) =>
                    updateConfig('doppler', {
                      ...config.doppler,
                      enabled: e.currentTarget.checked,
                      time_variance_model: config.doppler?.time_variance_model || 'jakes',
                    })
                  }
                />

                {config.doppler?.enabled && (
                  <SimpleGrid cols={2}>
                    <NumberInput
                      label="最大多普勒频移 (Hz)"
                      description="留空则根据速度自动计算"
                      value={config.doppler.max_doppler_hz}
                      onChange={(val) =>
                        updateNested('doppler', 'max_doppler_hz', val)
                      }
                      min={0}
                      max={5000}
                    />

                    <Select
                      label="时变模型"
                      data={DOPPLER_MODELS}
                      value={config.doppler.time_variance_model}
                      onChange={(val) =>
                        updateNested('doppler', 'time_variance_model', val)
                      }
                    />
                  </SimpleGrid>
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>

      {/* Validation & Export Options */}
      <Paper p="md" withBorder>
        <Stack gap="sm">
          <Text fw={600} size="sm">验证与导出</Text>
          <SimpleGrid cols={2}>
            <Switch
              label="验证环境配置"
              checked={config.validate_environment}
              onChange={(e) => updateConfig('validate_environment', e.currentTarget.checked)}
            />
            <Switch
              label="导出信道数据"
              checked={config.export_channel_data}
              onChange={(e) => updateConfig('export_channel_data', e.currentTarget.checked)}
            />
          </SimpleGrid>

          {config.export_channel_data && (
            <Select
              label="导出格式"
              data={EXPORT_FORMATS}
              value={config.export_format}
              onChange={(val) => updateConfig('export_format', val as any)}
            />
          )}

          <NumberInput
            label="超时时间 (秒)"
            value={config.timeout_seconds}
            onChange={(val) => updateConfig('timeout_seconds', typeof val === 'number' ? val : 600)}
            min={60}
            max={3600}
          />
        </Stack>
      </Paper>
    </Stack>
  )
}
