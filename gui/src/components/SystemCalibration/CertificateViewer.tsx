/** 只查询旧证书字段；不生成文件、不认证签名、不推导当前有效资格。 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Badge, Button, Code, Group, Loader, Paper, ScrollArea, Stack, Table, Text } from '@mantine/core';
import { getLegacyCertificate, listLegacyCertificates, legacyNumber, legacyVerdict } from '../../api/systemCalibrationReadService';

export function CertificateViewer() {
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const certificates = useQuery({
    queryKey: ['legacy-system-certificates', offset],
    queryFn: () => listLegacyCertificates(offset, 20), retry: false,
  });
  const details = useQuery({
    queryKey: ['legacy-system-certificate', selectedId], enabled: Boolean(selectedId), retry: false,
    queryFn: () => getLegacyCertificate(selectedId!),
  });
  const rows = !certificates.isError && !certificates.isPaused && !certificates.isFetching ? certificates.data : undefined;
  const detail = rows && !details.isError && !details.isPaused && !details.isFetching ? details.data : undefined;
  const changePage = (next: number) => { setOffset(next); setSelectedId(null); };

  return <Stack gap="md" data-testid="legacy-system-certificates" miw={0} style={{overflow:'hidden'}}>
    <Alert color="gray">旧系统记录（全局、实验室归属未知）。仅回放原字段，来源与当前正式资格未知，不计入当前实验室校准状态。</Alert>
    <Text size="sm">仅原记录详情；此入口不生成、认证或下载证书。已有文件未删除</Text>
    <Group justify="space-between">
      <Text size="sm" c="dimmed">来源：/api/v1/calibration/certificate；skip={offset}，limit=20。仅保留服务端本页顺序。</Text>
      <Button variant="light" onClick={() => void certificates.refetch()} loading={certificates.isFetching}>刷新</Button>
    </Group>
    {certificates.isError ? <Alert color="red">旧证书读取失败：{String(certificates.error)}</Alert>
      : certificates.isPaused ? <Alert color="yellow">旧证书读取已暂停；当前没有本次成功结果。</Alert>
      : certificates.isFetching || certificates.isPending ? <Loader size="sm" />
      : rows?.length === 0 ? <Alert color="gray">暂无旧证书</Alert>
      : rows && <Paper withBorder><ScrollArea><Table striped style={{tableLayout:'fixed',overflowWrap:'anywhere'}}>
        <Table.Thead><Table.Tr>
          <Table.Th>原 ID</Table.Th><Table.Th>原证书编号</Table.Th><Table.Th>原校准日期</Table.Th>
          <Table.Th>原截止日期</Table.Th><Table.Th>原签发日期</Table.Th><Table.Th w={150}>原判词</Table.Th><Table.Th>只读详情</Table.Th>
        </Table.Tr></Table.Thead>
        <Table.Tbody>{rows.map(row => <Table.Tr key={row.id} data-record-id={row.id}>
          <Table.Td>{row.id}</Table.Td><Table.Td>{row.certificate_number}</Table.Td>
          <Table.Td>{row.calibration_date}</Table.Td><Table.Td>{row.valid_until}</Table.Td><Table.Td>{row.issued_at}</Table.Td>
          <Table.Td><Badge color="gray">{legacyVerdict(row.overall_pass)}</Badge></Table.Td>
          <Table.Td><Button size="xs" variant="subtle" aria-label={`查看原证书 ${row.id}`} onClick={() => setSelectedId(row.id)}>查看原证书</Button></Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table></ScrollArea></Paper>}
    {rows && <Text size="sm">本页 {rows.length} 条</Text>}
    <Group>
      <Button variant="default" disabled={offset === 0 || certificates.isFetching} onClick={() => changePage(Math.max(0, offset - 20))}>上一页</Button>
      <Button variant="default" disabled={!rows || rows.length < 20} onClick={() => changePage(offset + 20)}>下一页</Button>
    </Group>
    {selectedId && rows && <Paper p="md" withBorder><Stack gap="xs">
      <Group justify="space-between">
        <Text size="sm">来源：/api/v1/calibration/certificate/{encodeURIComponent(selectedId)}；原 ID：{selectedId}</Text>
        <Button size="xs" variant="light" onClick={() => void details.refetch()} loading={details.isFetching}>刷新详情</Button>
      </Group>
      {details.isError ? <Alert color="red">证书详情读取失败：{String(details.error)}</Alert>
        : details.isPaused ? <Alert color="yellow">证书详情读取已暂停；当前没有本次成功结果。</Alert>
        : details.isFetching || details.isPending ? <Loader size="sm" />
        : detail && <>
          <Text>原系统名称：{detail.system_name}</Text>
          <Text>原截止日期：{detail.valid_until}</Text>
          <Badge color="gray">{legacyVerdict(detail.overall_pass)}</Badge>
          <Text size="sm">TRP 原误差：{legacyNumber(detail.trp_error_db, 'dB')}；{legacyVerdict(detail.trp_pass)}</Text>
          <Text size="sm">TIS 原误差：{legacyNumber(detail.tis_error_db, 'dB')}；{legacyVerdict(detail.tis_pass)}</Text>
          <Text size="sm">重复性原标准差：{legacyNumber(detail.repeatability_std_dev_db, 'dB')}；{legacyVerdict(detail.repeatability_pass)}</Text>
          <Text size="sm">原签名字符串（未核验）：{detail.digital_signature ?? '未知'}</Text>
          <Code block data-testid="legacy-certificate-json" style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(detail, null, 2)}</Code>
        </>}
    </Stack></Paper>}
  </Stack>;
}
