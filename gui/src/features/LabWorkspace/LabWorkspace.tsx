import type { ReactNode } from 'react'
import { Alert, Box, Stack, Tabs, Text } from '@mantine/core'
import { LabOverview } from './LabOverview'

export type LabWorkspaceView = 'labWorkspace' | 'equipment' | 'probeManager' | 'topologyEditor'

export function LabWorkspace({ view, onNavigate, children }: {
  view: LabWorkspaceView
  onNavigate: (view: LabWorkspaceView) => void
  children: ReactNode
}) {
  return (
    <Stack gap="md" style={{ minWidth: 0 }}>
      <Text size="sm" c="dimmed">使用顶部所选LabProfile；总览是当前配置与运行快照，不是历史执行冻结证据。</Text>
      <Tabs value={view} onChange={next => {
        if (next === 'labWorkspace' || next === 'equipment' || next === 'probeManager' || next === 'topologyEditor') {
          onNavigate(next)
        }
      }}>
        <Tabs.List aria-label="实验室配置子视图">
          <Tabs.Tab value="labWorkspace">总览</Tabs.Tab>
          <Tabs.Tab value="equipment">仪器资源</Tabs.Tab>
          <Tabs.Tab value="probeManager">探头与暗室</Tabs.Tab>
          <Tabs.Tab value="topologyEditor">射频拓扑</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      {view === 'equipment' && <Alert color="blue">
        仪器资源为全局配置，并非所选LabProfile已同步绑定。保存后分类HAL激活；同步到LabProfile仍需单独操作。
      </Alert>}
      <Box style={{ minWidth: 0 }}>
        {view === 'labWorkspace' ? <LabOverview /> : children}
      </Box>
    </Stack>
  )
}
