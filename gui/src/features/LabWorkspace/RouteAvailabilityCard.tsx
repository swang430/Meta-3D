import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Group, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { fetchRouteCalibrationAvailability } from '../../api/labProfileService'

/** 仅展示服务器选源结果；编辑目标即撤下旧结果，不把库存齐全当资格。 */
export function RouteAvailabilityCard({labId}:{labId:string}) {
  const [frequency,setFrequency]=useState(''),[mode,setMode]=useState('mimo_ota')
  const [target,setTarget]=useState<{frequency:number;mode:string}|null>(null)
  const query=useQuery({queryKey:['route-availability',labId,target?.mode,target?.frequency],
    queryFn:()=>fetchRouteCalibrationAvailability(labId,target!.mode,target!.frequency),enabled:target!==null,retry:false})
  const valid=frequency.trim()!==''&&Number.isFinite(Number(frequency))&&Number(frequency)>0&&Boolean(mode.trim())
  const result=target&&!query.isFetching&&!query.isError&&!query.isPaused?query.data:undefined
  return <Card withBorder data-testid="route-availability"><Stack gap="xs">
    <Title order={4}>目标频点校准来源</Title>
    <Text size="sm">只读查询，不连接仪器。来源齐全不代表正式资格；执行时仍重新核对并冻结。</Text>
    <Group align="end">
      <TextInput label="目标频率（MHz）" type="number" step="any" value={frequency}
        onChange={event=>{setFrequency(event.currentTarget.value);setTarget(null)}}/>
      <TextInput label="目标模式标识" value={mode} onChange={event=>{setMode(event.currentTarget.value);setTarget(null)}}/>
      <Button disabled={!valid} loading={query.isFetching&&target!==null} onClick={()=>{
        const next={frequency:Number(frequency),mode:mode.trim()}
        if(target?.frequency===next.frequency&&target.mode===next.mode)void query.refetch()
        else setTarget(next)
      }}>查询目标来源</Button>
    </Group>
    {!target&&<Text size="sm">请填写本次目标后查询；尚未判断任何用例的覆盖情况。</Text>}
    {target&&query.isError&&<Alert color="red">来源查询失败：{query.error.message}；不显示旧结果，请重试。</Alert>}
    {target&&query.isPaused&&<Alert color="yellow">来源查询暂停；旧结果不作为本次查询结果。</Alert>}
    {target&&query.isFetching&&<Text>正在读取目标来源…</Text>}
    {result&&<>
      <Alert color={result.all_chains_have_sources?'blue':'yellow'}>
        {result.all_chains_have_sources?'目标链均有来源':'目标来源有缺口或没有可解析链'}：{result.covered_chain_count}/{result.required_chain_count} 条；正式适用资格未知。
      </Alert>
      <Text size="xs">读取时间：{result.checked_at} · {result.frequency_mhz} MHz · {result.operating_mode}</Text>
      <Table.ScrollContainer minWidth={580}><Table><Table.Thead><Table.Tr>
        <Table.Th>链／端口</Table.Th><Table.Th>探头／极化</Table.Th><Table.Th>来源</Table.Th><Table.Th>净损耗 dB</Table.Th><Table.Th>服务器原因</Table.Th>
      </Table.Tr></Table.Thead><Table.Tbody>{result.routes.map(row=><Table.Tr key={row.chain_id}>
        <Table.Td>{row.chain_id} / {row.ce_port}</Table.Td><Table.Td>{row.probe_id} / {row.polarization}</Table.Td>
        <Table.Td>{({confirmed_route:'确认采用',legacy_certificate:'既有证书',unavailable:'无可用来源'})[row.source_kind]}<Text size="xs">{row.source_id??'—'}</Text></Table.Td>
        <Table.Td>{row.value_db??'未知'}</Table.Td><Table.Td>{row.reason}</Table.Td>
      </Table.Tr>)}</Table.Tbody></Table></Table.ScrollContainer>
      {[...result.warnings,...result.limitations].map((text,index)=><Text size="sm" key={index}>{text}</Text>)}
    </>}
  </Stack></Card>
}
