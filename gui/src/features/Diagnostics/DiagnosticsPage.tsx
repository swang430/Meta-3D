/**
 * P3 Phase 2: Diagnostics page entry.
 *
 * Hosts the SequenceRunnerPanel + Commissioning ad-hoc single-phase tab.
 * P2-8 moved the legacy Monitoring 演示回放 (demoPlan / scenarioMetrics /
 * timeline player) here from the old Dashboard case — it's a developer /
 * 调试 surface, not an operational view, so it belongs in 调试维护. It's
 * passed in as `monitoringSlot` because the player is still defined inline
 * in App.tsx (deeply coupled to App's demo-run state) and rendered into
 * this tab.
 */
import type { ReactNode } from 'react'
import { Container, Stack, Tabs, Title, Group, Badge } from '@mantine/core'
import { IconAdjustments, IconTerminal, IconTool, IconPlayerPlay, IconRotate } from '@tabler/icons-react'

import { SequenceRunnerPanel } from './SequenceRunnerPanel'
import { CommissioningAdhocPanel } from './CommissioningAdhocPanel'
import { PositionerControlPanel } from './PositionerControlPanel'

export function DiagnosticsPage({ monitoringSlot }: { monitoringSlot?: ReactNode }) {
  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        <Group gap="xs">
          <IconTool size={22} />
          <Title order={3}>调试维护</Title>
          <Badge color="orange" variant="light">workshop tier</Badge>
        </Group>
        <Tabs defaultValue="sequences">
          <Tabs.List>
            <Tabs.Tab value="sequences" leftSection={<IconTerminal size={14} />}>
              调试序列
            </Tabs.Tab>
            <Tabs.Tab value="adhoc_phase" leftSection={<IconAdjustments size={14} />}>
              单阶段 ad-hoc
            </Tabs.Tab>
            <Tabs.Tab value="positioner" leftSection={<IconRotate size={14} />}>
              转台控制
            </Tabs.Tab>
            {monitoringSlot && (
              <Tabs.Tab value="demo_playback" leftSection={<IconPlayerPlay size={14} />}>
                演示回放
              </Tabs.Tab>
            )}
          </Tabs.List>

          <Tabs.Panel value="sequences" pt="md">
            <SequenceRunnerPanel />
          </Tabs.Panel>
          <Tabs.Panel value="adhoc_phase" pt="md">
            <CommissioningAdhocPanel />
          </Tabs.Panel>
          <Tabs.Panel value="positioner" pt="md">
            <PositionerControlPanel />
          </Tabs.Panel>
          {monitoringSlot && (
            <Tabs.Panel value="demo_playback" pt="md">
              {monitoringSlot}
            </Tabs.Panel>
          )}
        </Tabs>
      </Stack>
    </Container>
  )
}
