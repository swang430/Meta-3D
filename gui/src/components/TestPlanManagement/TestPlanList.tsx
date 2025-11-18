/**
 * Test Plan List Component
 *
 * Displays a list of test plans with filtering and actions
 */
import { useState, useEffect } from 'react';
import {
  Stack,
  Paper,
  Title,
  Group,
  Button,
  Table,
  Badge,
  ActionIcon,
  Text,
  Select,
  TextInput,
  Progress,
  Tooltip,
  Menu,
  Modal,
} from '@mantine/core';
import {
  IconPlus,
  IconRefresh,
  IconPlayerPlay,
  IconPlayerPause,
  IconPlayerStop,
  IconEdit,
  IconTrash,
  IconDots,
  IconClock,
  IconSearch,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import {
  listTestPlans,
  deleteTestPlan,
  startTestPlan,
  pauseTestPlan,
  cancelTestPlan,
  queueTestPlan,
  getStatusColor,
  getStatusLabel,
  type TestPlanSummary,
  type TestPlanStatus,
} from '../../api/testPlanService';

interface TestPlanListProps {
  onCreateNew: () => void;
  onEdit: (id: string) => void;
}

export function TestPlanList({ onCreateNew, onEdit }: TestPlanListProps) {
  const [testPlans, setTestPlans] = useState<TestPlanSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [deleteModalOpened, setDeleteModalOpened] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);

  const loadTestPlans = async () => {
    setLoading(true);
    try {
      const response = await listTestPlans(
        0,
        100,
        statusFilter as TestPlanStatus | undefined
      );
      setTestPlans(response.items);
    } catch (error) {
      notifications.show({
        title: '加载失败',
        message: '无法加载测试计划列表',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTestPlans();
  }, [statusFilter]);

  const handleStart = async (id: string) => {
    try {
      await startTestPlan(id, '当前用户');
      notifications.show({
        title: '启动成功',
        message: '测试计划已开始执行',
        color: 'green',
      });
      loadTestPlans();
    } catch (error) {
      notifications.show({
        title: '启动失败',
        message: '无法启动测试计划',
        color: 'red',
      });
    }
  };

  const handlePause = async (id: string) => {
    try {
      await pauseTestPlan(id, '当前用户');
      notifications.show({
        title: '暂停成功',
        message: '测试计划已暂停',
        color: 'blue',
      });
      loadTestPlans();
    } catch (error) {
      notifications.show({
        title: '暂停失败',
        message: '无法暂停测试计划',
        color: 'red',
      });
    }
  };

  const handleCancel = async (id: string) => {
    try {
      await cancelTestPlan(id, '当前用户');
      notifications.show({
        title: '取消成功',
        message: '测试计划已取消',
        color: 'orange',
      });
      loadTestPlans();
    } catch (error) {
      notifications.show({
        title: '取消失败',
        message: '无法取消测试计划',
        color: 'red',
      });
    }
  };

  const handleQueue = async (id: string) => {
    try {
      await queueTestPlan({
        test_plan_id: id,
        priority: 5,
        queued_by: '当前用户',
      });
      notifications.show({
        title: '排队成功',
        message: '测试计划已添加到执行队列',
        color: 'green',
      });
      loadTestPlans();
    } catch (error) {
      notifications.show({
        title: '排队失败',
        message: '无法添加到队列',
        color: 'red',
      });
    }
  };

  const handleDelete = async () => {
    if (!selectedPlanId) return;

    try {
      await deleteTestPlan(selectedPlanId);
      notifications.show({
        title: '删除成功',
        message: '测试计划已删除',
        color: 'green',
      });
      setDeleteModalOpened(false);
      setSelectedPlanId(null);
      loadTestPlans();
    } catch (error) {
      notifications.show({
        title: '删除失败',
        message: '无法删除测试计划',
        color: 'red',
      });
    }
  };

  const openDeleteModal = (id: string) => {
    setSelectedPlanId(id);
    setDeleteModalOpened(true);
  };

  const filteredPlans = testPlans.filter((plan) =>
    plan.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between">
        <Title order={2}>测试计划管理</Title>
        <Group>
          <Button
            leftSection={<IconRefresh size={16} />}
            variant="light"
            onClick={loadTestPlans}
            loading={loading}
          >
            刷新
          </Button>
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={onCreateNew}
          >
            创建测试计划
          </Button>
        </Group>
      </Group>

      {/* Filters */}
      <Paper p="md" withBorder>
        <Group>
          <TextInput
            placeholder="搜索测试计划..."
            leftSection={<IconSearch size={16} />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <Select
            placeholder="状态筛选"
            clearable
            value={statusFilter}
            onChange={setStatusFilter}
            data={[
              { value: 'draft', label: '草稿' },
              { value: 'ready', label: '就绪' },
              { value: 'queued', label: '已排队' },
              { value: 'running', label: '执行中' },
              { value: 'paused', label: '已暂停' },
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
              { value: 'cancelled', label: '已取消' },
            ]}
            style={{ width: 200 }}
          />
        </Group>
      </Paper>

      {/* Table */}
      <Paper withBorder>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>名称</Table.Th>
              <Table.Th>状态</Table.Th>
              <Table.Th>进度</Table.Th>
              <Table.Th>测试用例</Table.Th>
              <Table.Th>优先级</Table.Th>
              <Table.Th>创建者</Table.Th>
              <Table.Th>创建时间</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filteredPlans.length === 0 ? (
              <Table.Tr>
                <Table.Td colSpan={8}>
                  <Text ta="center" c="dimmed" py="xl">
                    {loading ? '加载中...' : '暂无测试计划'}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              filteredPlans.map((plan) => {
                const progress =
                  plan.total_test_cases > 0
                    ? Math.round((plan.completed_test_cases / plan.total_test_cases) * 100)
                    : 0;

                return (
                  <Table.Tr key={plan.id}>
                    <Table.Td>
                      <Text fw={500}>{plan.name}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={getStatusColor(plan.status)} variant="light">
                        {getStatusLabel(plan.status)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Progress
                          value={progress}
                          size="sm"
                          style={{ flex: 1, minWidth: 100 }}
                          color={plan.failed_test_cases > 0 ? 'red' : 'blue'}
                        />
                        <Text size="xs" c="dimmed">
                          {plan.completed_test_cases}/{plan.total_test_cases}
                        </Text>
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{plan.total_test_cases}</Text>
                      {plan.failed_test_cases > 0 && (
                        <Text size="xs" c="red">
                          {plan.failed_test_cases} 失败
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Badge size="sm" color="gray" variant="outline">
                        P{plan.priority}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{plan.created_by}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Tooltip label={new Date(plan.created_at).toLocaleString()}>
                        <Text size="sm" c="dimmed">
                          {new Date(plan.created_at).toLocaleDateString()}
                        </Text>
                      </Tooltip>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        {/* Status-based actions */}
                        {plan.status === 'ready' && (
                          <Tooltip label="添加到队列">
                            <ActionIcon
                              variant="light"
                              color="blue"
                              onClick={() => handleQueue(plan.id)}
                            >
                              <IconClock size={16} />
                            </ActionIcon>
                          </Tooltip>
                        )}
                        {plan.status === 'queued' && (
                          <Tooltip label="开始执行">
                            <ActionIcon
                              variant="light"
                              color="green"
                              onClick={() => handleStart(plan.id)}
                            >
                              <IconPlayerPlay size={16} />
                            </ActionIcon>
                          </Tooltip>
                        )}
                        {plan.status === 'running' && (
                          <Tooltip label="暂停">
                            <ActionIcon
                              variant="light"
                              color="orange"
                              onClick={() => handlePause(plan.id)}
                            >
                              <IconPlayerPause size={16} />
                            </ActionIcon>
                          </Tooltip>
                        )}

                        {/* More actions menu */}
                        <Menu position="bottom-end">
                          <Menu.Target>
                            <ActionIcon variant="subtle">
                              <IconDots size={16} />
                            </ActionIcon>
                          </Menu.Target>
                          <Menu.Dropdown>
                            <Menu.Item
                              leftSection={<IconEdit size={14} />}
                              onClick={() => onEdit(plan.id)}
                            >
                              编辑
                            </Menu.Item>
                            {['running', 'paused', 'queued'].includes(plan.status) && (
                              <Menu.Item
                                leftSection={<IconPlayerStop size={14} />}
                                color="orange"
                                onClick={() => handleCancel(plan.id)}
                              >
                                取消执行
                              </Menu.Item>
                            )}
                            <Menu.Divider />
                            <Menu.Item
                              leftSection={<IconTrash size={14} />}
                              color="red"
                              onClick={() => openDeleteModal(plan.id)}
                              disabled={['running', 'queued'].includes(plan.status)}
                            >
                              删除
                            </Menu.Item>
                          </Menu.Dropdown>
                        </Menu>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                );
              })
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      {/* Delete Confirmation Modal */}
      <Modal
        opened={deleteModalOpened}
        onClose={() => setDeleteModalOpened(false)}
        title="确认删除"
      >
        <Text mb="md">确定要删除此测试计划吗？此操作无法撤销。</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setDeleteModalOpened(false)}>
            取消
          </Button>
          <Button color="red" onClick={handleDelete}>
            删除
          </Button>
        </Group>
      </Modal>
    </Stack>
  );
}
