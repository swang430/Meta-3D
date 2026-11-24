import type { ScenarioSummary, TestMode } from '../../types/roadTest'
import { OtaExecutionModal } from './OtaExecutionModal'
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
  return <OtaExecutionModal key={'ota:' + props.scenario.id} {...props} />
}
