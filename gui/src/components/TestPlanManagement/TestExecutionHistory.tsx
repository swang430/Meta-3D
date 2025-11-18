/**
 * Test Execution History Component
 *
 * Displays the history of executed test plans with filtering and search
 */
import { useState, useEffect } from 'react';
import {
  Stack,
  Paper,
  Table,
  Badge,
  Group,
  Text,
  TextInput,
  Select,
  Button,
  ActionIcon,
  Tooltip,
  LoadingOverlay,
  Pagination,
} from '@mantine/core';
import { IconSearch, IconFileText, IconRefresh, IconFilter } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import {
  listTestPlans,
  getStatusColor,
  getStatusLabel,
  type TestPlanSummary,
} from '../../api/testPlanService';

export function TestExecutionHistory() {
  const [loading, setLoading] = useState(true);
  const [testPlans, setTestPlans] = useState<TestPlanSummary[]>([]);
  const [filteredPlans, setFilteredPlans] = useState<TestPlanSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>('all');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  useEffect(() => {
    loadExecutionHistory();
  }, []);

  useEffect(() => {
    applyFilters();
  }, [testPlans, searchQuery, statusFilter]);

  const loadExecutionHistory = async () => {
    setLoading(true);
    try {
      // Load all completed, failed, and cancelled test plans
      const [completedRes, failedRes, cancelledRes] = await Promise.all([
        listTestPlans(0, 100, 'completed'),
        listTestPlans(0, 100, 'failed'),
        listTestPlans(0, 100, 'cancelled'),
      ]);

      const allPlans = [
        ...completedRes.items,
        ...failedRes.items,
        ...cancelledRes.items,
      ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

      setTestPlans(allPlans);
    } catch (error) {
      notifications.show({
        title: '加载失败',
        message: '无法加载执行历史',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let filtered = [...testPlans];

    // Apply status filter
    if (statusFilter && statusFilter !== 'all') {
      filtered = filtered.filter((plan) => plan.status === statusFilter);
    }

    // Apply search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((plan) =>
        plan.name.toLowerCase().includes(query) ||
        plan.created_by.toLowerCase().includes(query)
      );
    }

    setFilteredPlans(filtered);
    setCurrentPage(1);
  };

  const handleViewDetails = (id: string) => {
    notifications.show({
      title: '功能开发中',
      message: `查看测试计划 ${id} 的详细报告`,
      color: 'blue',
    });
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDuration = (_plan: TestPlanSummary) => {
    // This would need actual_duration_minutes from the full TestPlan object
    // For now, show a placeholder
    return '-';
  };

  // Pagination
  const totalPages = Math.ceil(filteredPlans.length / itemsPerPage);
  const paginatedPlans = filteredPlans.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  return (
    <Stack gap="md">
      {/* Filters and Search */}
      <Paper p="md" withBorder>
        <Group>
          <TextInput
            placeholder="搜索测试计划或创建者..."
            leftSection={<IconSearch size={16} />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <Select
            placeholder="状态过滤"
            leftSection={<IconFilter size={16} />}
            value={statusFilter}
            onChange={setStatusFilter}
            data={[
              { value: 'all', label: '全部状态' },
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
              { value: 'cancelled', label: '已取消' },
            ]}
            style={{ width: 180 }}
          />
          <Button
            leftSection={<IconRefresh size={16} />}
            variant="light"
            onClick={loadExecutionHistory}
            loading={loading}
          >
            刷新
          </Button>
        </Group>
      </Paper>

      {/* Execution History Table */}
      <Paper withBorder pos="relative">
        <LoadingOverlay visible={loading} />

        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>测试计划名称</Table.Th>
              <Table.Th>状态</Table.Th>
              <Table.Th>测试用例</Table.Th>
              <Table.Th>成功/失败</Table.Th>
              <Table.Th>执行时间</Table.Th>
              <Table.Th>时长</Table.Th>
              <Table.Th>创建者</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {paginatedPlans.length === 0 ? (
              <Table.Tr>
                <Table.Td colSpan={8}>
                  <Text ta="center" c="dimmed" py="xl">
                    {searchQuery || (statusFilter && statusFilter !== 'all')
                      ? '未找到符合条件的执行记录'
                      : '暂无执行历史记录'}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              paginatedPlans.map((plan) => (
                <Table.Tr key={plan.id}>
                  <Table.Td>
                    <Text size="sm" fw={500}>
                      {plan.name}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge color={getStatusColor(plan.status)} variant="light">
                      {getStatusLabel(plan.status)}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{plan.total_test_cases}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      <Badge color="green" variant="light" size="sm">
                        {plan.completed_test_cases}
                      </Badge>
                      {plan.failed_test_cases > 0 && (
                        <Badge color="red" variant="light" size="sm">
                          {plan.failed_test_cases}
                        </Badge>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{formatDate(plan.created_at)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{formatDuration(plan)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{plan.created_by}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Tooltip label="查看报告">
                      <ActionIcon
                        variant="light"
                        color="blue"
                        onClick={() => handleViewDetails(plan.id)}
                      >
                        <IconFileText size={16} />
                      </ActionIcon>
                    </Tooltip>
                  </Table.Td>
                </Table.Tr>
              ))
            )}
          </Table.Tbody>
        </Table>

        {totalPages > 1 && (
          <Group justify="center" p="md">
            <Pagination
              value={currentPage}
              onChange={setCurrentPage}
              total={totalPages}
            />
          </Group>
        )}
      </Paper>

      {/* Summary Statistics */}
      <Paper p="md" withBorder>
        <Group justify="space-between">
          <Group gap="xl">
            <div>
              <Text size="sm" c="dimmed" mb={4}>
                总执行次数
              </Text>
              <Text size="lg" fw={600}>
                {filteredPlans.length}
              </Text>
            </div>
            <div>
              <Text size="sm" c="dimmed" mb={4}>
                成功完成
              </Text>
              <Text size="lg" fw={600} c="green">
                {filteredPlans.filter((p) => p.status === 'completed').length}
              </Text>
            </div>
            <div>
              <Text size="sm" c="dimmed" mb={4}>
                失败
              </Text>
              <Text size="lg" fw={600} c="red">
                {filteredPlans.filter((p) => p.status === 'failed').length}
              </Text>
            </div>
            <div>
              <Text size="sm" c="dimmed" mb={4}>
                已取消
              </Text>
              <Text size="lg" fw={600} c="gray">
                {filteredPlans.filter((p) => p.status === 'cancelled').length}
              </Text>
            </div>
          </Group>
        </Group>
      </Paper>
    </Stack>
  );
}
