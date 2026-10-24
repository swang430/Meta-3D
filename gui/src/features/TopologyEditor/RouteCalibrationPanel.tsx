import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Badge, Button, Card, Code, Group, Select, Stack, Text, TextInput, Title } from '@mantine/core'
import { useOperationalLab } from '../OperationalLab'
import { FixedRouteAcquisitionFields } from '../LabWorkspace/FixedRouteAcquisitionCard'
import { fixedRouteDisplay, fixedRouteStillActive, acquisitionStatus } from '../LabWorkspace/fixedRouteDisplay'
import { fetchRouteCalibrationPaths, fetchRouteApplicationPreview, confirmRouteApplication, fetchRouteApplicationHistory,
  startFixedRouteAcquisition, cancelFixedRouteAcquisition, fetchFixedRouteAcquisition, fetchFixedRouteAcquisitions } from '../../api/labProfileService'
import type { FixedRouteRecord, FixedRouteRequest, ConfirmRouteApplication, RouteSelection } from '../../types/api'
import type { SwitchTopology } from '../../api/switchTopologyService'
import { buildRouteAcquisitionRequest, buildRouteConfirmation, canAdoptRoute, routePreviewDisplay,
  routeMatchesSaved, routeForAdoption, routeGraphMatchesSaved, runningRouteIdentity, canReleaseRouteStart, batchChildReady, type RouteFields } from './routeCalibrationState'
import { RouteBatchPanel } from './RouteBatchPanel'

function failure(error:unknown) {
  const detail=(error as {response?:{data?:{detail?:unknown}}})?.response?.data?.detail
  return typeof detail==='string'?detail:error instanceof Error?error.message:'请求未成功，请重新读取服务器状态'
}

/** 当前选择、活动run、历史查看各有身份；后台只读轮询在离开页面后仍保留跨lab锁直到服务器终态。 */
export function RouteCalibrationPanel({labId,topologyId,mode,dirty,saving,revision,graph,onSelectRoute,onRunningRoute,onBusyChange}:{
  labId:string;topologyId:string;mode:string;dirty:boolean;saving:boolean;revision:string;
  graph:SwitchTopology;
  onSelectRoute:(route:RouteSelection|null)=>void;onBusyChange:(busy:boolean)=>void
  onRunningRoute:(route:RouteSelection)=>void
}) {
  const {beginWork,activeWork}=useOperationalLab(), cache=useQueryClient()
  const scope={labId,topologyId,mode,dirty:dirty||saving,graph}
  const [chainId,setChainId]=useState<string|null>(null),[runId,setRunId]=useState<string|null>(null)
  const [activeRunId,setActiveRunId]=useState<string|null>(null),[trackingBusy,setBusy]=useState(false)
  // Global unfinished work survives unmount; unreadable history cannot clear it.
  const busy=trackingBusy||activeWork.length>0
  const [activeSelection,setActiveSelection]=useState<RouteSelection|undefined>(undefined)
  const [batchRoute,setBatchRoute]=useState<RouteSelection|null>(null)
  const [inputError,setInputError]=useState(''),[deadline,setDeadline]=useState('')
  const [values,setValues]=useState<RouteFields>({frequency:'',power:'',antenna:'',cable:'',cableSource:'',samples:'5',fixed:false,safe:false})
  const mounted=useRef(true),tracking=useRef<string|null>(null),pendingRelease=useRef<(()=>void)|null>(null)
  const startPending=useRef(false),startFailureStatus=useRef<number|undefined>(undefined)
  const confirmAttempt=useRef<{signature:string;key:string}|null>(null)
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;onBusyChange(false)}},[onBusyChange])
  // Restore the existing canvas/outer-device guards before the remounted page paints.
  useLayoutEffect(()=>onBusyChange(busy),[busy,onBusyChange])
  const paths=useQuery({queryKey:['route-calibration-paths',labId,topologyId,mode,revision],
    queryFn:()=>fetchRouteCalibrationPaths(labId,topologyId,mode),enabled:!dirty&&!saving&&mode!=='calibration',retry:false})
  const batchPaths=useQuery({queryKey:['individual-route-calibration-paths',labId,topologyId,mode,revision],
    queryFn:()=>fetchRouteCalibrationPaths(labId,topologyId,mode,'individual'),enabled:!dirty&&!saving&&mode==='mimo_ota',retry:false})
  const history=useQuery({queryKey:['fixed-route-acquisitions',labId],queryFn:()=>fetchFixedRouteAcquisitions(labId),retry:false})
  const route=paths.data?.find(row=>row.chain_id===chainId)
  const progress=useQuery({queryKey:['fixed-route-acquisition',labId,runId],
    queryFn:()=>fetchFixedRouteAcquisition(labId,runId!),enabled:Boolean(runId),retry:false})
  const result=!progress.isError&&!progress.isPaused?progress.data:undefined
  const activeSnapshot=activeRunId?activeSelection:undefined
  const preview=useQuery({queryKey:['route-application-preview',labId,runId],queryFn:()=>fetchRouteApplicationPreview(labId,runId!),
    enabled:Boolean(result && result.status!=='running'&&batchChildReady(result)),retry:false})
  const adoptedHistory=useQuery({queryKey:['route-application-history',labId,topologyId,chainId],
    queryFn:()=>fetchRouteApplicationHistory(labId,topologyId,chainId!),enabled:Boolean(chainId),retry:false})
  useEffect(()=>{onSelectRoute(activeRunId?
    (activeSnapshot&&activeSnapshot.topology_id===topologyId&&activeSnapshot.operating_mode===mode&&routeGraphMatchesSaved(graph,activeSnapshot)?activeSnapshot:null):
    routeMatchesSaved(scope,batchRoute)?batchRoute:!busy&&routeMatchesSaved(scope,route)?route!:null)
  },[route,batchRoute,busy,activeRunId,activeSnapshot,dirty,saving,mode,labId,topologyId,graph,onSelectRoute])
  useEffect(()=>{setValues(old=>({...old,fixed:false,safe:false}));setDeadline('');confirmAttempt.current=null},[mode,route?.route_digest,runId])

  const changeBusy=(value:boolean)=>{setBusy(value);if(value)onBusyChange(true)}
  const track=(record:FixedRouteRecord)=>{
    setRunId(record.run_id);cache.setQueryData(['fixed-route-acquisition',labId,record.run_id],record)
    if(tracking.current===record.run_id)return
    const frozen=runningRouteIdentity(record)
    setActiveSelection(frozen)
    if(frozen && frozen.lab_profile_id===labId && frozen.topology_id===topologyId){setChainId(frozen.chain_id);onRunningRoute(frozen)}
    tracking.current=record.run_id;setActiveRunId(record.run_id);changeBusy(true)
    const release=pendingRelease.current??beginWork('route-acquisition','拓扑通路采集尚未确认结束；请回到射频拓扑查看或取消')
    pendingRelease.current=null
    // 不把组件卸载、网络失败或HTTP中断当停发。只有该run服务器终态才释放全局切换锁。
    void(async()=>{
      let current:FixedRouteRecord|undefined=record
      while(fixedRouteStillActive(record.run_id,current)){
        await new Promise(resolve=>setTimeout(resolve,500))
        try {current=await fetchFixedRouteAcquisition(labId,record.run_id);cache.setQueryData(['fixed-route-acquisition',labId,record.run_id],current)}
        catch(error){console.warn('采集状态未知，继续保留实验室切换锁',error);current=undefined}
      }
      release()
      if(mounted.current){tracking.current=null;setActiveRunId(null);setActiveSelection(undefined);changeBusy(false);void history.refetch()}
    })()
  }
  const recover=async()=>{
    const response=await history.refetch()
    if(response.isSuccess&&!response.isPaused&&!response.isFetching){
      const running=response.data.find(row=>row.status==='running'&&!row.batch_context&&!row.result?.states?.batch_job_id)
      if(running)track(running)
      else if(!tracking.current&&canReleaseRouteStart(startPending.current,startFailureStatus.current,response.data)){
        pendingRelease.current?.();pendingRelease.current=null;changeBusy(false)
      }
    }
  }
  useEffect(()=>{
    const running=history.data?.find(row=>row.status==='running'&&!row.batch_context&&!row.result?.states?.batch_job_id)
    if(running&&!tracking.current)track(running)
  },[history.data])
  const start=useMutation({mutationFn:(request:FixedRouteRequest)=>startFixedRouteAcquisition(labId,request),
    onMutate:()=>{startPending.current=true;startFailureStatus.current=undefined;changeBusy(true);pendingRelease.current=beginWork('route-acquisition-start','通路采集开始状态尚未确认，不能切换实验室')},
    onSuccess:record=>track(record),onSettled:(_data,error)=>{
      startPending.current=false
      if(error){startFailureStatus.current=(error as {response?:{status?:number}}).response?.status;void recover()}
    }})
  const cancel=useMutation({mutationFn:()=>cancelFixedRouteAcquisition(labId,activeRunId!),
    onSuccess:record=>{cache.setQueryData(['fixed-route-acquisition',labId,record.run_id],record)}})
  const adopt=useMutation({mutationFn:(body:ConfirmRouteApplication)=>confirmRouteApplication(labId,body),
    onSuccess:()=>{void preview.refetch();void adoptedHistory.refetch()}})
  const shown=result?fixedRouteDisplay(result):null, frozen=runningRouteIdentity(result)
  const adoptionRoute=routeForAdoption(scope,result,route)
  const allowed=canAdoptRoute(scope,adoptionRoute,preview.data,runId??undefined)&&result?.status==='completed'&&
    batchChildReady(result)&&!preview.isFetching&&!preview.isError&&!preview.isPaused&&!progress.isError&&!busy
  const display=preview.data?routePreviewDisplay(preview.data):null
  return <Card withBorder radius={0} data-testid="route-calibration-panel" style={{height:'100%',overflowY:'auto'}}><Stack gap="sm">
    <Title order={4}>通路采集与确认采用</Title>
    <Alert color="blue">单项入口保持固定接线；同图多项入口按服务器清单逐项切换／等待人工。采用整条实测损耗后只作用于适用的新执行；既有执行保持冻结。认证资格未知，不代表DUT功率。</Alert>
    {dirty&&<Alert color="yellow">拓扑草稿未保存：先保存，再选择服务器完整通路；不会采集旧图而高亮草稿。</Alert>}
    {mode==='calibration'&&<Alert color="blue">此模式用于编辑参考接线。请切回正常测试模式选择完整待测通路；历史记录身份不随模式改变。</Alert>}
    <Select label="完整校准通路" placeholder="选择已保存的CE→探头通路" searchable value={activeRunId?activeSnapshot?.chain_id??null:chainId}
      disabled={busy||dirty||saving||mode==='calibration'||paths.isFetching}
      data={(activeRunId?(activeSnapshot?[activeSnapshot]:[]):paths.data)?.map(row=>({value:row.chain_id,label:`${row.ce_port} → 探头${row.probe_id} ${row.polarization} · ${row.chain_id}${activeSnapshot?'（本次冻结）':''}`}))??[]}
      onChange={value=>{setBatchRoute(null);setChainId(value);adopt.reset();setInputError('')}}/>
    {paths.isError&&<Alert color="red">正式同时集合路径读取失败：{failure(paths.error)}；串行批候选单独读取，不放宽正式集合门。</Alert>}
    {route&&!dirty&&!saving&&mode!=='calibration'&&!routeMatchesSaved(scope,route)&&<Alert color="yellow">
      服务器候选通路与当前保存画布的节点、端口或参考接线不一致，未用新候选高亮旧图。请重新加载保存图复核；这不是要求重新校准。
      <Button variant="light" size="xs" disabled={busy} onClick={()=>window.location.reload()}>重新加载保存图</Button>
    </Alert>}
    {route&&(!activeSnapshot||activeSnapshot.route_digest===route.route_digest)&&routeMatchesSaved(scope,route)&&<Stack gap={2} data-testid="selected-calibration-path">
      <Text size="sm" fw={600}>正常通路：{route.node_ids.join(' → ')}</Text>
      <Text size="sm">端口：{route.ports.map(row=>`${row.source_pin} → ${row.target_pin}`).join(' / ')}</Text>
      <Text size="sm">参考测量段：{route.calibration_node_ids.join(' → ')||'尚未声明参考接线'}</Text>
      <Badge variant="light">原图完整通路已高亮 · {route.polarization}极化</Badge>
    </Stack>}
    <form onSubmit={event=>{event.preventDefault();try{
      if(!route)throw new Error('请先选择当前保存的完整路径')
      const body=buildRouteAcquisitionRequest(scope,route,values);setInputError('');cancel.reset();adopt.reset();start.mutate(body)
    }catch(error){setInputError(failure(error))}}}>
      <fieldset disabled={busy||saving||dirty||!routeMatchesSaved(scope,route)} style={{border:0,padding:0,margin:0,minWidth:0}}>
        <FixedRouteAcquisitionFields values={values} onChange={(key,value)=>{setValues(old=>({...old,[key]:value}));setInputError('')}}/>
        <Button mt="sm" type="submit" disabled={!routeMatchesSaved(scope,route)||!values.fixed||!values.safe||history.isPending||history.isError} loading={start.isPending}>开始自动采集</Button>
      </fieldset>
    </form>
    {busy&&<Alert color="yellow"><Text>采集状态未确认结束；图编辑、模式、设备及实验室切换已锁定。关闭页面不等于停止。</Text>
      {activeSnapshot&&!routeGraphMatchesSaved(graph,activeSnapshot)&&<Text size="sm">活动记录的冻结路径与当前保存画布不同，未拿任一端替另一端背书。请看本次记录原文核对，服务器取消仍可用。</Text>}
      {!activeRunId&&<Text size="sm">开始回执未知时，空历史不能证明未启动。请继续读取服务器状态；发现活动记录后可在此取消，必要时结合现场核验。</Text>}
      <Button color="red" mt="xs" disabled={!activeRunId} loading={cancel.isPending} onClick={()=>cancel.mutate()}>取消采集并停止本次单音</Button></Alert>}
    <Button variant="light" size="xs" onClick={()=>{void recover();if(!dirty&&!saving&&mode!=='calibration'){void paths.refetch();if(mode==='mimo_ota')void batchPaths.refetch()}}} loading={history.isFetching}>读取历史／恢复采集状态</Button>
    {inputError&&<Alert color="red">{inputError}</Alert>}
    {start.isError&&<Alert color="red">无法开始采集：{failure(start.error)}。结果和参数仍保留。</Alert>}
    {cancel.isError&&<Alert color="red">停止请求失败：{failure(cancel.error)}；仍保留采集锁，请重试。</Alert>}
    {progress.isError&&<Alert color="red">记录读取失败，不能据此认为停发：{failure(progress.error)}<Button variant="subtle" onClick={()=>void progress.refetch()}>重读本次记录</Button></Alert>}
    {shown&&result&&<Alert color={result.status==='simulated'?'yellow':result.status==='completed'?'blue':'red'} data-testid="route-acquisition-result">
      <Text fw={600}>{shown.label}</Text><Text size="sm">记录：{result.run_id}</Text>
      <Text size="sm">记录模式：{frozen?.operating_mode??result.result?.request.operating_mode??'历史未知'}；路径：{frozen?.node_ids.join(' → ')??'历史无完整路径快照'}</Text>
      <Text>F64实测：{shown.source}；接收实测：{shown.received}</Text><Text>整条净损耗：{shown.loss}</Text><Text>停发：{shown.cleanup}</Text>
      {Boolean(result.batch_context||result.result?.states?.batch_job_id)&&<Text size="sm" c={!batchChildReady(result)?'yellow':undefined}>
        所属批：{result.batch_context?.job_id??String(result.result?.states?.batch_job_id??'未知')}；本项tone：{result.status==='simulated'?'模拟，未确认真实停发':result.result?.cleanup_confirmed===true?'清理已确认':'清理未知'}；
        {batchChildReady(result)?'服务器已确认父批终止、真实lease释放与父子最终提交；仍以原采用资格为准':'父批活动／最终化或外层释放未确认，不可采用'}。
      </Text>}
      {result.result?.error&&<Text>{result.result.error}</Text>}
      {result.result?.missing_items?.map((text,index)=><Text size="sm" key={index}>{text}</Text>)}
      <details><summary>本次冻结配置、原始回复与读数</summary><Code block style={{maxHeight:300,overflow:'auto',whiteSpace:'pre-wrap'}}>{JSON.stringify(result,null,2)}</Code></details>
    </Alert>}
    {preview.isError&&<Alert color="red">采用资格读取失败：{failure(preview.error)}</Alert>}
    {display&&preview.data&&batchChildReady(result)&&<Card withBorder><Stack gap="xs">
      <Text fw={600}>服务器采用预览（认证资格未知）</Text>
      <Text>原值：{display.old} · 新值：{display.next} · 差值：{display.delta}</Text>
      <Text size="xs">旧来源与新整条参考面不同的情形由服务器判定；不在页面相减或猜值。</Text>
      {preview.data.eligibility.blockers.map((text,index)=><Text c="red" size="sm" key={index}>{text}</Text>)}
      {preview.data.eligibility.warnings.map((text,index)=><Text size="sm" key={index}>{text}</Text>)}
      {!allowed&&<Text size="sm" c="dimmed">仅当前保存路径上服务器核验为真实且适用的记录可确认；模拟、历史或不匹配记录不能采用。</Text>}
      <TextInput label="选用截止时间（本地时间，明确填写）" type="datetime-local" value={deadline} disabled={!allowed||adopt.isPending}
        onChange={e=>{setDeadline(e.currentTarget.value);adopt.reset()}}/>
      <Text size="xs">这是操作员选用期限，不是证书有效期；不默认180天。</Text>
      <Button disabled={!allowed||!deadline||Boolean(adopt.data)} loading={adopt.isPending} onClick={()=>{try{
        const signature=JSON.stringify([runId,preview.data?.expected_current_application_id,adoptionRoute?.route_digest,deadline])
        if(confirmAttempt.current?.signature!==signature)confirmAttempt.current={signature,key:crypto.randomUUID()}
        adopt.mutate(buildRouteConfirmation(scope,adoptionRoute!,preview.data!,deadline,confirmAttempt.current.key));setInputError('')
      }catch(error){setInputError(failure(error))}}}>确认采用此实测记录</Button>
      <Button variant="subtle" disabled={busy||preview.isFetching} onClick={()=>{void preview.refetch();void adoptedHistory.refetch()}}>重新读取采用预览与历史</Button>
      {adopt.isError&&<Alert color="red">确认请求未获成功回执：{failure(adopt.error)}。原结果保留，未据此标为已采用；请重新读取预览及采用历史核对服务器是否保存。</Alert>}
      {adopt.data&&<Alert color="blue">已保存操作员确认采用记录：{adopt.data.id}。适用的新执行将一次使用该值；不是认证通过，也不改变旧执行。</Alert>}
    </Stack></Card>}
    <Text size="xs">执行支持：MIMO-First ASC以waveform方式只补一次；native GCM、外部ASC、B2没有整条参考面消费者，显示不支持／未应用，严格模式在硬件前拒绝。</Text>
    <Title order={5}>采集历史</Title>
    {history.isError&&<Alert color="red">历史读取失败：{failure(history.error)}</Alert>}
    {history.data?.map(row=><Group key={row.run_id} justify="space-between" wrap="nowrap"><Text size="xs">{new Date(row.run_at).toLocaleString()} · {row.result?.request.operating_mode??'历史未知'} · {acquisitionStatus[row.status]??'未知'}
      {row.batch_context&&` · 所属批${row.batch_context.job_id??'未知'} · ${row.status==='simulated'?'模拟tone':row.result?.cleanup_confirmed===true?'本项tone已清理':'本项tone未知'} · ${batchChildReady(row)?'父批最终化已确认':'外层释放未确认，不可采用'}`}</Text>
      <Button size="xs" variant="subtle" disabled={Boolean(activeRunId)} onClick={()=>{setRunId(row.run_id);const frozen=runningRouteIdentity(row);if(frozen)setChainId(frozen.chain_id);adopt.reset();setInputError('')}}>查看记录</Button></Group>)}
    {!history.data?.length&&!history.isError&&<Text size="sm">暂无采集记录。</Text>}
    <Title order={5}>所选通路采用历史</Title>
    {adoptedHistory.isError&&<Alert color="red">采用历史读取失败：{failure(adoptedHistory.error)}</Alert>}
    {adoptedHistory.data?.map(row=><Text size="xs" key={row.id} style={{overflowWrap:'anywhere'}}>{new Date(row.confirmed_at).toLocaleString()} · {row.selection_snapshot.operating_mode} / {row.frequency_mhz} MHz · {row.net_loss_db.toFixed(2)} dB · 认证资格未知 · 截止{String(row.coverage_snapshot.adoption_valid_until??'未知')} · 采集{row.acquisition_run_id} · 采用{row.id}</Text>)}
    {!adoptedHistory.data?.length&&<Text size="sm">当前通路暂无确认采用记录。</Text>}
    {batchPaths.isError&&<Alert color="red">逐项保存路径候选读取失败：{failure(batchPaths.error)}</Alert>}
    <RouteBatchPanel scope={scope} paths={!batchPaths.isError&&!batchPaths.isPaused?batchPaths.data??[]:[]} blocked={busy} onSelectRoute={setBatchRoute} onRunningRoute={onRunningRoute}
      onInspectChild={(id,selection)=>{setRunId(id);if(selection){setChainId(selection.chain_id);setBatchRoute(selection)}adopt.reset();setInputError('')}}/>
  </Stack></Card>
}
