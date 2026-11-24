import { Modal, Text } from '@mantine/core'
import type { ScenarioSummary, TestMode } from '../../types/roadTest'
import { ConductedExecutionModal } from './ConductedExecutionModal'
import { DigitalTwinExecutionModal } from './DigitalTwinExecutionModal'

interface Props {
  opened: boolean
  onClose: () => void
  scenario: ScenarioSummary
  testMode?: TestMode
}

export function TestExecutionModal(props: Props) {
  if (props.testMode === 'conducted') return <ConductedExecutionModal key={props.scenario.id} {...props} />
  if (props.testMode === 'digital_twin') return props.opened && <DigitalTwinExecutionModal {...props} />
  return <Modal opened={props.opened} onClose={props.onClose} title="执行测试">
    <Text>当前入口支持传导测试和数字孪生。要运行软件模拟，请先选择数字孪生模式。</Text>
  </Modal>
}
