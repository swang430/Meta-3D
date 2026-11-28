import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Group, Paper, Select, Stack, Text, TextInput } from '@mantine/core'
import { isAxiosError } from 'axios'
import client from '../../api/client'

const root = '/channel-assets/mpdb-projects'
interface Project {
  source_id: string
  project_id: string
  mode: 'ota' | 'conducted'
  tx_ports: number[]
  rx_ports: number[]
  source_frames: number
}
interface Scene extends Project {
  version: string
  source_sha256: string
  available: boolean
  name: string
  carrier_hz: number
  time_source: string | null
}
function clockLabel(source: string | null) {
  if (!source) return '源帧时间未核验'
  if (source === 'operator_constant_speed') return '按距离和恒速推算时间'
  if (source === 'operator_segment_durations') return '采用逐段指定的时长'
  return '时间来源：' + source
}
function projectLabel(p: Project) {
  return (p.mode === 'ota' ? '空口' : '传导') + ' · ' + p.tx_ports.length + ' 发 ' + p.rx_ports.length + ' 收 · ' + p.source_frames + ' 个源帧'
}
interface Conditions {
  reasons: string[]
  registrations: { name: string; scenario_id: string; asset_kind: string; ready: boolean; reasons: string[] }[]
}
function ProjectPreparation({scene}: {scene: Scene}) {
  const [expanded, expand] = useState(false)
  const [lab, selectLab] = useState<string | null>(null)
  const backend = scene.mode === 'ota' ? 'ota' : 'conducted'
  const options = useQuery({queryKey:['project-labs', backend], enabled:expanded,
    queryFn:async () => (await client.get<{labs:{id:string;name:string}[]}>('/road-test/'+backend+'/options')).data})
  const check = useQuery({queryKey:['project-conditions',scene.source_sha256,scene.version,lab],enabled:expanded,
    queryFn:async () => (await client.get<Conditions>('/road-test/project-capabilities/'+scene.source_sha256+'/'+scene.version,
      {params:lab?{lab_id:lab}:{}})).data})
  return <Stack gap="xs">
    <Button variant="light" onClick={()=>expand(!expanded)}>{expanded?'收起准备条件':'准备测试'}</Button>
    {expanded && <>
      <Text>{scene.mode==='ota'?'辐射测试 · 当前仅支持模拟硬件':'传导测试 · 核对实验室登记后确定播放方式'}</Text>
      <Select label="实验室" clearable value={lab} onChange={selectLab}
        data={(options.data?.labs ?? []).map(x=>({value:x.id,label:x.name}))}/>
      {(options.error || check.error) && <Alert color="red">准备条件读取失败，请重新核对。</Alert>}
      {check.isFetching && <Text>正在核对准备条件</Text>}
      {check.data?.reasons.map(r=><Text key={r}>{r}</Text>)}
      {check.data?.registrations.map((r,i)=><Stack key={i} gap={2}><Text>{r.name} · {r.asset_kind} · {r.ready?'准备检查已通过':'尚有缺项'}</Text>
        {r.reasons.map(reason=><Text key={reason}>{reason}</Text>)}</Stack>)}
      <Text size="sm">数字孪生使用独立的软件仿真配置。</Text>
    </>}
  </Stack>
}
export function ProjectSceneLibrary() {
  const cache = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [id, select] = useState<string | null>(null)
  const scenes = useQuery({queryKey:['mpdb-road-scenes'], queryFn:async () => (await client.get<Scene[]>(root+'/scenes')).data})
  const candidates = useQuery({queryKey:['mpdb-road-candidates'], enabled:adding, queryFn:async () => (await client.get<Project[]>(root+'/scene-candidates')).data})
  const chosen = candidates.data?.find(p=>p.project_id===id)
  const save = useMutation({mutationFn:async () => {
    if (!chosen) throw Error('请选择工程')
    await client.post(root+'/'+chosen.source_id+'/'+chosen.project_id+'/scene',{name:name.trim()})
  }, onSuccess:async () => {
    await cache.invalidateQueries({queryKey:['mpdb-road-scenes']})
    setAdding(false); select(null); setName('')
  }})
  const error = save.error || scenes.error || candidates.error
  const grouped = new Map<string, Scene[]>()
  for (const scene of scenes.data ?? []) grouped.set(scene.source_sha256,[...(grouped.get(scene.source_sha256) ?? []),scene])
  return <Stack>
    <Group><Button onClick={()=>setAdding(!adding)}>{adding?'收起工程选择':'从信道工作台选工程'}</Button></Group>
    {adding && <Paper withBorder p="md"><Stack>
      <Select label="已生成的工程" value={id} onChange={select} searchable
        nothingFoundMessage="请先在信道工作台生成工程"
        data={(candidates.data ?? []).map(p=>({value:p.project_id,label:projectLabel(p)+' · '+p.project_id}))}/>
      <TextInput label="场景版本名称" maxLength={160} value={name} onChange={e=>setName(e.currentTarget.value)}/>
      <Button disabled={!chosen || !name.trim()} loading={save.isPending} onClick={()=>save.mutate()}>保存到道路场景库</Button>
    </Stack></Paper>}
    {error && <Alert color="red">{isAxiosError(error) && typeof error.response?.data?.detail==='string'?error.response.data.detail:error.message}</Alert>}
    {[...grouped].map(([source,versions])=><Paper key={source} withBorder p="md"><Stack gap="xs">
      <Text fw={600}>下行道路场景 · 来源 {source.slice(0,12)}</Text>
      {versions.map(v=><details key={v.version}><summary>{v.name} · {projectLabel(v)}</summary>
        <Text>载频 {v.carrier_hz/1e6} MHz · {clockLabel(v.time_source)}</Text>
        <Text>发射端口 {v.tx_ports.join('、')} · 接收端口 {v.rx_ports.join('、')}</Text>
        <Text>工程版本 {v.version} · {v.available?'已保存工程包':'工程文件缺失'}</Text>
        <ProjectPreparation scene={v}/>
      </details>)}
    </Stack></Paper>)}
  </Stack>
}
