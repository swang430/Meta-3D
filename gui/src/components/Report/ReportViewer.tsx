/**
 * Unified Report Viewer Component
 *
 * Display detailed report with scenario info, step configs, KPI summary, phase results, and events
 * Can be used by both test plan management and virtual road test modules
 */

import { useQuery } from '@tanstack/react-query'
import {
  Stack,
  Text,
  Badge,
  Card,
  SimpleGrid,
  Timeline,
  Table,
  Group,
  Alert,
  Loader,
  Center,
  ThemeIcon,
  Divider,
  Accordion,
  Code,
  Tabs,
} from '@mantine/core'
import {
  IconCheck,
  IconX,
  IconClock,
  IconAlertCircle,
  IconArrowsExchange,
  IconAntenna,
  IconActivity,
  IconNetwork,
  IconMapPin,
  IconSettings,
  IconReportAnalytics,
  IconListDetails,
  IconChartLine,
  IconMap,
} from '@tabler/icons-react'
import { fetchReport } from '../../api/reportService'
import type { Report, ReportContentData } from '../../types/report'
import { ChartsTab } from './ChartsTab'
import { TrajectoryMapTab } from './TrajectoryMapTab'

interface Props {
  /** Report ID to fetch from API */
  reportId?: string
  /** Direct content data (if already available) */
  contentData?: ReportContentData
  /** Report title override */
  title?: string
}

const MODE_LABELS: Record<string, string> = {
  digital_twin: '数字孪生',
  conducted: '传导测试',
  ota: 'OTA测试',
}

const RESULT_CONFIG = {
  passed: { color: 'green', label: '通过', icon: IconCheck },
  failed: { color: 'red', label: '失败', icon: IconX },
  incomplete: { color: 'yellow', label: '未完成', icon: IconClock },
}

const EVENT_ICONS: Record<string, typeof IconCheck> = {
  handover: IconArrowsExchange,
  beam_switch: IconAntenna,
  default: IconActivity,
}

/**
 * Unified Report Viewer
 * Supports two modes:
 * 1. Fetch by reportId from API
 * 2. Direct contentData passed as prop
 */
export function ReportViewer({ reportId, contentData, title }: Props) {
  const { data: report, isLoading, error } = useQuery({
    queryKey: ['report', reportId],
    queryFn: () => fetchReport(reportId!),
    enabled: !!reportId && !contentData,
  })

  // Use direct contentData or from API response
  const content = contentData || report?.content_data

  if (reportId && !contentData) {
    if (isLoading) {
      return (
        <Center py="xl">
          <Loader size="lg" />
          <Text ml="md" c="dimmed">加载报告...</Text>
        </Center>
      )
    }

    if (error) {
      return (
        <Alert icon={<IconAlertCircle size={16} />} title="加载失败" color="red">
          {(error as Error).message}
        </Alert>
      )
    }
  }

  if (!content) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} title="无报告数据" color="gray">
        报告内容不可用
      </Alert>
    )
  }

  return <ReportContent content={content} title={title || report?.title} />
}

interface ReportContentProps {
  content: ReportContentData
  title?: string
}

function ReportContent({ content, title }: ReportContentProps) {
  const resultConfig = RESULT_CONFIG[content.overall_result] || RESULT_CONFIG.incomplete
  const ResultIcon = resultConfig.icon
  const displayTitle = title || content.title || content.scenario?.name || '测试报告'

  return (
    <Stack gap="lg">
      {/* Header with Result */}
      <Card withBorder p="md" bg={`${resultConfig.color}.0`}>
        <Group justify="space-between" align="center">
          <div>
            <Text size="lg" fw={600}>{displayTitle}</Text>
            <Group gap="xs" mt={4}>
              {content.execution.mode && (
                <Badge size="sm">{MODE_LABELS[content.execution.mode] || content.execution.mode}</Badge>
              )}
              <Badge size="sm" color={resultConfig.color} leftSection={<ResultIcon size={12} />}>
                {resultConfig.label}
              </Badge>
              {content.scenario?.category && (
                <Badge size="sm" variant="outline">{content.scenario.category}</Badge>
              )}
              <Badge size="sm" variant="light" color="gray">
                {content.source === 'road_test' ? '虚拟路测' : '测试计划'}
              </Badge>
            </Group>
            {content.description && (
              <Text size="sm" c="dimmed" mt="xs">{content.description}</Text>
            )}
          </div>
          <div style={{ textAlign: 'right' }}>
            <Text size="xl" fw={700} c={resultConfig.color}>
              {content.pass_rate}%
            </Text>
            <Text size="xs" c="dimmed">通过率</Text>
          </div>
        </Group>
      </Card>

      {/* Tabs for different sections */}
      <Tabs defaultValue="overview">
        <Tabs.List>
          <Tabs.Tab value="overview" leftSection={<IconReportAnalytics size={14} />}>
            概览
          </Tabs.Tab>
          <Tabs.Tab value="config" leftSection={<IconNetwork size={14} />}>
            配置信息
          </Tabs.Tab>
          {content.step_configs && content.step_configs.length > 0 && (
            <Tabs.Tab value="steps" leftSection={<IconSettings size={14} />}>
              步骤参数
            </Tabs.Tab>
          )}
          <Tabs.Tab value="results" leftSection={<IconListDetails size={14} />}>
            执行过程
          </Tabs.Tab>
          {content.time_series && content.time_series.length > 0 && (
            <Tabs.Tab value="charts" leftSection={<IconChartLine size={14} />}>
              时间序列
            </Tabs.Tab>
          )}
          {content.source === 'road_test' && content.trajectory && content.trajectory.length > 0 && (
            <Tabs.Tab value="map" leftSection={<IconMap size={14} />}>
              路径地图
            </Tabs.Tab>
          )}
        </Tabs.List>

        {/* Overview Tab */}
        <Tabs.Panel value="overview" pt="md">
          <OverviewTab content={content} />
        </Tabs.Panel>

        {/* Configuration Tab */}
        <Tabs.Panel value="config" pt="md">
          <ConfigurationTab content={content} />
        </Tabs.Panel>

        {/* Steps Tab */}
        {content.step_configs && content.step_configs.length > 0 && (
          <Tabs.Panel value="steps" pt="md">
            <StepsTab stepConfigs={content.step_configs} />
          </Tabs.Panel>
        )}

        {/* Results Tab */}
        <Tabs.Panel value="results" pt="md">
          <ResultsTab content={content} />
        </Tabs.Panel>

        {/* Charts Tab */}
        {content.time_series && content.time_series.length > 0 && (
          <Tabs.Panel value="charts" pt="md">
            <ChartsTab timeSeries={content.time_series} />
          </Tabs.Panel>
        )}

        {/* Map Tab */}
        {content.source === 'road_test' && content.trajectory && content.trajectory.length > 0 && (
          <Tabs.Panel value="map" pt="md">
            <TrajectoryMapTab
              trajectory={content.trajectory}
              baseStations={content.base_stations}
            />
          </Tabs.Panel>
        )}
      </Tabs>
    </Stack>
  )
}

function OverviewTab({ content }: { content: ReportContentData }) {
  return (
    <Stack gap="md">
      {/* Summary Stats */}
      <SimpleGrid cols={4} spacing="md">
        <Card withBorder p="sm">
          <Text size="xs" c="dimmed" fw={500}>开始时间</Text>
          <Text size="sm">
            {content.execution.start_time
              ? new Date(content.execution.start_time).toLocaleString('zh-CN')
              : '-'}
          </Text>
        </Card>
        <Card withBorder p="sm">
          <Text size="xs" c="dimmed" fw={500}>结束时间</Text>
          <Text size="sm">
            {content.execution.end_time
              ? new Date(content.execution.end_time).toLocaleString('zh-CN')
              : '-'}
          </Text>
        </Card>
        <Card withBorder p="sm">
          <Text size="xs" c="dimmed" fw={500}>持续时间</Text>
          <Text size="sm">
            {content.execution.duration_s ? `${Math.round(content.execution.duration_s)}s` : '-'}
          </Text>
        </Card>
        <Card withBorder p="sm">
          <Text size="xs" c="dimmed" fw={500}>执行ID</Text>
          <Text size="sm" ff="monospace">
            {content.execution_id.length > 12
              ? `${content.execution_id.slice(0, 12)}...`
              : content.execution_id}
          </Text>
        </Card>
      </SimpleGrid>

      {/* KPI Summary Table */}
      <Divider label="KPI 指标汇总" labelPosition="center" />
      <KPISummaryTable kpiSummary={content.kpi_summary} />

      {/* Events */}
      {content.events.length > 0 && (
        <>
          <Divider label="关键事件" labelPosition="center" />
          <EventsList events={content.events} />
        </>
      )}
    </Stack>
  )
}

function ConfigurationTab({ content }: { content: ReportContentData }) {
  const hasConfig = content.network || content.environment || content.route ||
                    (content.base_stations && content.base_stations.length > 0)

  if (!hasConfig) {
    return (
      <Alert color="gray" title="无配置信息">
        该报告没有关联的配置信息
      </Alert>
    )
  }

  return (
    <Stack gap="md">
      {/* Network Configuration */}
      {content.network && (
        <Card withBorder p="md">
          <Group gap="xs" mb="sm">
            <ThemeIcon size="sm" variant="light" color="blue">
              <IconNetwork size={14} />
            </ThemeIcon>
            <Text fw={500}>网络配置</Text>
          </Group>
          <SimpleGrid cols={3} spacing="md">
            <div>
              <Text size="xs" c="dimmed">网络类型</Text>
              <Text size="sm" fw={500}>{content.network.type}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">频段</Text>
              <Text size="sm" fw={500}>{content.network.band}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">带宽</Text>
              <Text size="sm" fw={500}>{content.network.bandwidth_mhz} MHz</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">双工模式</Text>
              <Text size="sm" fw={500}>{content.network.duplex_mode}</Text>
            </div>
            {content.network.scs_khz && (
              <div>
                <Text size="xs" c="dimmed">子载波间隔</Text>
                <Text size="sm" fw={500}>{content.network.scs_khz} kHz</Text>
              </div>
            )}
          </SimpleGrid>
        </Card>
      )}

      {/* Environment */}
      {content.environment && (
        <Card withBorder p="md">
          <Group gap="xs" mb="sm">
            <ThemeIcon size="sm" variant="light" color="green">
              <IconMapPin size={14} />
            </ThemeIcon>
            <Text fw={500}>环境配置</Text>
          </Group>
          <SimpleGrid cols={4} spacing="md">
            <div>
              <Text size="xs" c="dimmed">环境类型</Text>
              <Text size="sm" fw={500}>{content.environment.type}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">信道模型</Text>
              <Text size="sm" fw={500}>{content.environment.channel_model}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">天气</Text>
              <Text size="sm" fw={500}>{content.environment.weather}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">交通密度</Text>
              <Text size="sm" fw={500}>{content.environment.traffic_density}</Text>
            </div>
          </SimpleGrid>
        </Card>
      )}

      {/* Route Info */}
      {content.route && (
        <Card withBorder p="md">
          <Group gap="xs" mb="sm">
            <ThemeIcon size="sm" variant="light" color="orange">
              <IconMapPin size={14} />
            </ThemeIcon>
            <Text fw={500}>路径信息</Text>
          </Group>
          <SimpleGrid cols={4} spacing="md">
            <div>
              <Text size="xs" c="dimmed">持续时间</Text>
              <Text size="sm" fw={500}>{content.route.duration_s.toFixed(1)}s</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">总距离</Text>
              <Text size="sm" fw={500}>{(content.route.distance_m / 1000).toFixed(2)} km</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed">航点数</Text>
              <Text size="sm" fw={500}>{content.route.waypoint_count}</Text>
            </div>
            {content.route.avg_speed_kmh && (
              <div>
                <Text size="xs" c="dimmed">平均速度</Text>
                <Text size="sm" fw={500}>{content.route.avg_speed_kmh} km/h</Text>
              </div>
            )}
          </SimpleGrid>
        </Card>
      )}

      {/* Base Stations */}
      {content.base_stations && content.base_stations.length > 0 && (
        <Card withBorder p="md">
          <Group gap="xs" mb="sm">
            <ThemeIcon size="sm" variant="light" color="violet">
              <IconAntenna size={14} />
            </ThemeIcon>
            <Text fw={500}>基站配置 ({content.base_stations.length})</Text>
          </Group>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>ID</Table.Th>
                <Table.Th>名称</Table.Th>
                <Table.Th>发射功率</Table.Th>
                <Table.Th>天线配置</Table.Th>
                <Table.Th>天线高度</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {content.base_stations.map((bs) => (
                <Table.Tr key={bs.bs_id}>
                  <Table.Td><Text size="sm" ff="monospace">{bs.bs_id}</Text></Table.Td>
                  <Table.Td><Text size="sm">{bs.name}</Text></Table.Td>
                  <Table.Td><Text size="sm">{bs.tx_power_dbm} dBm</Text></Table.Td>
                  <Table.Td><Text size="sm">{bs.antenna_config}</Text></Table.Td>
                  <Table.Td><Text size="sm">{bs.antenna_height_m} m</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}
    </Stack>
  )
}

function StepsTab({ stepConfigs }: { stepConfigs: ReportContentData['step_configs'] }) {
  if (!stepConfigs || stepConfigs.length === 0) {
    return (
      <Alert color="gray" title="无步骤配置">
        该报告未配置测试步骤参数
      </Alert>
    )
  }

  return (
    <Accordion variant="separated">
      {stepConfigs.map((step, idx) => (
        <Accordion.Item key={idx} value={step.step_name}>
          <Accordion.Control>
            <Group gap="sm">
              <Badge size="sm" color={step.enabled ? 'green' : 'gray'}>
                {step.enabled ? '启用' : '禁用'}
              </Badge>
              <Text fw={500}>{step.step_name}</Text>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Stack gap="xs">
              {Object.entries(step.parameters).map(([key, value]) => (
                <Group key={key} justify="space-between" style={{ borderBottom: '1px solid #eee', paddingBottom: 4 }}>
                  <Text size="xs" c="dimmed">{key}</Text>
                  <Text size="xs" style={{ maxWidth: '60%', textAlign: 'right' }}>
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </Text>
                </Group>
              ))}
              {Object.keys(step.parameters).length === 0 && (
                <Text size="xs" c="dimmed" fs="italic">无参数配置</Text>
              )}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      ))}
    </Accordion>
  )
}

function ResultsTab({ content }: { content: ReportContentData }) {
  return (
    <Stack gap="md">
      <Divider label="执行阶段" labelPosition="center" />
      <Card withBorder p="md">
        <Timeline active={content.phases.length} bulletSize={24} lineWidth={2}>
          {content.phases.map((phase) => {
            const isCompleted = phase.status === 'completed'
            const isFailed = phase.status === 'failed'

            return (
              <Timeline.Item
                key={phase.name}
                bullet={
                  isCompleted ? (
                    <IconCheck size={12} />
                  ) : isFailed ? (
                    <IconX size={12} />
                  ) : (
                    <IconClock size={12} />
                  )
                }
                color={isCompleted ? 'green' : isFailed ? 'red' : 'gray'}
                title={
                  <Group gap="xs">
                    <Text size="sm" fw={500}>{phase.name}</Text>
                    <Badge size="xs" color={isCompleted ? 'green' : isFailed ? 'red' : 'gray'}>
                      {phase.duration_s.toFixed(1)}s
                    </Badge>
                  </Group>
                }
              >
                <Text size="xs" c="dimmed">
                  {new Date(phase.start_time).toLocaleTimeString('zh-CN')} -{' '}
                  {new Date(phase.end_time).toLocaleTimeString('zh-CN')}
                </Text>
              </Timeline.Item>
            )
          })}
        </Timeline>
      </Card>
    </Stack>
  )
}

function KPISummaryTable({ kpiSummary }: { kpiSummary: ReportContentData['kpi_summary'] }) {
  return (
    <Card withBorder p={0}>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>指标</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>平均值</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>最小值</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>最大值</Table.Th>
            <Table.Th style={{ textAlign: 'right' }}>目标值</Table.Th>
            <Table.Th style={{ textAlign: 'center' }}>结果</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {kpiSummary.map((kpi) => (
            <Table.Tr key={kpi.name}>
              <Table.Td>
                <Text size="sm" fw={500}>{kpi.name}</Text>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                <Text size="sm">{kpi.mean} {kpi.unit}</Text>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                <Text size="sm" c="dimmed">{kpi.min}</Text>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                <Text size="sm" c="dimmed">{kpi.max}</Text>
              </Table.Td>
              <Table.Td style={{ textAlign: 'right' }}>
                <Text size="sm" c="dimmed">{kpi.target ?? '-'}</Text>
              </Table.Td>
              <Table.Td style={{ textAlign: 'center' }}>
                {kpi.passed !== undefined ? (
                  <ThemeIcon
                    size="sm"
                    radius="xl"
                    color={kpi.passed ? 'green' : 'red'}
                    variant="light"
                  >
                    {kpi.passed ? <IconCheck size={12} /> : <IconX size={12} />}
                  </ThemeIcon>
                ) : (
                  <Text size="sm" c="dimmed">-</Text>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Card>
  )
}

function EventsList({ events }: { events: ReportContentData['events'] }) {
  return (
    <Card withBorder p="md">
      <Stack gap="xs">
        {events.map((event, idx) => {
          const EventIcon = EVENT_ICONS[event.type] || EVENT_ICONS.default
          return (
            <Group key={idx} gap="sm">
              <ThemeIcon size="sm" variant="light" color="blue">
                <EventIcon size={12} />
              </ThemeIcon>
              <Text size="sm" c="dimmed" style={{ minWidth: 80 }}>
                {new Date(event.time).toLocaleTimeString('zh-CN')}
              </Text>
              <Text size="sm">{event.description}</Text>
            </Group>
          )
        })}
      </Stack>
    </Card>
  )
}

export default ReportViewer
