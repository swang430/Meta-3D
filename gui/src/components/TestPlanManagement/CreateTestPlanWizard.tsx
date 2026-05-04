/**
 * Create Test Plan Wizard
 *
 * Refactored flow: TestCase first → Basic Info & DUT → Confirm
 * TestCase is the foundation; TestPlan organizes TestCases.
 */
import { useState, useEffect } from 'react';
import {
  Modal,
  Stepper,
  Button,
  Group,
  TextInput,
  Textarea,
  NumberInput,
  Stack,
  Text,
  MultiSelect,
  Paper,
  Badge,
  ActionIcon,
  Divider,
} from '@mantine/core';
import { IconTrash } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import {
  createTestPlan,
  listTestCases,
  markTestPlanReady,
  type CreateTestPlanRequest,
  type TestCaseSummary,
  getTestTypeLabel,
} from '../../api/testPlanService';
import { TestCaseLibrary } from './TestCaseLibrary';

interface CreateTestPlanWizardProps {
  opened: boolean;
  onClose: () => void;
  onCreated: () => void;
  /** Pre-selected test case IDs from TestCaseLibrary */
  preSelectedCaseIds?: string[];
}

export function CreateTestPlanWizard({
  opened,
  onClose,
  onCreated,
  preSelectedCaseIds = [],
}: CreateTestPlanWizardProps) {
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);

  // Step 1: Test Case Selection
  const [selectedTestCaseIds, setSelectedTestCaseIds] = useState<string[]>([]);
  const [selectedCaseDetails, setSelectedCaseDetails] = useState<TestCaseSummary[]>([]);

  // Step 2: Basic Info & DUT
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<number>(5);
  const [tags, setTags] = useState<string[]>([]);
  const [dutModel, setDutModel] = useState('');
  const [dutSerial, setDutSerial] = useState('');
  const [dutImei, setDutImei] = useState('');

  // Initialize with pre-selected cases
  useEffect(() => {
    if (opened && preSelectedCaseIds.length > 0) {
      setSelectedTestCaseIds(preSelectedCaseIds);
      // Skip to step 2 if cases are already selected
      setActive(1);
    }
  }, [opened, preSelectedCaseIds]);

  // Load case details when selection changes (for summary display)
  useEffect(() => {
    if (selectedTestCaseIds.length > 0) {
      loadSelectedCaseDetails();
    } else {
      setSelectedCaseDetails([]);
    }
  }, [selectedTestCaseIds]);

  const loadSelectedCaseDetails = async () => {
    try {
      const response = await listTestCases(0, 500);
      const details = response.items.filter((tc) =>
        selectedTestCaseIds.includes(tc.id)
      );
      setSelectedCaseDetails(details);
    } catch {
      // Silently fail - details are for display only
    }
  };

  // Auto-generate plan name from selected cases
  useEffect(() => {
    if (selectedCaseDetails.length > 0 && !name) {
      const types = [...new Set(selectedCaseDetails.map((tc) => tc.test_type))];
      const typeStr = types.map((t) => getTestTypeLabel(t)).join(' + ');
      setName(`${typeStr} 测试计划`);
    }
  }, [selectedCaseDetails]);

  const nextStep = () => {
    if (active === 0 && selectedTestCaseIds.length === 0) {
      notifications.show({
        title: '请选择测试用例',
        message: '至少选择一个测试用例才能创建测试计划',
        color: 'orange',
      });
      return;
    }

    if (active === 1) {
      if (!name) {
        notifications.show({ title: '验证失败', message: '请输入测试计划名称', color: 'red' });
        return;
      }
      if (!dutModel) {
        notifications.show({ title: '验证失败', message: '请输入 DUT 型号', color: 'red' });
        return;
      }
    }

    setActive((current) => (current < 2 ? current + 1 : current));
  };

  const prevStep = () => setActive((current) => (current > 0 ? current - 1 : current));

  const handleCreate = async () => {
    setLoading(true);
    try {
      // Calculate estimated duration from selected cases
      const totalDurationSec = selectedCaseDetails.reduce(
        (sum, tc) => sum + (tc.test_duration_sec || 0),
        0
      );

      const request: CreateTestPlanRequest = {
        name,
        description,
        version: '1.0',
        dut_info: {
          model: dutModel,
          serial: dutSerial,
          imei: dutImei,
        },
        test_environment: {
          chamber_id: 'MPAC-001',
          temperature: 25,
          humidity: 50,
          estimated_duration_sec: totalDurationSec,
        },
        test_case_ids: selectedTestCaseIds,
        priority,
        created_by: '当前用户',
        tags,
      };

      const testPlan = await createTestPlan(request);

      // Auto mark as ready since cases are selected
      if (selectedTestCaseIds.length > 0) {
        try {
          await markTestPlanReady(testPlan.id);
        } catch {
          // Not critical if mark-ready fails
        }
      }

      notifications.show({
        title: '创建成功',
        message: `测试计划 "${name}" 已创建，包含 ${selectedTestCaseIds.length} 个测试用例`,
        color: 'green',
      });

      handleClose();
      onCreated();
    } catch (error) {
      notifications.show({
        title: '创建失败',
        message: '无法创建测试计划',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setActive(0);
    setName('');
    setDescription('');
    setPriority(5);
    setTags([]);
    setDutModel('');
    setDutSerial('');
    setDutImei('');
    setSelectedTestCaseIds([]);
    setSelectedCaseDetails([]);
    onClose();
  };

  const removeCase = (id: string) => {
    setSelectedTestCaseIds((prev) => prev.filter((x) => x !== id));
  };

  // Estimated total duration
  const totalMinutes = Math.round(
    selectedCaseDetails.reduce((sum, tc) => sum + (tc.test_duration_sec || 0), 0) / 60
  );

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title="创建测试计划"
      size="xl"
      closeOnClickOutside={false}
    >
      <Stepper active={active} onStepClick={setActive}>
        {/* Step 1: Select Test Cases */}
        <Stepper.Step label="选择用例" description="从标准库选择">
          <Stack gap="md" mt="md">
            <TestCaseLibrary
              selectionMode
              selectedIds={selectedTestCaseIds}
              onSelectionChange={setSelectedTestCaseIds}
            />
          </Stack>
        </Stepper.Step>

        {/* Step 2: Plan Info & DUT */}
        <Stepper.Step label="计划配置" description="基本信息与 DUT">
          <Stack gap="md" mt="xl">
            {/* Selected cases summary */}
            <Paper p="sm" withBorder radius="md" bg="blue.0">
              <Group justify="space-between" mb="xs">
                <Text size="sm" fw={600} c="blue.8">
                  已选 {selectedTestCaseIds.length} 个用例 · 预计 {totalMinutes} 分钟
                </Text>
              </Group>
              <Group gap={6} wrap="wrap">
                {selectedCaseDetails.map((tc) => (
                  <Badge
                    key={tc.id}
                    variant="light"
                    rightSection={
                      <ActionIcon
                        size="xs"
                        color="blue"
                        radius="xl"
                        variant="transparent"
                        onClick={() => removeCase(tc.id)}
                      >
                        <IconTrash size={10} />
                      </ActionIcon>
                    }
                  >
                    {tc.name}
                  </Badge>
                ))}
              </Group>
            </Paper>

            <Divider label="测试计划信息" labelPosition="left" />

            <TextInput
              label="测试计划名称"
              placeholder="例如：5G NR MIMO 性能测试 v1.0"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />

            <Textarea
              label="描述"
              placeholder="测试计划的详细说明..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              minRows={2}
            />

            <Group grow>
              <NumberInput
                label="优先级"
                description="1 = 最高，10 = 最低"
                value={priority}
                onChange={(val) => setPriority(typeof val === 'number' ? val : 5)}
                min={1}
                max={10}
              />
              <MultiSelect
                label="标签"
                placeholder="选择或创建"
                data={['5G', 'LTE', 'MIMO', '性能测试', '合规性测试']}
                value={tags}
                onChange={setTags}
                searchable
              />
            </Group>

            <Divider label="被测设备 (DUT)" labelPosition="left" />

            <TextInput
              label="DUT 型号"
              placeholder="例如：iPhone 15 Pro / 大众 ID.4"
              value={dutModel}
              onChange={(e) => setDutModel(e.target.value)}
              required
            />

            <Group grow>
              <TextInput
                label="序列号"
                placeholder="SN123456789"
                value={dutSerial}
                onChange={(e) => setDutSerial(e.target.value)}
              />
              <TextInput
                label="IMEI"
                placeholder="123456789012345"
                value={dutImei}
                onChange={(e) => setDutImei(e.target.value)}
              />
            </Group>
          </Stack>
        </Stepper.Step>

        {/* Step 3: Confirm */}
        <Stepper.Step label="确认创建" description="检查并提交">
          <Stack gap="md" mt="xl">
            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="md">测试计划概要</Text>
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">名称:</Text>
                  <Text size="sm" fw={500}>{name}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">DUT:</Text>
                  <Text size="sm">{dutModel}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">优先级:</Text>
                  <Badge size="sm" color="gray" variant="outline">P{priority}</Badge>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">测试用例数量:</Text>
                  <Text size="sm" fw={500}>{selectedTestCaseIds.length}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">预计总时长:</Text>
                  <Text size="sm">
                    {totalMinutes >= 60
                      ? `${Math.floor(totalMinutes / 60)}h ${totalMinutes % 60}m`
                      : `${totalMinutes} min`}
                  </Text>
                </Group>
                {tags.length > 0 && (
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">标签:</Text>
                    <Group gap="xs">
                      {tags.map((tag) => (
                        <Badge key={tag} size="xs" variant="light">{tag}</Badge>
                      ))}
                    </Group>
                  </Group>
                )}
              </Stack>
            </Paper>

            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="sm">包含的测试用例</Text>
              <Stack gap={4}>
                {selectedCaseDetails.map((tc, idx) => (
                  <Group key={tc.id} justify="space-between">
                    <Text size="xs">
                      {idx + 1}. {tc.name}
                    </Text>
                    <Group gap="xs">
                      <Badge size="xs" variant="light">
                        {getTestTypeLabel(tc.test_type)}
                      </Badge>
                      {tc.frequency_mhz && (
                        <Text size="xs" c="dimmed">{tc.frequency_mhz} MHz</Text>
                      )}
                    </Group>
                  </Group>
                ))}
              </Stack>
            </Paper>

            {description && (
              <Paper p="md" withBorder>
                <Text size="sm" fw={600} mb="xs">描述</Text>
                <Text size="sm" c="dimmed">{description}</Text>
              </Paper>
            )}
          </Stack>
        </Stepper.Step>
      </Stepper>

      <Group justify="right" mt="xl">
        {active > 0 && (
          <Button variant="default" onClick={prevStep}>
            上一步
          </Button>
        )}
        {active < 2 && (
          <Button onClick={nextStep}>
            下一步
          </Button>
        )}
        {active === 2 && (
          <Button onClick={handleCreate} loading={loading}>
            创建测试计划
          </Button>
        )}
      </Group>
    </Modal>
  );
}
