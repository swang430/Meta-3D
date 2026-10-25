/**
 * 相对基线原记录查询：原状态不代表当前正式资格，不执行 quick/drift。
 */
import { useQuery } from '@tanstack/react-query';
import { Alert, Badge, Button, Group, Loader, Paper, Stack, Table, Text } from '@mantine/core';
import { useOperationalLab } from '../../features/OperationalLab';

interface BaselineStatus {
  calibration_type: string;
  frequency_mhz: number;
  status: string;
  valid_until: string | null;
  total_channels: number;
}

export function BaselineCalibrationCard() {
  const { chamberId, error: labError } = useOperationalLab();
  const history = useQuery({
    queryKey: ['legacy-calibration-baselines', chamberId],
    enabled: Boolean(chamberId) && !labError,
    retry: false,
    queryFn: async () => {
      const res = await fetch(`/api/v1/calibration/baseline/status/${chamberId}`);
      if (!res.ok) throw new Error(`基线读取失败 (${res.status})`);
      const data = await res.json();
      if (data.chamber_id !== chamberId || !Array.isArray(data.baselines))
        throw new Error('基线响应与当前暗室不一致');
      return data.baselines as BaselineStatus[];
    },
  });
  const rows = !labError && !history.isError && !history.isPaused && !history.isFetching
    ? history.data : undefined;

  return (
    <Paper p="md" withBorder data-testid="legacy-calibration-baselines">
      <Stack gap="sm">
        <Group justify="space-between">
          <Text fw={600}>相对基线原记录</Text>
          <Button size="xs" variant="light" onClick={() => void history.refetch()}
            disabled={!chamberId || Boolean(labError)} loading={history.isFetching}>刷新</Button>
        </Group>
        <Text size="sm" c="dimmed">来源与当前正式资格未知；仅保留原记录查询，不执行旧模拟 quick/drift。</Text>
        {labError ? <Alert color="red">当前实验室读取失败：{labError}</Alert>
          : !chamberId ? <Alert color="yellow">当前 LabProfile 未绑定暗室</Alert>
          : history.isError ? <Alert color="red">{String(history.error)}</Alert>
          : history.isPaused ? <Alert color="yellow">基线读取已暂停；当前没有本次成功结果。</Alert>
          : history.isFetching ? <Loader size="sm" />
          : rows?.length === 0 ? <Alert color="gray">暂无原基线记录</Alert>
          : rows && <Table striped>
            <Table.Thead><Table.Tr>
              <Table.Th>原类型</Table.Th><Table.Th>原频率</Table.Th><Table.Th>原通道数</Table.Th>
              <Table.Th>原截止日期</Table.Th><Table.Th>原状态</Table.Th>
            </Table.Tr></Table.Thead>
            <Table.Tbody>{rows.map((row, index) => <Table.Tr key={index}>
              <Table.Td>{row.calibration_type}</Table.Td>
              <Table.Td>{row.frequency_mhz} MHz</Table.Td>
              <Table.Td>{row.total_channels}</Table.Td>
              <Table.Td>{row.valid_until ?? '未知'}</Table.Td>
              <Table.Td><Badge color="gray">{row.status}</Badge></Table.Td>
            </Table.Tr>)}</Table.Tbody>
          </Table>}
      </Stack>
    </Paper>
  );
}
