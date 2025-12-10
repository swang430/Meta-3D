/**
 * Scenario Detail Modal
 *
 * Display complete scenario configuration and parameters
 */

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Modal,
  Stack,
  Group,
  Text,
  Badge,
  Tabs,
  Card,
  SimpleGrid,
  Loader,
  Alert,
  Divider,
  ThemeIcon,
  Button,
} from '@mantine/core'
import {
  IconNetwork,
  IconBroadcast,
  IconRoute2,
  IconAlertCircle,
  IconRefresh,
  IconSettings,
} from '@tabler/icons-react'
import { fetchScenarioDetail } from '../../api/roadTestService'
import type { ScenarioSummary } from '../../types/roadTest'
import { StepConfigurationDisplay } from './StepConfigurationDisplay'

interface Props {
  opened: boolean
  onClose: () => void
  scenario: ScenarioSummary
}

export function ScenarioDetailModal({ opened, onClose, scenario }: Props) {
  const {
    data: scenarioDetail,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['scenario-detail', scenario.id],
    queryFn: () => fetchScenarioDetail(scenario.id),
    enabled: opened,
  })

  const categoryColors: Record<string, string> = {
    standard: 'blue',
    functional: 'green',
    performance: 'orange',
    environment: 'teal',
    extreme: 'red',
    custom: 'violet',
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={`场景详情: ${scenario.name}`}
      size="xl"
      centered
    >
      <Stack gap="md">
        {/* Header Info */}
        <Card withBorder p="md" bg="blue.0">
          <Group justify="space-between" mb="md">
            <div>
              <Text fw={600} size="lg">
                {scenario.name}
              </Text>
              <Text c="dimmed" size="sm">
                {scenario.description}
              </Text>
            </div>
            <Group gap="xs">
              <Badge color={categoryColors[scenario.category]}>
                {scenario.category}
              </Badge>
              <Badge variant="outline">{scenario.source}</Badge>
            </Group>
          </Group>

          <Group grow>
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                创建者
              </Text>
              <Text size="sm">{scenario.author || '-'}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                创建时间
              </Text>
              <Text size="sm">
                {scenario.created_at
                  ? new Date(scenario.created_at).toLocaleDateString()
                  : '-'}
              </Text>
            </div>
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                时长 / 距离
              </Text>
              <Text size="sm">
                {Math.round(scenario.duration_s)}s / {Math.round(scenario.distance_m)}m
              </Text>
            </div>
          </Group>
        </Card>

        {/* Tags */}
        {scenario.tags.length > 0 && (
          <div>
            <Text fw={500} size="sm" mb="xs">
              标签
            </Text>
            <Group gap="xs">
              {scenario.tags.map((tag) => (
                <Badge key={tag} variant="dot" size="lg">
                  {tag}
                </Badge>
              ))}
            </Group>
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <Group justify="center" py="xl">
            <Loader size="md" />
            <Text c="dimmed">加载场景详情...</Text>
          </Group>
        )}

        {/* Error State */}
        {error && (
          <Alert icon={<IconAlertCircle size={16} />} title="错误" color="red">
            加载场景详情失败: {(error as Error).message}
          </Alert>
        )}

        {/* Detail Tabs */}
        {scenarioDetail && !isLoading && (
          <Tabs defaultValue="network">
            <Tabs.List>
              <Tabs.Tab value="network" leftSection={<IconNetwork size={14} />}>
                网络配置
              </Tabs.Tab>
              <Tabs.Tab value="stations" leftSection={<IconBroadcast size={14} />}>
                基站 ({scenarioDetail.base_stations?.length || 0})
              </Tabs.Tab>
              <Tabs.Tab value="route" leftSection={<IconRoute2 size={14} />}>
                路由
              </Tabs.Tab>
              <Tabs.Tab value="steps" leftSection={<IconSettings size={14} />}>
                测试步骤配置
              </Tabs.Tab>
              <Tabs.Tab value="kpi">KPI</Tabs.Tab>
            </Tabs.List>

            {/* Network Configuration Tab */}
            <Tabs.Panel value="network" pt="md">
              <Stack gap="md">
                <Card withBorder p="md">
                  <Text fw={600} mb="md">
                    网络参数
                  </Text>
                  <SimpleGrid cols={2} spacing="md">
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        网络类型
                      </Text>
                      <Text size="sm">{scenarioDetail.network?.type || '-'}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        频段
                      </Text>
                      <Text size="sm">{scenarioDetail.network?.band || '-'}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        带宽
                      </Text>
                      <Text size="sm">
                        {scenarioDetail.network?.bandwidth_mhz || '-'} MHz
                      </Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        双工模式
                      </Text>
                      <Text size="sm">{scenarioDetail.network?.duplex_mode || '-'}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        子载波间距
                      </Text>
                      <Text size="sm">
                        {scenarioDetail.network?.scs_khz || '-'} kHz
                      </Text>
                    </div>
                  </SimpleGrid>
                </Card>

                <Card withBorder p="md">
                  <Text fw={600} mb="md">
                    环境配置
                  </Text>
                  <SimpleGrid cols={2} spacing="md">
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        环境类型
                      </Text>
                      <Text size="sm">{scenarioDetail.environment?.type || '-'}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        信道模型
                      </Text>
                      <Text size="sm">{scenarioDetail.environment?.channel_model || '-'}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        天气
                      </Text>
                      <Text size="sm">{scenarioDetail.environment?.weather || '-'}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        业务密度
                      </Text>
                      <Text size="sm">
                        {scenarioDetail.environment?.traffic_density || '-'}
                      </Text>
                    </div>
                  </SimpleGrid>
                </Card>
              </Stack>
            </Tabs.Panel>

            {/* Base Stations Tab */}
            <Tabs.Panel value="stations" pt="md">
              <Stack gap="md">
                {scenarioDetail.base_stations && scenarioDetail.base_stations.length > 0 ? (
                  scenarioDetail.base_stations.map((bs, index) => (
                    <Card key={bs.bs_id || index} withBorder p="md">
                      <Group justify="space-between" mb="md">
                        <Text fw={600}>
                          {bs.name || `基站 ${index + 1}`}
                        </Text>
                        <Badge>{bs.bs_id}</Badge>
                      </Group>

                      <SimpleGrid cols={2} spacing="md">
                        <div>
                          <Text size="xs" c="dimmed" fw={500}>
                            位置 (Lat, Lon, Alt)
                          </Text>
                          <Text size="sm">
                            {bs.position?.lat?.toFixed(6)}, {bs.position?.lon?.toFixed(6)}, {bs.position?.alt || 0}m
                          </Text>
                        </div>
                        <div>
                          <Text size="xs" c="dimmed" fw={500}>
                            发射功率
                          </Text>
                          <Text size="sm">{bs.tx_power_dbm || '-'} dBm</Text>
                        </div>
                        <div>
                          <Text size="xs" c="dimmed" fw={500}>
                            天线高度
                          </Text>
                          <Text size="sm">{bs.antenna_height_m || '-'} m</Text>
                        </div>
                        <div>
                          <Text size="xs" c="dimmed" fw={500}>
                            天线配置
                          </Text>
                          <Text size="sm">{bs.antenna_config || '-'}</Text>
                        </div>
                        <div>
                          <Text size="xs" c="dimmed" fw={500}>
                            方位角 / 倾斜角
                          </Text>
                          <Text size="sm">
                            {bs.azimuth_deg || 0}° / {bs.tilt_deg || 0}°
                          </Text>
                        </div>
                      </SimpleGrid>
                    </Card>
                  ))
                ) : (
                  <Text c="dimmed">无基站信息</Text>
                )}
              </Stack>
            </Tabs.Panel>

            {/* Route Tab */}
            <Tabs.Panel value="route" pt="md">
              <Stack gap="md">
                <Card withBorder p="md">
                  <Text fw={600} mb="md">
                    路由信息
                  </Text>
                  <SimpleGrid cols={2} spacing="md">
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        路由类型
                      </Text>
                      <Text size="sm">{scenarioDetail.route?.type || '-'}</Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        路由时长
                      </Text>
                      <Text size="sm">
                        {scenarioDetail.route?.duration_s || 0} s
                      </Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        总距离
                      </Text>
                      <Text size="sm">
                        {scenarioDetail.route?.total_distance_m || 0} m
                      </Text>
                    </div>
                    <div>
                      <Text size="xs" c="dimmed" fw={500}>
                        路由点数
                      </Text>
                      <Text size="sm">
                        {scenarioDetail.route?.waypoints?.length || 0}
                      </Text>
                    </div>
                  </SimpleGrid>
                </Card>

                {scenarioDetail.traffic && (
                  <Card withBorder p="md">
                    <Text fw={600} mb="md">
                      业务配置
                    </Text>
                    <SimpleGrid cols={2} spacing="md">
                      <div>
                        <Text size="xs" c="dimmed" fw={500}>
                          业务类型
                        </Text>
                        <Text size="sm">{scenarioDetail.traffic.type || '-'}</Text>
                      </div>
                      <div>
                        <Text size="xs" c="dimmed" fw={500}>
                          方向
                        </Text>
                        <Text size="sm">{scenarioDetail.traffic.direction || '-'}</Text>
                      </div>
                      <div>
                        <Text size="xs" c="dimmed" fw={500}>
                          数据率
                        </Text>
                        <Text size="sm">
                          {scenarioDetail.traffic.data_rate_mbps || 0} Mbps
                        </Text>
                      </div>
                    </SimpleGrid>
                  </Card>
                )}
              </Stack>
            </Tabs.Panel>

            {/* Test Steps Configuration Tab */}
            <Tabs.Panel value="steps" pt="md">
              <StepConfigurationDisplay stepConfiguration={scenarioDetail.step_configuration} />
            </Tabs.Panel>

            {/* KPI Tab */}
            <Tabs.Panel value="kpi" pt="md">
              <Stack gap="md">
                {scenarioDetail.kpi_definitions && scenarioDetail.kpi_definitions.length > 0 ? (
                  scenarioDetail.kpi_definitions.map((kpi, index) => (
                    <Card key={index} withBorder p="md">
                      <Group justify="space-between" mb="md">
                        <Text fw={600}>{kpi.kpi_type}</Text>
                        <Badge>{kpi.unit}</Badge>
                      </Group>

                      <SimpleGrid cols={2} spacing="md">
                        <div>
                          <Text size="xs" c="dimmed" fw={500}>
                            目标值
                          </Text>
                          <Text size="sm">{kpi.target_value || '-'}</Text>
                        </div>
                        <div>
                          <Text size="xs" c="dimmed" fw={500}>
                            百分位
                          </Text>
                          <Text size="sm">{kpi.percentile || '-'}</Text>
                        </div>
                        {kpi.threshold_min && (
                          <div>
                            <Text size="xs" c="dimmed" fw={500}>
                              最小阈值
                            </Text>
                            <Text size="sm">{kpi.threshold_min}</Text>
                          </div>
                        )}
                        {kpi.threshold_max && (
                          <div>
                            <Text size="xs" c="dimmed" fw={500}>
                              最大阈值
                            </Text>
                            <Text size="sm">{kpi.threshold_max}</Text>
                          </div>
                        )}
                      </SimpleGrid>
                    </Card>
                  ))
                ) : (
                  <Text c="dimmed">无 KPI 定义</Text>
                )}
              </Stack>
            </Tabs.Panel>
          </Tabs>
        )}

        {/* Action Buttons */}
        <Group justify="flex-end">
          {error && (
            <Button
              variant="light"
              leftSection={<IconRefresh size={16} />}
              onClick={() => refetch()}
            >
              重新加载
            </Button>
          )}
          <Button variant="subtle" onClick={onClose}>
            关闭
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
