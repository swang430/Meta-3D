/**
 * Edit Test Plan Wizard
 *
 * Multi-step wizard for editing an existing test plan
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
  Table,
  Checkbox,
  Badge,
  ActionIcon,
  LoadingOverlay,
} from '@mantine/core';
import { IconTrash, IconPlus } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import {
  getTestPlan,
  updateTestPlan,
  listTestCases,
  type UpdateTestPlanRequest,
  type TestCaseSummary,
  getTestTypeLabel,
} from '../../api/testPlanService';

interface EditTestPlanWizardProps {
  opened: boolean;
  testPlanId: string | null;
  onClose: () => void;
  onUpdated: () => void;
}

export function EditTestPlanWizard({ opened, testPlanId, onClose, onUpdated }: EditTestPlanWizardProps) {
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);

  // Step 1: Basic Info
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<number>(5);
  const [tags, setTags] = useState<string[]>([]);

  // Step 2: DUT Info
  const [dutModel, setDutModel] = useState('');
  const [dutSerial, setDutSerial] = useState('');
  const [dutImei, setDutImei] = useState('');

  // Step 3: Test Cases
  const [availableTestCases, setAvailableTestCases] = useState<TestCaseSummary[]>([]);
  const [selectedTestCaseIds, setSelectedTestCaseIds] = useState<string[]>([]);

  // Load test plan data
  useEffect(() => {
    if (opened && testPlanId) {
      loadTestPlanData();
    }
  }, [opened, testPlanId]);

  // Load available test cases when reaching step 3
  useEffect(() => {
    if (active === 2) {
      loadTestCases();
    }
  }, [active]);

  const loadTestPlanData = async () => {
    if (!testPlanId) return;

    setInitialLoading(true);
    try {
      const testPlan = await getTestPlan(testPlanId);

      // Populate form fields
      setName(testPlan.name);
      setDescription(testPlan.description || '');
      setPriority(testPlan.priority);
      setTags(testPlan.tags || []);

      // DUT Info
      if (testPlan.dut_info) {
        setDutModel(testPlan.dut_info.model || '');
        setDutSerial(testPlan.dut_info.serial || '');
        setDutImei(testPlan.dut_info.imei || '');
      }

      // Test cases
      setSelectedTestCaseIds(testPlan.test_case_ids || []);
    } catch (error) {
      notifications.show({
        title: '加载失败',
        message: '无法加载测试计划数据',
        color: 'red',
      });
      onClose();
    } finally {
      setInitialLoading(false);
    }
  };

  const loadTestCases = async () => {
    try {
      const response = await listTestCases(0, 100);
      setAvailableTestCases(response.items);
    } catch (error) {
      notifications.show({
        title: '加载失败',
        message: '无法加载测试用例列表',
        color: 'red',
      });
    }
  };

  const nextStep = () => {
    // Validation
    if (active === 0 && !name) {
      notifications.show({
        title: '验证失败',
        message: '请输入测试计划名称',
        color: 'red',
      });
      return;
    }

    if (active === 1 && !dutModel) {
      notifications.show({
        title: '验证失败',
        message: '请输入 DUT 型号',
        color: 'red',
      });
      return;
    }

    setActive((current) => (current < 3 ? current + 1 : current));
  };

  const prevStep = () => setActive((current) => (current > 0 ? current - 1 : current));

  const handleUpdate = async () => {
    if (!testPlanId) return;

    setLoading(true);
    try {
      const request: UpdateTestPlanRequest = {
        name,
        description,
        dut_info: {
          model: dutModel,
          serial: dutSerial,
          imei: dutImei,
        },
        test_case_ids: selectedTestCaseIds,
        priority,
        tags,
      };

      await updateTestPlan(testPlanId, request);

      notifications.show({
        title: '更新成功',
        message: `测试计划 "${name}" 已更新`,
        color: 'green',
      });

      handleClose();
      onUpdated();
    } catch (error) {
      notifications.show({
        title: '更新失败',
        message: '无法更新测试计划',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    // Reset form
    setActive(0);
    setName('');
    setDescription('');
    setPriority(5);
    setTags([]);
    setDutModel('');
    setDutSerial('');
    setDutImei('');
    setSelectedTestCaseIds([]);
    onClose();
  };

  const toggleTestCase = (id: string) => {
    setSelectedTestCaseIds((current) =>
      current.includes(id)
        ? current.filter((tcId) => tcId !== id)
        : [...current, id]
    );
  };

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title="编辑测试计划"
      size="xl"
      closeOnClickOutside={false}
    >
      <LoadingOverlay visible={initialLoading} />

      <Stepper active={active} onStepClick={setActive}>
        {/* Step 1: Basic Info */}
        <Stepper.Step label="基本信息" description="测试计划基本信息">
          <Stack gap="md" mt="xl">
            <TextInput
              label="测试计划名称"
              placeholder="例如：5G NR 性能测试 - 版本 1.0"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />

            <Textarea
              label="描述"
              placeholder="测试计划的详细说明..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              minRows={3}
            />

            <NumberInput
              label="优先级"
              description="1 = 最高优先级，10 = 最低优先级"
              value={priority}
              onChange={(val) => setPriority(typeof val === 'number' ? val : 5)}
              min={1}
              max={10}
              required
            />

            <MultiSelect
              label="标签"
              placeholder="选择或创建标签"
              data={['5G', 'LTE', 'MIMO', '性能测试', '合规性测试']}
              value={tags}
              onChange={setTags}
              searchable
            />
          </Stack>
        </Stepper.Step>

        {/* Step 2: DUT Info */}
        <Stepper.Step label="DUT 信息" description="被测设备信息">
          <Stack gap="md" mt="xl">
            <Text size="sm" c="dimmed">
              配置被测设备（DUT）的基本信息
            </Text>

            <TextInput
              label="DUT 型号"
              placeholder="例如：iPhone 15 Pro"
              value={dutModel}
              onChange={(e) => setDutModel(e.target.value)}
              required
            />

            <TextInput
              label="序列号"
              placeholder="例如：SN123456789"
              value={dutSerial}
              onChange={(e) => setDutSerial(e.target.value)}
            />

            <TextInput
              label="IMEI"
              placeholder="例如：123456789012345"
              value={dutImei}
              onChange={(e) => setDutImei(e.target.value)}
            />

            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="xs">
                测试环境
              </Text>
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">暗室 ID:</Text>
                  <Text size="sm">MPAC-001</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">温度:</Text>
                  <Text size="sm">25°C</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">湿度:</Text>
                  <Text size="sm">50%</Text>
                </Group>
              </Stack>
            </Paper>
          </Stack>
        </Stepper.Step>

        {/* Step 3: Test Cases */}
        <Stepper.Step label="测试用例" description="选择测试用例">
          <Stack gap="md" mt="xl">
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                从下方列表中选择要执行的测试用例
              </Text>
              <Button
                size="xs"
                leftSection={<IconPlus size={14} />}
                variant="light"
                onClick={() => notifications.show({
                  title: '提示',
                  message: '此功能将在后续版本中实现',
                  color: 'blue',
                })}
              >
                创建新用例
              </Button>
            </Group>

            <Paper withBorder>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th style={{ width: 40 }}>选择</Table.Th>
                    <Table.Th>名称</Table.Th>
                    <Table.Th>类型</Table.Th>
                    <Table.Th>频率</Table.Th>
                    <Table.Th>时长</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {availableTestCases.length === 0 ? (
                    <Table.Tr>
                      <Table.Td colSpan={5}>
                        <Text ta="center" c="dimmed" py="md">
                          暂无可用的测试用例
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ) : (
                    availableTestCases.map((tc) => (
                      <Table.Tr key={tc.id}>
                        <Table.Td>
                          <Checkbox
                            checked={selectedTestCaseIds.includes(tc.id)}
                            onChange={() => toggleTestCase(tc.id)}
                          />
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{tc.name}</Text>
                          {tc.is_template && (
                            <Badge size="xs" variant="light" color="blue" ml="xs">
                              模板
                            </Badge>
                          )}
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{getTestTypeLabel(tc.test_type)}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">
                            {tc.frequency_mhz ? `${tc.frequency_mhz} MHz` : '-'}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">
                            {tc.test_duration_sec ? `${Math.round(tc.test_duration_sec / 60)} 分钟` : '-'}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ))
                  )}
                </Table.Tbody>
              </Table>
            </Paper>

            {selectedTestCaseIds.length > 0 && (
              <Paper p="md" withBorder>
                <Text size="sm" fw={600} mb="xs">
                  已选择 {selectedTestCaseIds.length} 个测试用例
                </Text>
                <Group gap="xs">
                  {selectedTestCaseIds.map((id) => {
                    const tc = availableTestCases.find((t) => t.id === id);
                    return tc ? (
                      <Badge
                        key={id}
                        variant="light"
                        rightSection={
                          <ActionIcon
                            size="xs"
                            color="blue"
                            radius="xl"
                            variant="transparent"
                            onClick={() => toggleTestCase(id)}
                          >
                            <IconTrash size={10} />
                          </ActionIcon>
                        }
                      >
                        {tc.name}
                      </Badge>
                    ) : null;
                  })}
                </Group>
              </Paper>
            )}
          </Stack>
        </Stepper.Step>

        {/* Step 4: Summary */}
        <Stepper.Step label="确认" description="检查并更新">
          <Stack gap="md" mt="xl">
            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="md">
                测试计划概要
              </Text>
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
                  <Text size="sm">{selectedTestCaseIds.length}</Text>
                </Group>
                {tags.length > 0 && (
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">标签:</Text>
                    <Group gap="xs">
                      {tags.map((tag) => (
                        <Badge key={tag} size="xs" variant="light">
                          {tag}
                        </Badge>
                      ))}
                    </Group>
                  </Group>
                )}
              </Stack>
            </Paper>

            {description && (
              <Paper p="md" withBorder>
                <Text size="sm" fw={600} mb="xs">
                  描述
                </Text>
                <Text size="sm" c="dimmed">
                  {description}
                </Text>
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
        {active < 3 && (
          <Button onClick={nextStep}>
            下一步
          </Button>
        )}
        {active === 3 && (
          <Button onClick={handleUpdate} loading={loading}>
            更新测试计划
          </Button>
        )}
      </Group>
    </Modal>
  );
}
