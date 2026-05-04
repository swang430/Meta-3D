/**
 * Test Plan Management Main Component
 *
 * Unified test management hub with TestCase Library as the foundation.
 * Structure: 用例库 (首页) → 测试计划 → 执行队列 → 执行历史
 */
import { useState } from 'react';
import { Container, Tabs, Badge, Group } from '@mantine/core';
import {
  IconChecklist,
  IconList,
  IconClock,
  IconChartBar,
} from '@tabler/icons-react';
import { TestCaseLibrary } from './TestCaseLibrary';
import { TestPlanList } from './TestPlanList';
import { CreateTestPlanWizard } from './CreateTestPlanWizard';
import { EditTestPlanWizard } from './EditTestPlanWizard';
import { TestQueue } from './TestQueue';
import { TestExecutionHistory } from './TestExecutionHistory';

export function TestPlanManagement() {
  const [createWizardOpened, setCreateWizardOpened] = useState(false);
  const [editWizardOpened, setEditWizardOpened] = useState(false);
  const [editingTestPlanId, setEditingTestPlanId] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Pre-selected test case IDs (passed from TestCaseLibrary → CreateTestPlanWizard)
  const [preSelectedCaseIds, setPreSelectedCaseIds] = useState<string[]>([]);

  const handleCreateNew = () => {
    setPreSelectedCaseIds([]);
    setCreateWizardOpened(true);
  };

  const handleCreateFromSelection = (selectedIds: string[]) => {
    setPreSelectedCaseIds(selectedIds);
    setCreateWizardOpened(true);
  };

  const handleEdit = (id: string) => {
    setEditingTestPlanId(id);
    setEditWizardOpened(true);
  };

  const handleCreated = () => {
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleUpdated = () => {
    setRefreshTrigger((prev) => prev + 1);
  };

  return (
    <Container size="xl" py="md">
      <Tabs defaultValue="caseLibrary">
        <Tabs.List>
          <Tabs.Tab value="caseLibrary" leftSection={<IconChecklist size={16} />}>
            测试用例库
          </Tabs.Tab>
          <Tabs.Tab value="plans" leftSection={<IconList size={16} />}>
            测试计划
          </Tabs.Tab>
          <Tabs.Tab value="queue" leftSection={<IconClock size={16} />}>
            执行队列
          </Tabs.Tab>
          <Tabs.Tab value="history" leftSection={<IconChartBar size={16} />}>
            执行历史
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="caseLibrary" pt="md">
          <TestCaseLibrary
            onCreateNew={handleCreateNew}
          />
        </Tabs.Panel>

        <Tabs.Panel value="plans" pt="md">
          <TestPlanList
            key={refreshTrigger}
            onCreateNew={handleCreateNew}
            onEdit={handleEdit}
          />
        </Tabs.Panel>

        <Tabs.Panel value="queue" pt="md">
          <TestQueue />
        </Tabs.Panel>

        <Tabs.Panel value="history" pt="md">
          <TestExecutionHistory />
        </Tabs.Panel>
      </Tabs>

      <CreateTestPlanWizard
        opened={createWizardOpened}
        onClose={() => setCreateWizardOpened(false)}
        onCreated={handleCreated}
        preSelectedCaseIds={preSelectedCaseIds}
      />

      <EditTestPlanWizard
        opened={editWizardOpened}
        testPlanId={editingTestPlanId}
        onClose={() => {
          setEditWizardOpened(false);
          setEditingTestPlanId(null);
        }}
        onUpdated={handleUpdated}
      />
    </Container>
  );
}
