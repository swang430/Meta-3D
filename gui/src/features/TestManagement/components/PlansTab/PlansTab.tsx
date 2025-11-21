/**
 * Plans Tab - Test Plan Management
 *
 * Main container for test plan lifecycle management:
 * - Create new test plans
 * - List and filter existing plans
 * - Edit plan metadata
 * - Delete plans
 * - Queue plans for execution
 *
 * @version 2.0.0
 */

import { useState } from 'react'
import { Stack } from '@mantine/core'
import { TestPlanList } from './TestPlanList'
import { CreateTestPlanWizard } from './CreateTestPlanWizard'
import { EditTestPlanWizard } from './EditTestPlanWizard'

interface PlansTabProps {
  onSelectPlan?: (planId: string) => void
}

export function PlansTab({ onSelectPlan }: PlansTabProps) {
  const [createWizardOpened, setCreateWizardOpened] = useState(false)
  const [editWizardOpened, setEditWizardOpened] = useState(false)
  const [editingPlanId, setEditingPlanId] = useState<string | null>(null)

  const handleCreateNew = () => {
    setCreateWizardOpened(true)
  }

  const handleEdit = (planId: string) => {
    setEditingPlanId(planId)
    setEditWizardOpened(true)
  }

  const handleCreated = () => {
    setCreateWizardOpened(false)
  }

  const handleUpdated = () => {
    setEditWizardOpened(false)
    setEditingPlanId(null)
  }

  const handleSelect = (planId: string) => {
    onSelectPlan?.(planId)
  }

  return (
    <Stack gap="md">
      {/* Test Plan List */}
      <TestPlanList
        onCreateNew={handleCreateNew}
        onEdit={handleEdit}
        onSelect={handleSelect}
      />

      {/* Create Wizard Modal */}
      <CreateTestPlanWizard
        opened={createWizardOpened}
        onClose={() => setCreateWizardOpened(false)}
        onCreated={handleCreated}
      />

      {/* Edit Wizard Modal */}
      {editingPlanId && (
        <EditTestPlanWizard
          opened={editWizardOpened}
          planId={editingPlanId}
          onClose={() => {
            setEditWizardOpened(false)
            setEditingPlanId(null)
          }}
          onUpdated={handleUpdated}
        />
      )}
    </Stack>
  )
}

export default PlansTab
