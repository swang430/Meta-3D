/**
 * P2-8 主控制台重设计为操作驾驶舱 (Operational Cockpit).
 *
 * Single-screen 4-zone layout replacing the old静态计数 Dashboard +
 * 内嵌 Monitoring 演示播放器 (the latter moved to Diagnostics):
 *
 *   ① ZoneReadiness   — 顶部常驻就绪带 (能不能开测 + 阻塞原因)
 *   ② ZoneActiveRun   — 左主区 最近执行 (终结态历史)
 *   ③ ZoneLiveMetrics — 右主区 实时 WS 指标
 *   ④ ZoneLogsAlerts  — 底部宽条 实时日志 + 活动告警
 *
 * 设计原则: 计数→状态 · 实时优先 · 就绪前置 · 消灭死数据/mock.
 */
import { Stack, Grid } from '@mantine/core'
import { ZoneReadiness } from './ZoneReadiness'
import { ZoneActiveRun } from './ZoneActiveRun'
import { ZoneLiveMetrics } from './ZoneLiveMetrics'
import { ZoneLogsAlerts } from './ZoneLogsAlerts'

export function DashboardCockpit({
  onNavigateTestManagement,
}: {
  onNavigateTestManagement: () => void
}) {
  return (
    <Stack gap="lg">
      {/* ① 就绪前置 — 顶部常驻 */}
      <ZoneReadiness />

      {/* ② 运行态 (左) + ③ 实时指标 (右) */}
      <Grid gutter="lg" align="stretch">
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <ZoneActiveRun onNavigateTestManagement={onNavigateTestManagement} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <ZoneLiveMetrics />
        </Grid.Col>
      </Grid>

      {/* ④ 实时日志 + 告警 — 底部宽条 */}
      <ZoneLogsAlerts />
    </Stack>
  )
}
