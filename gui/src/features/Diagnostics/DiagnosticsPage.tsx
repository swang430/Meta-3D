/**
 * P3 Phase 2: Diagnostics page entry.
 *
 * Currently hosts only the SequenceRunnerPanel. Phase 3 adds the
 * Commissioning ad-hoc single-phase tab here too; Phase 4 reorganizes the
 * sidebar so commissioning + diagnostics live under one "调试维护" group.
 */
import { Container, Stack, Tabs, Title, Group, Badge } from '@mantine/core'
import { IconTerminal, IconTool } from '@tabler/icons-react'

import { SequenceRunnerPanel } from './SequenceRunnerPanel'

export function DiagnosticsPage() {
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
          </Tabs.List>

          <Tabs.Panel value="sequences" pt="md">
            <SequenceRunnerPanel />
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Container>
  )
}
