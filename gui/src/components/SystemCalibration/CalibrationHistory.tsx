/** 全局旧档案只读回放，不推导当前实验室的正式资格。 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Badge, Button, Code, Group, Loader, Paper, ScrollArea, Select, Stack, Table, Text, TextInput } from '@mantine/core';
import { listLegacyCalibrations, legacyNumber, legacyVerdict, type LegacyKind } from '../../api/systemCalibrationReadService';

export function CalibrationHistory() {
  const [kind, setKind] = useState<LegacyKind>('trp');
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const records = useQuery({
    queryKey: ['legacy-system-calibration', kind, offset],
    queryFn: () => listLegacyCalibrations(kind, offset, 20), retry: false,
  });
  const rows = !records.isError && !records.isPaused && !records.isFetching ? records.data : undefined;
  const selected = rows?.find(row => row.id === selectedId);
  const changePage = (next: number) => { setOffset(next); setSelectedId(null); };

  return <Stack gap="md" data-testid="legacy-system-history" miw={0} style={{overflow:'hidden'}}>
    <Alert color="gray">旧系统记录（全局、实验室归属未知）。仅回放原字段，来源与当前正式资格未知，不计入当前实验室校准状态。</Alert>
    <Group align="end">
      <Select label="旧记录类型" value={kind} allowDeselect={false}
        data={[{value:'trp',label:'TRP'}, {value:'tis',label:'TIS'}, {value:'repeatability',label:'重复性'}]}
        onChange={value => { if (value) { setKind(value as LegacyKind); setOffset(0); setSelectedId(null); setSearch(''); } }} />
      <TextInput label="按原 ID 检索当前页" value={search} onChange={event => setSearch(event.currentTarget.value)} style={{flex:1}} />
      <Button variant="light" onClick={() => void records.refetch()} loading={records.isFetching}>刷新</Button>
    </Group>
    <Text size="sm" c="dimmed">来源：/api/v1/calibration/{kind}；skip={offset}，limit=20。仅保留服务端本页顺序。</Text>
    {records.isError ? <Alert color="red">旧记录读取失败：{String(records.error)}</Alert>
      : records.isPaused ? <Alert color="yellow">旧记录读取已暂停；当前没有本次成功结果。</Alert>
      : records.isFetching || records.isPending ? <Loader size="sm" />
      : rows?.length === 0 ? <Alert color="gray">暂无旧记录</Alert>
      : rows && <Paper withBorder><ScrollArea><Table striped highlightOnHover style={{tableLayout:'fixed',overflowWrap:'anywhere'}}>
        <Table.Thead><Table.Tr>
          <Table.Th>原 ID</Table.Th><Table.Th>原类型</Table.Th><Table.Th>原测量值</Table.Th>
          <Table.Th>{kind === 'repeatability' ? '原标准差' : '原误差'}</Table.Th>
          <Table.Th w={150}>原判词</Table.Th><Table.Th>原测试时间</Table.Th><Table.Th>只读详情</Table.Th>
        </Table.Tr></Table.Thead>
        <Table.Tbody>{rows.filter(row => row.id.includes(search.trim())).map(row => <Table.Tr key={row.id} data-record-id={row.id}>
          <Table.Td>{row.id}</Table.Td>
          <Table.Td>{kind === 'repeatability'
            ? row.test_type === 'execution_metrics' ? '执行指标对齐（非TRP/TIS校准）' : row.test_type ?? '未知'
            : kind.toUpperCase()}</Table.Td>
          <Table.Td>{legacyNumber(kind === 'trp' ? row.measured_trp_dbm : kind === 'tis' ? row.measured_tis_dbm : row.mean_dbm, 'dBm')}</Table.Td>
          <Table.Td>{legacyNumber(kind === 'trp' ? row.trp_error_db : kind === 'tis' ? row.tis_error_db : row.std_dev_db, 'dB')}</Table.Td>
          <Table.Td><Badge color="gray">{legacyVerdict(row.validation_pass)}</Badge></Table.Td>
          <Table.Td>{row.tested_at}</Table.Td>
          <Table.Td><Button size="xs" variant="subtle" aria-label={`查看原记录 ${row.id}`} onClick={() => setSelectedId(row.id)}>查看原记录</Button></Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table></ScrollArea></Paper>}
    {rows && <Text size="sm">本页 {rows.length} 条</Text>}
    <Group>
      <Button variant="default" disabled={offset === 0 || records.isFetching} onClick={() => changePage(Math.max(0, offset - 20))}>上一页</Button>
      <Button variant="default" disabled={!rows || rows.length < 20} onClick={() => changePage(offset + 20)}>下一页</Button>
    </Group>
    {selected && <Paper withBorder p="md">
      <Stack gap="xs">
        <Text size="sm">来源：/api/v1/calibration/{kind}；原 ID：{selected.id}</Text>
        <Text size="sm" c="dimmed">仅回放当前页原字段；未补充当前实验室属性。</Text>
        <Code block data-testid="legacy-record-json" style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(selected, null, 2)}</Code>
      </Stack>
    </Paper>}
  </Stack>;
}
