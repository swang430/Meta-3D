import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Badge, Button, Card, Code, Group, Stack, Table, Text, Title } from '@mantine/core'
import { compareCalibrationScope, fetchCalibrationScope } from '../../api/labProfileService'
import type { CalibrationScopeSnapshot } from '../../types/api'

/** 父层按 lab/chamber key 挂载；保留快照不跨实验室沿用。 */
export function CalibrationScopeCard({ labId, chamberId }: { labId: string; chamberId: string | null }) {
  const key = ['lab-workspace', 'calibration-scope', labId]
  const [baseline, setBaseline] = useState<CalibrationScopeSnapshot | null>(null)
  const scope = useQuery({ queryKey: key, queryFn: () => fetchCalibrationScope(labId), retry: false })
  const compare = useMutation({
    mutationFn: async () => {
      if (!baseline) throw new Error('请先保留配置快照')
      const result = await compareCalibrationScope(labId, baseline)
      if (result.current.payload.lab_profile_id !== labId || result.current.payload.chamber_id !== chamberId) {
        throw new Error('比较响应实验室或暗室不一致')
      }
      return result
    },
    // 比较响应不覆盖 GET 缓存；重新读取，只有与新读取摘要一致才显示比较结论。
    onSuccess: () => { void scope.refetch() },
  })
  const value = scope.data
  const mismatch = value && (value.payload.lab_profile_id !== labId || value.payload.chamber_id !== chamberId)
  const blocked = scope.isFetching || scope.isPaused || scope.isError || mismatch || !value
  const result = !blocked && !compare.isPending && !compare.isError && compare.data?.current.digest === value?.digest ? compare.data : null
  return <Card withBorder data-testid="calibration-scope">
    <Stack gap="xs">
      <Title order={4}>校准配置范围（PC-01A）</Title>
      <Alert color="yellow">仅盘点保存声明，不是实物确认或校准证明。序列号、真实接线与参考位置仍需现场核验；没有配置差异也不表示旧校准可复用。</Alert>
      <Group>
        <Button size="xs" disabled={compare.isPending} onClick={() => { compare.reset(); void scope.refetch() }} loading={scope.isFetching}>刷新范围</Button>
        <Button size="xs" variant="light" disabled={Boolean(blocked) || compare.isPending}
          onClick={() => { setBaseline(value!); compare.reset() }}>保留当前范围快照</Button>
        <Button size="xs" variant="light" disabled={!baseline || Boolean(blocked)} loading={compare.isPending}
          onClick={() => compare.mutate()}>与保留快照比较</Button>
      </Group>
      {baseline && <Text size="xs" style={{ overflowWrap: 'anywhere' }}>保留摘要：{baseline.digest}</Text>}
      {scope.isError ? <Alert color="red">范围读取失败：{scope.error.message}</Alert>
        : scope.isPaused ? <Alert color="yellow">范围读取暂停；旧范围不作为新结果。</Alert>
        : scope.isFetching ? <Text>范围读取中…</Text>
        : mismatch ? <Alert color="red">范围响应实验室或暗室不一致，拒绝展示。</Alert>
        : value ? <>
          <Badge color="yellow">实物身份未核验 · 无正式资格</Badge>
          <Text size="sm" style={{ overflowWrap: 'anywhere' }}>当前摘要：{value.digest}</Text>
          <Text>模式：{value.payload.operating_mode} · {value.payload.chains.length} 条解析链</Text>
          {value.warnings.map((warning, index) => <Text size="sm" c="orange" key={index}>{warning}</Text>)}
          <Table.ScrollContainer minWidth={520}>
            <Table><Table.Thead><Table.Tr><Table.Th>链身份</Table.Th><Table.Th>CE 端口</Table.Th><Table.Th>探头</Table.Th><Table.Th>极化</Table.Th><Table.Th>拓扑声明损耗 dB（非本片实测）</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{value.payload.chains.map((chain, index) => <Table.Tr key={`${chain.chain_id}-${index}`}>
                <Table.Td>{chain.chain_id}</Table.Td><Table.Td>{chain.ce_port}</Table.Td><Table.Td>{chain.probe_id}</Table.Td><Table.Td>{chain.polarization}</Table.Td><Table.Td>{chain.cable_loss_db}</Table.Td>
              </Table.Tr>)}</Table.Tbody></Table>
          </Table.ScrollContainer>
          <details><summary>查看服务器范围声明（几何、器件、保存资源与绑定、探头、拓扑）</summary>
            <Code block style={{ maxHeight: 360, overflow: 'auto' }}>{JSON.stringify(value.payload, null, 2)}</Code>
          </details>
        </> : <Text>尚未取得范围。</Text>}
      {compare.isError && <Alert color="red">比较失败：{compare.error.message}</Alert>}
      {result && <Alert color={result.requires_review ? 'yellow' : 'blue'}>
        {result.requires_review ? `配置变化，需复核：${result.changed_sections.join('、')}；受影响链：${result.affected_chain_ids.join('、') || '无已解析链'}`
          : '配置范围无差异；未证明校准有效、适用或已应用。'}
      </Alert>}
    </Stack>
  </Card>
}
