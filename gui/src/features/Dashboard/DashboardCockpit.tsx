/**
 * P2-8 主控制台重设计为操作驾驶舱 (Operational Cockpit).
 *
 * Single-screen 3-zone layout replacing the old静态计数 Dashboard +
 * 内嵌 Monitoring 演示播放器 (the latter moved to Diagnostics):
 *
 *   ① ZoneReadiness   — 顶部常驻就绪带 (能不能开测 + 阻塞原因)
 *   ② ZoneActiveRun   — 左主区 最近执行 (终结态历史)
 *   ③ ZoneLogsAlerts  — 右主区 实时日志 + 紧凑告警计数
 *
 * 设计原则: 计数→状态 · 就绪前置 · 排障信息邻接执行 · 消灭死数据/mock.
 */
import { Stack, Grid } from '@mantine/core'
import { ZoneReadiness } from './ZoneReadiness'
import { ZoneActiveRun } from './ZoneActiveRun'
import { ZoneLogsAlerts } from './ZoneLogsAlerts'
import {
  dashboardMainZones,
  type DashboardMainZone,
} from './dashboardCockpitLayout'

function renderMainZone(
  zone: DashboardMainZone,
  onNavigateTestManagement: () => void,
) {
  if (zone === 'recentExecutions') {
    return <ZoneActiveRun onNavigateTestManagement={onNavigateTestManagement} />
  }
  return <ZoneLogsAlerts />
}

export function DashboardCockpit({
  onNavigateTestManagement,
}: {
  onNavigateTestManagement: () => void
}) {
  return (
    <Stack gap="lg">
      {/* ① 就绪前置 — 顶部常驻 */}
      <ZoneReadiness />

      {/* ② 最近执行 (左) + ③ 实时日志 (右) */}
      <Grid gutter="lg" align="stretch">
        {dashboardMainZones().map((zone) => (
          <Grid.Col key={zone} span={{ base: 12, lg: 6 }}>
            {renderMainZone(zone, onNavigateTestManagement)}
          </Grid.Col>
        ))}
      </Grid>
    </Stack>
  )
}
