import { useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ReactFlow, Background, Controls, Handle, Position } from '@xyflow/react'
import type { NodeProps, Node } from '@xyflow/react'
import { Alert, Badge, Button, Drawer, Group, Paper, Stack, Text, Title } from '@mantine/core'
import type { SwitchTopology } from '../../api/switchTopologyService'
import { cancelFixedRouteAcquisition, fetchCalibrationScope, fetchFixedRouteAcquisitions } from '../../api/labProfileService'
import type { FixedRouteRecord } from '../../types/api'
import { CalibrationScopeCard } from '../LabWorkspace/CalibrationScopeCard'
import { F64CalibrationStateCard } from '../LabWorkspace/F64CalibrationStateCard'
import { FixedRouteAcquisitionPanel } from './FixedRouteAcquisitionPanel'
import { buildCalibrationGraph } from './calibrationGraph'
import type { CalibrationNodeData } from './calibrationGraph'
import { calibrationActivityBlocked } from './calibrationActivity'
import './topologyCalibration.css'

function CalibrationNode({ data }: NodeProps<Node<CalibrationNodeData>>) {
  return <Paper withBorder p="sm" radius="md" className={`calibration-node calibration-node-${data.role}`}>
    <Handle type="target" position={data.reverse?Position.Right:Position.Left}/><Handle type="source" position={data.reverse?Position.Left:Position.Right}/>
    <Text fw={600} size="sm">{data.title}</Text>
    {data.detail && <Text size="xs" c="dimmed">{data.detail}</Text>}
    {data.reading && <Text size="sm" fw={600} c="blue">{data.reading}</Text>}
    {data.chains?.map(chain=><Button key={chain.chain_id} size="compact-xs" variant="light" className="nodrag nopan"
      disabled={Boolean(data.busy)} aria-label={`选择校准通路 ${chain.ce_port} 探头${chain.probe_id} ${chain.polarization}`}
      onClick={()=>{if(typeof data.onChoose==='function')data.onChoose(chain.chain_id)}}>
      {chain.ce_port} · {chain.polarization} · 选择通路
    </Button>)}
  </Paper>
}
const nodeTypes={calibration:CalibrationNode}

export function TopologyCalibrationWorkspace({labId,topology,onBusy}:{
  labId:string;topology:SwitchTopology;onBusy:(busy:boolean)=>void
}) {
  const scope=useQuery({queryKey:['lab-workspace','calibration-scope',labId],queryFn:()=>fetchCalibrationScope(labId),retry:false})
  const jobs=useQuery({queryKey:['topology-calibration-jobs',labId],queryFn:()=>fetchFixedRouteAcquisitions(labId),retry:false,
    refetchInterval:query=>query.state.data?.some(r=>r.status==='running')?500:false})
  const [chainId,setChainId]=useState<string|null>(null)
  const [record,setRecord]=useState<FixedRouteRecord|undefined>()
  const [measuring,setMeasuring]=useState(false)
  const [tool,setTool]=useState<'configuration'|'f64'|null>(null)
  const pending=jobs.data?.find(r=>r.status==='running')
  const busy=calibrationActivityBlocked(measuring,Boolean(pending),jobs)
  const stop=useMutation({mutationFn:(id:string)=>cancelFixedRouteAcquisition(labId,id),
    onSuccess:()=>{void jobs.refetch()}})
  useEffect(()=>{onBusy(busy);return()=>onBusy(false)},[busy,onBusy])
  useEffect(()=>{
    if(pending?.result?.request.chain_id && scope.data?.payload.chains.some(c=>c.chain_id===pending.result!.request.chain_id)){
      setChainId(pending.result.request.chain_id)
    }
  },[pending?.run_id,scope.data])
  const choose=useCallback((id:string)=>{if(!busy){setRecord(undefined);setChainId(id)}},[busy])
  const measurementBusy=useCallback((value:boolean)=>{setMeasuring(value);if(!value)void jobs.refetch()},[jobs.refetch])
  const snapshot=scope.data
  const graph=snapshot?buildCalibrationGraph(topology,snapshot,labId,chainId,record):null
  const blocked=scope.isError||scope.isFetching||scope.isPaused||jobs.isError||jobs.isPaused||!jobs.isSuccess||Boolean(graph?.problem)
  return <Stack gap="sm" data-testid="topology-calibration" className="topology-calibration-workspace">
    <Group justify="space-between">
      <div><Title order={4}>在图上选择校准通路</Title><Text size="sm" c="dimmed">蓝色实线是保存接线；绿色虚线是参考测量段。选择和查看不切换开关。</Text></div>
      <Group gap="xs">
        <Button size="xs" variant="light" onClick={()=>{void scope.refetch();void jobs.refetch()}}>重新读取配置</Button>
        <Button size="xs" variant="subtle" disabled={busy} onClick={()=>setTool('configuration')}>配置复核</Button>
        <Button size="xs" variant="subtle" disabled={busy} onClick={()=>setTool('f64')}>F64状态</Button>
        {chainId&&<Button size="xs" disabled={busy} variant="light" onClick={()=>{setChainId(null);setRecord(undefined)}}>查看全部通路</Button>}
      </Group>
    </Group>
    {scope.isError&&<Alert color="red">测量配置读取失败：{scope.error.message}</Alert>}
    {jobs.isError&&<Alert color="red">运行记录读取失败，不能认为仪器已停止：{jobs.error.message}</Alert>}
    {jobs.isPaused&&<Alert color="red">网络离线，尚未确认仪器已停止。请恢复网络后重新读取配置。</Alert>}
    {pending&&<Alert color="orange"><Text>本实验室有正在运行的采集。即使接线图无法读取，仍可请求停止。</Text>
      <Button color="red" loading={stop.isPending} onClick={()=>stop.mutate(pending.run_id)}>停止正在运行的采集</Button>
      {stop.isError&&<Text>停止请求未成功，请重试并检查仪器：{stop.error.message}</Text>}
    </Alert>}
    {graph?.problem&&<Alert color="red">{graph.problem}</Alert>}
    {graph?.notice&&<Alert color="yellow">{graph.notice}</Alert>}
    <div className={`topology-calibration-layout${chainId?' has-selection':''}`}>
      <Paper withBorder radius="md" className="topology-calibration-canvas" data-testid="calibration-graph">
        {graph&&!graph.problem?<ReactFlow key={chainId??'overview'}
          nodes={graph.nodes.map(n=>({...n,data:{...n.data,onChoose:choose,busy}}))} edges={graph.edges}
          nodeTypes={nodeTypes} nodesDraggable={false} nodesConnectable={false} fitView
          fitViewOptions={{padding:0.15,maxZoom:1}} minZoom={0.12} attributionPosition="bottom-right">
          <Background gap={22} color="#e2e8f0"/><Controls showInteractive={false}/>
        </ReactFlow>:<Text p="md">{scope.isFetching?'正在读取保存拓扑…':'没有可显示的测量通路。请先核对实验室和保存接线。'}</Text>}
      </Paper>
      {chainId&&snapshot&&!graph?.problem?<Paper withBorder p="md" radius="md" className="topology-calibration-sidebar">
        <FixedRouteAcquisitionPanel key={chainId} labId={labId} snapshot={snapshot} chainId={chainId}
          blocked={blocked} onBusy={measurementBusy} onRecord={setRecord}/>
      </Paper>:<Paper withBorder p="md" radius="md"><Badge color="blue">先选通路</Badge>
        <Text mt="sm">点击探头旁的端口按钮，展开空口、参考天线和分析仪，再开始自动测量。</Text>
        <Text mt="sm" size="sm" c="dimmed">配置损耗与实测结果分开保存。这里不会自动覆盖线缆损耗或启用测试补偿。</Text></Paper>}
    </div>
    <Drawer opened={tool!==null} onClose={()=>setTool(null)} title={tool==='configuration'?'配置复核':'F64状态与历史'} position="right" size="lg">
      {tool==='configuration'&&<CalibrationScopeCard labId={labId} chamberId={topology.chamber_id??null}/>}
      {tool==='f64'&&<F64CalibrationStateCard labId={labId}/>}
    </Drawer>
  </Stack>
}
