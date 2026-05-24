/**
 * P2-8 ① 系统就绪带 — top-of-cockpit traffic-light strip.
 *
 * Surfaces the commissioning precheck fail-loud gate信息 (P1-8 校准 /
 * P1-9 DUT-attach) to the first screen: a four-cell traffic light
 * (驱动链 / 活动 Lab / 校准证书 / DUT attach) plus a one-line总判
 * (能不能开测 + 阻塞原因), styled to match the commissioning precheck
 * FAIL voice.
 *
 * Honesty notes:
 * - DUT-attach is a backend placeholder (status always "not_implemented");
 *   this cell renders gray "未实现" — never fake green/red.
 * - When `available=false` HAL hasn't initialised; we render a "HAL 未就绪"
 *   banner rather than treating the placeholder sub-sections as live.
 * - Polls ~10s (readiness changes slowly).
 */
import { useQuery } from '@tanstack/react-query'
import { Card, Group, Stack, Text, Badge, SimpleGrid, Loader, Alert, Divider } from '@mantine/core'
import {
  IconCircleCheck,
  IconAlertTriangle,
  IconCircleX,
  IconCircleDashed,
  IconShieldCheck,
  IconNetwork,
} from '@tabler/icons-react'
import { fetchReadiness } from '../../api/service'
import type {
  HALReadinessResponse,
  ReadinessDriverRow,
  ReadinessDriverStatus,
  ReadinessLabProfileStatus,
  ReadinessCalibrationStatus,
} from '../../types/api'

type Light = 'green' | 'yellow' | 'red' | 'gray'

const LIGHT_COLOR: Record<Light, string> = {
  green: 'green',
  yellow: 'yellow',
  red: 'red',
  gray: 'gray',
}

function LightIcon({ light, size = 18 }: { light: Light; size?: number }) {
  switch (light) {
    case 'green':
      return <IconCircleCheck size={size} color="var(--mantine-color-green-6)" />
    case 'yellow':
      return <IconAlertTriangle size={size} color="var(--mantine-color-yellow-6)" />
    case 'red':
      return <IconCircleX size={size} color="var(--mantine-color-red-6)" />
    default:
      return <IconCircleDashed size={size} color="var(--mantine-color-gray-5)" />
  }
}

// 聚合 drivers: 有 fail → 红 / 有 skipped → 黄 / 全 ok → 绿 / 空 → 灰
function aggregateDriverLight(statuses: ReadinessDriverStatus[]): Light {
  if (statuses.length === 0) return 'gray'
  if (statuses.some((s) => s === 'fail')) return 'red'
  if (statuses.some((s) => s === 'skipped')) return 'yellow'
  return 'green'
}

function labLight(status: ReadinessLabProfileStatus): Light {
  switch (status) {
    case 'ok':
      return 'green'
    case 'ambiguous':
      return 'yellow'
    case 'inactive':
    case 'missing':
      return 'red'
    default:
      return 'gray'
  }
}

function calLight(status: ReadinessCalibrationStatus): Light {
  switch (status) {
    case 'valid':
      return 'green'
    case 'expired':
      return 'red'
    case 'missing':
    case 'no_lab':
      return 'red'
    default:
      return 'gray'
  }
}

// P1-11: render a driver's status with the fail cause distinguished —
// "网络不可达" (子网/路由) vs "SCPI 无响应" (仪表/会话) vs 泛 fail.
// This is the core of P1-11: a CAICT operator should read "网络不可达"
// and reach for the subnet runbook, not stare at an opaque error code.
function driverStatusLabel(d: ReadinessDriverRow): string {
  if (d.status !== 'fail') return d.status
  if (d.fail_kind === 'network') return 'fail · 网络不可达'
  if (d.fail_kind === 'scpi') return 'fail · SCPI 无响应'
  return 'fail'
}

type Cell = {
  key: string
  title: string
  light: Light
  valueText: string
  detail: string
}

function buildCells(report: HALReadinessResponse): Cell[] {
  const driverLight = aggregateDriverLight(report.drivers.map((d) => d.status))
  const failCount = report.drivers.filter((d) => d.status === 'fail').length
  const skipCount = report.drivers.filter((d) => d.status === 'skipped').length
  const okCount = report.drivers.filter((d) => d.status === 'ok').length
  const driverValue =
    report.drivers.length === 0
      ? '无驱动'
      : failCount > 0
        ? `${failCount} 个失败`
        : skipCount > 0
          ? `${okCount} ok / ${skipCount} 跳过`
          : `全部 ${okCount} 个 ok`

  const cal = report.calibration
  const calValue =
    cal.status === 'valid'
      ? typeof cal.days_remaining === 'number'
        ? `有效 · 剩 ${cal.days_remaining} 天`
        : '有效'
      : cal.status === 'expired'
        ? typeof cal.days_remaining === 'number'
          ? `已过期 ${Math.abs(cal.days_remaining)} 天`
          : '已过期'
        : cal.status === 'missing'
          ? '未绑定证书'
          : cal.status === 'no_lab'
            ? '无活动 Lab'
            : '未知'

  return [
    {
      key: 'drivers',
      title: '驱动链',
      light: driverLight,
      valueText: driverValue,
      detail:
        report.drivers.map((d) => `${d.category}: ${driverStatusLabel(d)}`).join(' · ') ||
        '无已加载驱动',
    },
    {
      key: 'lab',
      title: '活动 Lab',
      light: labLight(report.lab_profile.status),
      valueText: report.lab_profile.profile_name || report.lab_profile.status,
      detail: report.lab_profile.detail,
    },
    {
      key: 'cal',
      title: '校准证书',
      light: calLight(cal.status),
      valueText: calValue,
      detail: cal.detail,
    },
    {
      key: 'dut',
      // DUT-attach 是后端硬编码占位符 — 永远灰色"未实现"，不假装绿/红。
      title: 'DUT attach',
      light: 'gray',
      valueText: '未实现',
      detail: report.dut_attach.detail,
    },
  ]
}

// 总判: 任一红 → 不可开测 + 原因; 否则可开测。
// 文案风格跟 commissioning precheck FAIL 一致。DUT 灰色不阻断开测
// (后端未实现感知，缺这一格不应误判为"不可开测")。
function buildVerdict(cells: Cell[]): { canStart: boolean; text: string } {
  const blockers = cells.filter((c) => c.light === 'red')
  if (blockers.length > 0) {
    const reason = blockers.map((c) => `${c.title}（${c.valueText}）`).join('、')
    return { canStart: false, text: `🔴 不可开测：${reason}` }
  }
  return { canStart: true, text: '✅ 可开测' }
}

// P1-11: per-/24-subnet 可达性小节。诚实性原则: reachable=false 才标红
// 不可达并给 runbook 提示; reachable=true 标绿; 'unknown' 桶 (解析不出 IP)
// 不假装可达也不假装不可达 —— 直接展示 cidr='unknown' + 计数, 不给红/绿断言。
function SubnetSection({ report }: { report: HALReadinessResponse }) {
  const subnets = report.subnets ?? []
  if (subnets.length === 0) return null

  return (
    <Stack gap="xs">
      <Group gap="xs">
        <IconNetwork size={16} />
        <Text size="sm" fw={600}>
          子网可达性
        </Text>
      </Group>
      <Stack gap={6}>
        {subnets.map((s) => {
          const isUnknown = s.cidr === 'unknown'
          // unknown 桶: 灰色诚实展示, 不做可达/不可达断言。
          const light: Light = isUnknown ? 'gray' : s.reachable ? 'green' : 'red'
          const mark = isUnknown ? '❔' : s.reachable ? '✅ 可达' : '🔴 不可达'
          const label = isUnknown ? '未知 (IP 无法解析)' : s.cidr
          return (
            <Card key={s.cidr} withBorder radius="sm" padding="xs">
              <Group justify="space-between" wrap="nowrap" gap="xs">
                <Group gap="xs" wrap="nowrap">
                  <LightIcon light={light} size={16} />
                  <Text size="sm" fw={500}>
                    {label}
                  </Text>
                  <Badge color={LIGHT_COLOR[light]} variant="light" size="sm">
                    {mark}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed">
                  {s.instrument_count} 台仪表
                  {s.unreachable_count > 0 ? ` · ${s.unreachable_count} 台不可达` : ''}
                </Text>
              </Group>
              {s.hint && (
                <Text size="xs" c="red.7" mt={4}>
                  {s.hint}
                </Text>
              )}
            </Card>
          )
        })}
      </Stack>
    </Stack>
  )
}

export function ZoneReadiness() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['cockpit', 'readiness'],
    queryFn: fetchReadiness,
    refetchInterval: 10_000,
  })

  return (
    <Card withBorder radius="md" padding="lg">
      <Stack gap="sm">
        <Group justify="space-between">
          <Group gap="xs">
            <IconShieldCheck size={20} />
            <Text fw={700} fz="lg">
              系统就绪
            </Text>
          </Group>
          {data && (
            <Badge
              size="lg"
              color={
                buildVerdict(buildCells(data)).canStart ? 'green' : 'red'
              }
              variant="filled"
            >
              {buildVerdict(buildCells(data)).text}
            </Badge>
          )}
        </Group>

        {isLoading && (
          <Group gap="xs">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">
              就绪状态读取中……
            </Text>
          </Group>
        )}

        {error && (
          <Alert color="red" variant="light" title="就绪状态读取失败">
            无法获取 HAL 就绪快照：{(error as Error).message}
          </Alert>
        )}

        {data && !data.available && (
          <Alert color="orange" variant="light" title="HAL 未就绪">
            HAL 尚未初始化（启动未完成或正在重新加载），以下为占位状态，不代表实时设备。
          </Alert>
        )}

        {data && (
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
            {buildCells(data).map((cell) => (
              <Card key={cell.key} withBorder radius="sm" padding="sm">
                <Stack gap={6}>
                  <Group justify="space-between" wrap="nowrap">
                    <Text size="sm" c="dimmed">
                      {cell.title}
                    </Text>
                    <LightIcon light={cell.light} />
                  </Group>
                  <Badge color={LIGHT_COLOR[cell.light]} variant="light" size="sm">
                    {cell.valueText}
                  </Badge>
                  <Text size="xs" c="dimmed" lineClamp={2} title={cell.detail}>
                    {cell.detail}
                  </Text>
                </Stack>
              </Card>
            ))}
          </SimpleGrid>
        )}

        {data && data.subnets && data.subnets.length > 0 && (
          <>
            <Divider my={4} />
            <SubnetSection report={data} />
          </>
        )}
      </Stack>
    </Card>
  )
}
