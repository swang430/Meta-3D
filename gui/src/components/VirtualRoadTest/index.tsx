import { Stack, Title } from '@mantine/core'
import ScenarioLibrary from './ScenarioLibrary'

export type ExecutionLink = { id: string; mode: import('../../types/roadTest').TestMode }
export type SceneHistoryLink = (scene: { id: string; name: string }, execution?: ExecutionLink) => void

export function VirtualRoadTest({ onViewHistory }: { onViewHistory: SceneHistoryLink }) {
  return <Stack>
    <Title order={3}>道路信道场景库</Title>
    <ScenarioLibrary onViewHistory={onViewHistory} />
  </Stack>
}
