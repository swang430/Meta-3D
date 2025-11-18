/**
 * Test Queue Component
 *
 * Displays and manages the test execution queue
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
  Tooltip,
  Progress,
} from '@mantine/core';
import { IconRefresh, IconPlayerPlay, IconTrash } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import {
  getTestQueue,
  removeFromQueue,
  startTestPlan,
  getStatusColor,
  getStatusLabel,
  type TestQueueSummary,
} from '../../api/testPlanService';

export function TestQueue() {
  const [queueItems, setQueueItems] = useState<TestQueueSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const loadQueue = async () => {
    setLoading(true);
    try {
      const response = await getTestQueue(0, 100);
      setQueueItems(response.items);
    } catch (error) {
      notifications.show({
        title: '加载失败',
        message: '无法加载测试队列',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
    // Auto-refresh every 10 seconds
    const interval = setInterval(loadQueue, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleStart = async (test_plan_id: string) => {
    try {
      await startTestPlan(test_plan_id, '当前用户');
      notifications.show({
        title: '启动成功',
        message: '测试计划已开始执行',
        color: 'green',
      });
      loadQueue();
    } catch (error) {
      notifications.show({
        title: '启动失败',
        message: '无法启动测试计划',
        color: 'red',
      });
    }
  };

  const handleRemove = async (test_plan_id: string) => {
    try {
      await removeFromQueue(test_plan_id);
      notifications.show({
        title: '移除成功',
        message: '测试计划已从队列中移除',
        color: 'green',
      });
      loadQueue();
    } catch (error) {
      notifications.show({
        title: '移除失败',
        message: '无法从队列中移除',
        color: 'red',
      });
    }
  };

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>测试执行队列</Title>
        <Button
          leftSection={<IconRefresh size={16} />}
          variant="light"
          onClick={loadQueue}
          loading={loading}
        >
          刷新
        </Button>
      </Group>

      <Paper withBorder>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>位置</Table.Th>
              <Table.Th>测试计划</Table.Th>
              <Table.Th>状态</Table.Th>
              <Table.Th>进度</Table.Th>
              <Table.Th>优先级</Table.Th>
              <Table.Th>排队时间</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {queueItems.length === 0 ? (
              <Table.Tr>
                <Table.Td colSpan={7}>
                  <Text ta="center" c="dimmed" py="xl">
                    {loading ? '加载中...' : '队列为空'}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              queueItems.map((item) => {
                const progress =
                  item.test_plan.total_test_cases > 0
                    ? Math.round(
                        (item.test_plan.completed_test_cases / item.test_plan.total_test_cases) * 100
                      )
                    : 0;

                return (
                  <Table.Tr key={item.queue_item.id}>
                    <Table.Td>
                      <Group gap="xs">
                        <Badge size="lg" variant="filled" color="blue">
                          {item.queue_item.position}
                        </Badge>
                        {/* TODO: Add reorder buttons */}
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Text fw={500}>{item.test_plan.name}</Text>
                      <Text size="xs" c="dimmed">
                        {item.test_plan.total_test_cases} 个测试用例
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={getStatusColor(item.test_plan.status)} variant="light">
                        {getStatusLabel(item.test_plan.status)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Progress
                          value={progress}
                          size="sm"
                          style={{ flex: 1, minWidth: 100 }}
                          color={item.test_plan.failed_test_cases > 0 ? 'red' : 'blue'}
                        />
                        <Text size="xs" c="dimmed">
                          {item.test_plan.completed_test_cases}/{item.test_plan.total_test_cases}
                        </Text>
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Badge size="sm" color="gray" variant="outline">
                        P{item.queue_item.priority}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Tooltip label={new Date(item.queue_item.queued_at).toLocaleString()}>
                        <Text size="sm" c="dimmed">
                          {new Date(item.queue_item.queued_at).toLocaleDateString()}
                        </Text>
                      </Tooltip>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        {item.queue_item.position === 1 && (
                          <Tooltip label="开始执行">
                            <ActionIcon
                              variant="light"
                              color="green"
                              onClick={() => handleStart(item.queue_item.test_plan_id)}
                            >
                              <IconPlayerPlay size={16} />
                            </ActionIcon>
                          </Tooltip>
                        )}
                        <Tooltip label="从队列移除">
                          <ActionIcon
                            variant="light"
                            color="red"
                            onClick={() => handleRemove(item.queue_item.test_plan_id)}
                          >
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                );
              })
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      {queueItems.length > 0 && (
        <Paper p="md" withBorder>
          <Group justify="space-between">
            <div>
              <Text size="sm" fw={600}>
                队列状态
              </Text>
              <Text size="xs" c="dimmed">
                当前有 {queueItems.length} 个测试计划在队列中
              </Text>
            </div>
            {queueItems[0] && (
              <Button
                leftSection={<IconPlayerPlay size={16} />}
                color="green"
                onClick={() => handleStart(queueItems[0].queue_item.test_plan_id)}
              >
                开始执行队列
              </Button>
            )}
          </Group>
        </Paper>
      )}
    </Stack>
  );
}
