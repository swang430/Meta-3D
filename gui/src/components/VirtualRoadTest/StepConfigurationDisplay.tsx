/**
 * Step Configuration Display Component
 *
 * Displays pre-configured test step parameters in a readable format
 */

import { Stack, Title, Text, Paper, Group, Badge, Divider, Alert } from '@mantine/core'
import { IconInfoCircle, IconSettings } from '@tabler/icons-react'
import type { StepConfiguration } from '../../types/roadTest'

interface Props {
  stepConfiguration?: StepConfiguration
}

const STEP_NAMES = {
  chamber_init: '步骤1: 初始化OTA暗室',
  network_config: '步骤2: 配置网络',
  base_station_setup: '步骤3: 设置基站和信道模型',
  ota_mapper: '步骤4: 配置OTA Mapper',
  route_execution: '步骤5: 执行路径测试',
  kpi_validation: '步骤6: 验证KPI和性能指标',
  report_generation: '步骤7: 生成测试报告',
  environment_setup: '步骤8: 配置数字孪生环境',
}

export function StepConfigurationDisplay({ stepConfiguration }: Props) {
  if (!stepConfiguration) {
    return (
      <Alert icon={<IconInfoCircle size={16} />} title="无自定义配置" color="gray">
        此场景使用默认的测试步骤配置。转换为测试计划时，将使用标准参数。
      </Alert>
    )
  }

  // 检查是否有任何配置
  const hasAnyConfig = Object.keys(stepConfiguration).some(
    (key) => stepConfiguration[key as keyof StepConfiguration] !== undefined
  )

  if (!hasAnyConfig) {
    return (
      <Alert icon={<IconInfoCircle size={16} />} title="无自定义配置" color="gray">
        此场景使用默认的测试步骤配置。
      </Alert>
    )
  }

  return (
    <Stack gap="md">
      <Alert icon={<IconSettings size={16} />} title="自定义步骤配置" color="cyan">
        以下步骤已预配置自定义参数。转换为测试计划时，这些参数将自动应用到相应步骤。
      </Alert>

      {/* Chamber Init */}
      {stepConfiguration.chamber_init && (
        <Paper p="md" withBorder>
          <Group mb="sm">
            <Badge color="blue" variant="light">
              步骤 1
            </Badge>
            <Text fw={600}>{STEP_NAMES.chamber_init}</Text>
          </Group>
          <Stack gap="xs">
            {stepConfiguration.chamber_init.chamber_id && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  Chamber ID:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.chamber_init.chamber_id}
                </Text>
              </Group>
            )}
            {stepConfiguration.chamber_init.timeout_seconds !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  超时时间:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.chamber_init.timeout_seconds} 秒
                </Text>
              </Group>
            )}
            {stepConfiguration.chamber_init.verify_connections !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  验证连接:
                </Text>
                <Badge size="sm" color={stepConfiguration.chamber_init.verify_connections ? 'green' : 'gray'}>
                  {stepConfiguration.chamber_init.verify_connections ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.chamber_init.calibrate_position_table !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  校准转台:
                </Text>
                <Badge size="sm" color={stepConfiguration.chamber_init.calibrate_position_table ? 'green' : 'gray'}>
                  {stepConfiguration.chamber_init.calibrate_position_table ? '是' : '否'}
                </Badge>
              </Group>
            )}
          </Stack>
        </Paper>
      )}

      {/* Network Config */}
      {stepConfiguration.network_config && (
        <Paper p="md" withBorder>
          <Group mb="sm">
            <Badge color="blue" variant="light">
              步骤 2
            </Badge>
            <Text fw={600}>{STEP_NAMES.network_config}</Text>
          </Group>
          <Stack gap="xs">
            {stepConfiguration.network_config.frequency_mhz !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  频率:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.network_config.frequency_mhz} MHz
                </Text>
              </Group>
            )}
            {stepConfiguration.network_config.bandwidth_mhz !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  带宽:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.network_config.bandwidth_mhz} MHz
                </Text>
              </Group>
            )}
            {stepConfiguration.network_config.technology && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  技术:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.network_config.technology}
                </Text>
              </Group>
            )}
            {stepConfiguration.network_config.timeout_seconds !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  超时时间:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.network_config.timeout_seconds} 秒
                </Text>
              </Group>
            )}
            {stepConfiguration.network_config.verify_signal !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  验证信号:
                </Text>
                <Badge size="sm" color={stepConfiguration.network_config.verify_signal ? 'green' : 'gray'}>
                  {stepConfiguration.network_config.verify_signal ? '是' : '否'}
                </Badge>
              </Group>
            )}
          </Stack>
        </Paper>
      )}

      {/* Base Station Setup */}
      {stepConfiguration.base_station_setup && (
        <Paper p="md" withBorder>
          <Group mb="sm">
            <Badge color="blue" variant="light">
              步骤 3
            </Badge>
            <Text fw={600}>{STEP_NAMES.base_station_setup}</Text>
          </Group>
          <Stack gap="xs">
            {stepConfiguration.base_station_setup.channel_model && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  信道模型:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.base_station_setup.channel_model}
                </Text>
              </Group>
            )}
            {stepConfiguration.base_station_setup.num_base_stations !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  基站数量:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.base_station_setup.num_base_stations}
                </Text>
              </Group>
            )}
            {stepConfiguration.base_station_setup.timeout_seconds !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  超时时间:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.base_station_setup.timeout_seconds} 秒
                </Text>
              </Group>
            )}
            {stepConfiguration.base_station_setup.verify_coverage !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  验证覆盖:
                </Text>
                <Badge size="sm" color={stepConfiguration.base_station_setup.verify_coverage ? 'green' : 'gray'}>
                  {stepConfiguration.base_station_setup.verify_coverage ? '是' : '否'}
                </Badge>
              </Group>
            )}
          </Stack>
        </Paper>
      )}

      {/* OTA Mapper */}
      {stepConfiguration.ota_mapper && (
        <Paper p="md" withBorder>
          <Group mb="sm">
            <Badge color="blue" variant="light">
              步骤 4
            </Badge>
            <Text fw={600}>{STEP_NAMES.ota_mapper}</Text>
          </Group>
          <Stack gap="xs">
            {stepConfiguration.ota_mapper.route_type && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  路径类型:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.ota_mapper.route_type}
                </Text>
              </Group>
            )}
            {stepConfiguration.ota_mapper.update_rate_hz !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  更新频率:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.ota_mapper.update_rate_hz} Hz
                </Text>
              </Group>
            )}
            {stepConfiguration.ota_mapper.enable_handover !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  启用切换:
                </Text>
                <Badge size="sm" color={stepConfiguration.ota_mapper.enable_handover ? 'green' : 'gray'}>
                  {stepConfiguration.ota_mapper.enable_handover ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.ota_mapper.position_tolerance_m !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  位置容差:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.ota_mapper.position_tolerance_m} m
                </Text>
              </Group>
            )}
            {stepConfiguration.ota_mapper.timeout_seconds !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  超时时间:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.ota_mapper.timeout_seconds} 秒
                </Text>
              </Group>
            )}
          </Stack>
        </Paper>
      )}

      {/* Route Execution */}
      {stepConfiguration.route_execution && (
        <Paper p="md" withBorder>
          <Group mb="sm">
            <Badge color="blue" variant="light">
              步骤 5
            </Badge>
            <Text fw={600}>{STEP_NAMES.route_execution}</Text>
          </Group>
          <Stack gap="xs">
            {stepConfiguration.route_execution.route_duration_s !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  路径时长:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.route_execution.route_duration_s} 秒 (~
                  {Math.round(stepConfiguration.route_execution.route_duration_s / 60)} 分钟)
                </Text>
              </Group>
            )}
            {stepConfiguration.route_execution.total_distance_m !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  总距离:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.route_execution.total_distance_m} m (~
                  {(stepConfiguration.route_execution.total_distance_m / 1000).toFixed(1)} km)
                </Text>
              </Group>
            )}
            {stepConfiguration.route_execution.monitor_kpis !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  监控KPI:
                </Text>
                <Badge size="sm" color={stepConfiguration.route_execution.monitor_kpis ? 'green' : 'gray'}>
                  {stepConfiguration.route_execution.monitor_kpis ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.route_execution.log_interval_s !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  日志间隔:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.route_execution.log_interval_s} 秒
                </Text>
              </Group>
            )}
            {stepConfiguration.route_execution.auto_screenshot !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  自动截图:
                </Text>
                <Badge size="sm" color={stepConfiguration.route_execution.auto_screenshot ? 'green' : 'gray'}>
                  {stepConfiguration.route_execution.auto_screenshot ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.route_execution.timeout_seconds !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  超时时间:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.route_execution.timeout_seconds} 秒 (~
                  {Math.round(stepConfiguration.route_execution.timeout_seconds / 60)} 分钟)
                </Text>
              </Group>
            )}
          </Stack>
        </Paper>
      )}

      {/* KPI Validation */}
      {stepConfiguration.kpi_validation && (
        <Paper p="md" withBorder>
          <Group mb="sm">
            <Badge color="blue" variant="light">
              步骤 6
            </Badge>
            <Text fw={600}>{STEP_NAMES.kpi_validation}</Text>
          </Group>
          <Stack gap="xs">
            {stepConfiguration.kpi_validation.kpi_thresholds && (
              <>
                <Text size="sm" c="dimmed" mb={4}>
                  KPI阈值:
                </Text>
                <Stack gap={4} pl="md">
                  {stepConfiguration.kpi_validation.kpi_thresholds.min_throughput_mbps !== undefined && (
                    <Group gap="xs">
                      <Text size="sm" c="dimmed" w={160}>
                        最小吞吐量:
                      </Text>
                      <Text size="sm" fw={500}>
                        {stepConfiguration.kpi_validation.kpi_thresholds.min_throughput_mbps} Mbps
                      </Text>
                    </Group>
                  )}
                  {stepConfiguration.kpi_validation.kpi_thresholds.max_latency_ms !== undefined && (
                    <Group gap="xs">
                      <Text size="sm" c="dimmed" w={160}>
                        最大延迟:
                      </Text>
                      <Text size="sm" fw={500}>
                        {stepConfiguration.kpi_validation.kpi_thresholds.max_latency_ms} ms
                      </Text>
                    </Group>
                  )}
                  {stepConfiguration.kpi_validation.kpi_thresholds.min_rsrp_dbm !== undefined && (
                    <Group gap="xs">
                      <Text size="sm" c="dimmed" w={160}>
                        最小RSRP:
                      </Text>
                      <Text size="sm" fw={500}>
                        {stepConfiguration.kpi_validation.kpi_thresholds.min_rsrp_dbm} dBm
                      </Text>
                    </Group>
                  )}
                  {stepConfiguration.kpi_validation.kpi_thresholds.max_packet_loss_percent !== undefined && (
                    <Group gap="xs">
                      <Text size="sm" c="dimmed" w={160}>
                        最大丢包率:
                      </Text>
                      <Text size="sm" fw={500}>
                        {stepConfiguration.kpi_validation.kpi_thresholds.max_packet_loss_percent}%
                      </Text>
                    </Group>
                  )}
                </Stack>
              </>
            )}
            {stepConfiguration.kpi_validation.generate_plots !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  生成图表:
                </Text>
                <Badge size="sm" color={stepConfiguration.kpi_validation.generate_plots ? 'green' : 'gray'}>
                  {stepConfiguration.kpi_validation.generate_plots ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.kpi_validation.timeout_seconds !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  超时时间:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.kpi_validation.timeout_seconds} 秒
                </Text>
              </Group>
            )}
          </Stack>
        </Paper>
      )}

      {/* Report Generation */}
      {stepConfiguration.report_generation && (
        <Paper p="md" withBorder>
          <Group mb="sm">
            <Badge color="blue" variant="light">
              步骤 7
            </Badge>
            <Text fw={600}>{STEP_NAMES.report_generation}</Text>
          </Group>
          <Stack gap="xs">
            {stepConfiguration.report_generation.report_format && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  报告格式:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.report_generation.report_format.toUpperCase()}
                </Text>
              </Group>
            )}
            {stepConfiguration.report_generation.include_raw_data !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  包含原始数据:
                </Text>
                <Badge size="sm" color={stepConfiguration.report_generation.include_raw_data ? 'green' : 'gray'}>
                  {stepConfiguration.report_generation.include_raw_data ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.report_generation.include_screenshots !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  包含截图:
                </Text>
                <Badge size="sm" color={stepConfiguration.report_generation.include_screenshots ? 'green' : 'gray'}>
                  {stepConfiguration.report_generation.include_screenshots ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.report_generation.include_recommendations !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  包含建议:
                </Text>
                <Badge
                  size="sm"
                  color={stepConfiguration.report_generation.include_recommendations ? 'green' : 'gray'}
                >
                  {stepConfiguration.report_generation.include_recommendations ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.report_generation.timeout_seconds !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  超时时间:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.report_generation.timeout_seconds} 秒
                </Text>
              </Group>
            )}
          </Stack>
        </Paper>
      )}

      {/* Environment Setup - Step 8 */}
      {stepConfiguration.environment_setup && (
        <Paper p="md" withBorder>
          <Group mb="sm">
            <Badge color="teal" variant="light">
              步骤 8
            </Badge>
            <Text fw={600}>{STEP_NAMES.environment_setup}</Text>
          </Group>
          <Stack gap="xs">
            {stepConfiguration.environment_setup.environment_file && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  环境文件:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.environment_setup.environment_file}
                </Text>
              </Group>
            )}
            {stepConfiguration.environment_setup.channel_model && (
              <>
                <Text size="sm" c="dimmed" mb={4}>
                  信道模型:
                </Text>
                <Stack gap={4} pl="md">
                  {stepConfiguration.environment_setup.channel_model.type && (
                    <Group gap="xs">
                      <Text size="sm" c="dimmed" w={160}>
                        类型:
                      </Text>
                      <Badge size="sm" color="cyan">
                        {stepConfiguration.environment_setup.channel_model.type}
                      </Badge>
                    </Group>
                  )}
                  {stepConfiguration.environment_setup.channel_model.scenario && (
                    <Group gap="xs">
                      <Text size="sm" c="dimmed" w={160}>
                        场景:
                      </Text>
                      <Text size="sm" fw={500}>
                        {stepConfiguration.environment_setup.channel_model.scenario}
                      </Text>
                    </Group>
                  )}
                  {stepConfiguration.environment_setup.channel_model.los_condition && (
                    <Group gap="xs">
                      <Text size="sm" c="dimmed" w={160}>
                        LOS条件:
                      </Text>
                      <Text size="sm" fw={500}>
                        {stepConfiguration.environment_setup.channel_model.los_condition}
                      </Text>
                    </Group>
                  )}
                </Stack>
              </>
            )}
            {stepConfiguration.environment_setup.interference !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  干扰仿真:
                </Text>
                <Badge size="sm" color={stepConfiguration.environment_setup.interference.enabled ? 'orange' : 'gray'}>
                  {stepConfiguration.environment_setup.interference.enabled ? '启用' : '禁用'}
                </Badge>
                {stepConfiguration.environment_setup.interference.enabled &&
                  stepConfiguration.environment_setup.interference.sources && (
                    <Text size="xs" c="dimmed">
                      ({stepConfiguration.environment_setup.interference.sources.length} 个干扰源)
                    </Text>
                  )}
              </Group>
            )}
            {stepConfiguration.environment_setup.scatterers !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  移动散射体:
                </Text>
                <Badge size="sm" color={stepConfiguration.environment_setup.scatterers.enabled ? 'violet' : 'gray'}>
                  {stepConfiguration.environment_setup.scatterers.enabled ? '启用' : '禁用'}
                </Badge>
                {stepConfiguration.environment_setup.scatterers.enabled &&
                  stepConfiguration.environment_setup.scatterers.sources && (
                    <Text size="xs" c="dimmed">
                      ({stepConfiguration.environment_setup.scatterers.sources.length} 个散射体)
                    </Text>
                  )}
              </Group>
            )}
            {stepConfiguration.environment_setup.precompute_channel !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  预计算信道:
                </Text>
                <Badge size="sm" color={stepConfiguration.environment_setup.precompute_channel.enabled ? 'green' : 'gray'}>
                  {stepConfiguration.environment_setup.precompute_channel.enabled ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.environment_setup.validate_environment !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  验证环境:
                </Text>
                <Badge size="sm" color={stepConfiguration.environment_setup.validate_environment ? 'green' : 'gray'}>
                  {stepConfiguration.environment_setup.validate_environment ? '是' : '否'}
                </Badge>
              </Group>
            )}
            {stepConfiguration.environment_setup.timeout_seconds !== undefined && (
              <Group gap="xs">
                <Text size="sm" c="dimmed" w={180}>
                  超时时间:
                </Text>
                <Text size="sm" fw={500}>
                  {stepConfiguration.environment_setup.timeout_seconds} 秒
                </Text>
              </Group>
            )}
          </Stack>
        </Paper>
      )}
    </Stack>
  )
}
