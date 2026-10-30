import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Badge, Button, Card, Checkbox, Code, Group, MultiSelect, Stack, Text, Textarea, TextInput, Title } from '@mantine/core'
import type { BatchJobRecord, BatchPlan, BatchPlanRequest, FixedRouteRecord, RouteSelection } from '../../types/api'
import { previewRouteCalibrationBatch, startRouteCalibrationBatch, fetchRouteCalibrationBatches, fetchRouteCalibrationBatch,
  continueRouteCalibrationBatch, cancelRouteCalibrationBatch, fetchFixedRouteAcquisition } from '../../api/labProfileService'
import { useOperationalLab } from '../OperationalLab'
import {parseMockCalibrationCsv} from './mockCalibrationCsv'
import {MockCalibrationResult} from './MockCalibrationResult'
import {withSimulationMarker} from '../LabWorkspace/fixedRouteDisplay'
import { batchCanRelease, batchItemRoute, batchPureSimulationEnded, batchCounts, batchStartAttempt, batchStartRequest, batchToneState, batchRejectionCanRelease, findUnsettledBatch, buildBatchContinue,
  buildBatchRequest, routeMatchesSaved, routeGraphMatchesSaved, type BatchStartAttempt, type BatchReferenceFields, type RouteScope } from './routeCalibrationState'

// 未知启动身份与全局工作锁一起跨卸载保存；只读空历史不能删除它。
type Session={attempt:BatchStartAttempt|null;jobId?:string;release:()=>void;polling?:boolean}
const sessions=new Map<string,Session>()
const statusLabels:Record<string,string>={running:'运行中',waiting_manual:'等待人工',paused_failure:'失败暂停',completed:'批处理结束（逐项核对）',
  failed:'批失败（保留其余结果）',cancelled:'已请求结束/取消',cleanup_unconfirmed:'清理未确认',interrupted:'中断，需核验',incomplete:'未完成',
  measuring:'测量中',pending:'待执行',simulated:'模拟，不可采用'}
const message=(error:unknown)=>{
  const detail=(error as {response?:{data?:{detail?:unknown}}})?.response?.data?.detail
  return typeof detail==='string'?detail:error instanceof Error?error.message:'请求失败，服务器状态未知'
}

export function RouteBatchPanel({scope,paths,blocked,onSelectRoute,onInspectChild,onRunningRoute}:{scope:RouteScope;paths:RouteSelection[];blocked:boolean;
  onSelectRoute:(route:RouteSelection|null)=>void;onInspectChild:(runId:string,route:RouteSelection|undefined)=>void;onRunningRoute:(route:RouteSelection)=>void}) {
  const {beginWork}=useOperationalLab(),cache=useQueryClient(),key=`${scope.labId}:${scope.topologyId}`
  const [activeId,setActiveId]=useState<string|null>(sessions.get(key)?.jobId??null),[viewId,setViewId]=useState<string|null>(null)
  const [ids,setIds]=useState<string[]>([]),[frequencies,setFrequencies]=useState(''),[power,setPower]=useState(''),[samples,setSamples]=useState('5')
  const [fixed,setFixed]=useState(false),[safe,setSafe]=useState(false),[references,setReferences]=useState<BatchReferenceFields[]>([])
  const [plan,setPlan]=useState<BatchPlan|null>(null),[request,setRequest]=useState<BatchPlanRequest|null>(null)
  const [mockEnabled,setMockEnabled]=useState(false),[csv,setCsv]=useState('')
  const previewRequest=useRef<BatchPlanRequest|null>(null)
  const inputVersion=useRef(0)
  const [operator,setOperator]=useState(''),[note,setNote]=useState(''),[error,setError]=useState('')
  const [manual,setManual]=useState(false),[position,setPosition]=useState(''),[transition,setTransition]=useState<{item:string;id:string}|null>(null)
  const [unknown,setUnknown]=useState(Boolean(sessions.get(key)?.attempt&&!sessions.get(key)?.jobId))
  const mounted=useRef(true)
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
  const history=useQuery({queryKey:['route-batches',scope.labId],queryFn:()=>fetchRouteCalibrationBatches(scope.labId),retry:false})
  const active=useQuery({queryKey:['route-batch',scope.labId,activeId],queryFn:()=>fetchRouteCalibrationBatch(scope.labId,activeId!),enabled:Boolean(activeId),retry:false})
  const viewed=useQuery({queryKey:['route-batch',scope.labId,viewId],queryFn:()=>fetchRouteCalibrationBatch(scope.labId,viewId!),enabled:Boolean(viewId),retry:false})
  const viewedChildren=useQuery({queryKey:['route-batch-view-children',scope.labId,viewId,JSON.stringify(viewed.data?.items)],
    queryFn:()=>Promise.all((viewed.data?.items??[]).flatMap(i=>i.run_id?[fetchFixedRouteAcquisition(scope.labId,i.run_id)]:[])),enabled:Boolean(viewed.data&&viewId),retry:false})
  const current=active.isError||active.isPaused?undefined:active.data
  const childIds=current?.items.flatMap(item=>item.run_id?[item.run_id]:[])??[]
  const children=useQuery({queryKey:['route-batch-children',scope.labId,current?.job_id,JSON.stringify(current?.items)],
    queryFn:()=>Promise.all(childIds.map(id=>fetchFixedRouteAcquisition(scope.labId,id))),enabled:Boolean(current),retry:false})
  const childRecords=!children.isError&&!children.isPaused?children.data??[]:[]
  useEffect(()=>{
    if(children.data&&!children.isError&&!children.isPaused){
      for(const record of children.data)cache.setQueryData(['fixed-route-acquisition',scope.labId,record.run_id],record)
      void cache.invalidateQueries({queryKey:['fixed-route-acquisitions',scope.labId]})
    }
  },[children.data,children.isError,children.isPaused,cache,scope.labId])
  const frozen=useMemo(()=>batchItemRoute(current?.plan?.items[current.current_index??-1]),[current?.plan,current?.current_index])
  useEffect(()=>{
    if(frozen&&routeMatchesSaved(scope,frozen))onSelectRoute(frozen)
    else if(frozen&&frozen.lab_profile_id===scope.labId&&frozen.topology_id===scope.topologyId&&routeGraphMatchesSaved(scope.graph,frozen))onRunningRoute(frozen)
    else if(activeId)onSelectRoute(null)
  },[frozen,activeId,scope.dirty,scope.graph,scope.mode,onSelectRoute,onRunningRoute])
  useEffect(()=>{
    const item=current?.items[current.current_index??-1]
    setManual(false);setPosition('');setTransition(item&&current?.transition_id?{item:item.item_id,id:current.transition_id}:null)
  },[current?.transition_id,current?.job_id])
  useEffect(()=>{
    inputVersion.current++;previewRequest.current=null;setPlan(null);setRequest(null);setOperator('');setNote('')
  },[scope.graph,scope.mode,scope.dirty])
  useEffect(()=>{setMockEnabled(false);setCsv('');setReferences([]);setIds([]);setViewId(null)},[scope.labId,scope.topologyId,scope.mode])
  useEffect(()=>{
    if(current&&batchCanRelease(current,childRecords)){setViewId(current.job_id);setActiveId(null);onSelectRoute(null)}
  },[current,children.data,onSelectRoute])

  const track=(row:BatchJobRecord)=>{
    cache.setQueryData(['route-batch',scope.labId,row.job_id],row)
    setActiveId(row.job_id);setUnknown(false)
    let session=sessions.get(key)
    if(!session){session={attempt:null,release:beginWork('route-batch','批量校准尚未确认停发、释放及最终提交')};sessions.set(key,session)}
    session.jobId=row.job_id
    if(session.polling)return
    session.polling=true
    const owner=session
    void(async()=>{
      let latest:BatchJobRecord|undefined=row
      let settled:FixedRouteRecord[]=[]
      while(!batchCanRelease(latest,settled)){
        await new Promise(resolve=>setTimeout(resolve,700))
        try{
          latest=await fetchRouteCalibrationBatch(scope.labId,row.job_id);cache.setQueryData(['route-batch',scope.labId,row.job_id],latest)
          if(latest.finalization_committed&&!batchCanRelease(latest)){
            settled=await Promise.all(latest.items.flatMap(i=>i.run_id?[fetchFixedRouteAcquisition(scope.labId,i.run_id)]:[]))
            for(const record of settled)cache.setQueryData(['fixed-route-acquisition',scope.labId,record.run_id],record)
          }
        }
        catch(cause){latest=undefined;console.warn('批量校准状态未知，保留全局工作锁',cause)}
      }
      owner.release();if(sessions.get(key)===owner)sessions.delete(key)
      await cache.invalidateQueries({queryKey:['route-batches',scope.labId]})
      await cache.invalidateQueries({queryKey:['fixed-route-acquisitions',scope.labId]})
      await cache.invalidateQueries({queryKey:['fixed-route-acquisition',scope.labId]})
      if(mounted.current){setViewId(row.job_id);setActiveId(null);onSelectRoute(null)}
    })()
  }
  useEffect(()=>{
    const attempt=sessions.get(key)?.attempt
    const knownChildren=history.data?.flatMap(row=>row.items.flatMap(item=>{
      const record=item.run_id?cache.getQueryData<FixedRouteRecord>(['fixed-route-acquisition',scope.labId,item.run_id]):undefined
      return record?[record]:[]
    }))??[]
    // 未知开始已有独立锁，不用另一份历史替换它的job/幂等身份。
    const running=findUnsettledBatch(attempt?history.data?.filter(row=>row.idempotency_key===attempt.key):history.data,knownChildren)
    if(running&&!activeId)track(running)
    const session=sessions.get(key)
    if(session?.jobId&&!session.polling){
      const row=history.data?.find(value=>value.job_id===session.jobId)
      if(row)track(row)
    }
  },[history.data])
  const clearPreview=()=>{inputVersion.current++;previewRequest.current=null;setPlan(null);setRequest(null);setOperator('');setNote('');setError('')}
  const preview=useMutation({mutationFn:(body:BatchPlanRequest)=>previewRouteCalibrationBatch(scope.labId,body),
    onMutate:body=>{previewRequest.current=body},
    onSuccess:(value,body)=>{if(previewRequest.current===body&&value.lab_profile_id===scope.labId&&value.topology_id===scope.topologyId){setPlan(value);setRequest(body);setError('')}},onError:cause=>setError(message(cause))})
  const start=useMutation({mutationFn:(attempt:BatchStartAttempt)=>startRouteCalibrationBatch(scope.labId,attempt.request,attempt.key),
    onSuccess:track,onError:async(cause,attempt)=>{
      setUnknown(true);setError(`开始回执未确认：${message(cause)}。保留同一请求和幂等键；不要另起测量。`)
      const response=await history.refetch(),status=(cause as {response?:{status?:number}})?.response?.status
      if(response.isSuccess&&!response.isPaused&&batchRejectionCanRelease(status,response.data,attempt.key)){
        sessions.get(key)?.release();sessions.delete(key)
        if(mounted.current){setUnknown(false);setPlan(null);setRequest(null);setError(`服务器明确拒绝该请求，且已核对无本次／活动批：${message(cause)}。修正输入后重新预览。`)}
      }
    }})
  const resume=useMutation({mutationFn:(body:ReturnType<typeof buildBatchContinue>)=>continueRouteCalibrationBatch(scope.labId,activeId!,body),
    onSuccess:row=>{cache.setQueryData(['route-batch',scope.labId,row.job_id],row);setManual(false)},onError:cause=>setError(message(cause))})
  const cancel=useMutation({mutationFn:()=>cancelRouteCalibrationBatch(scope.labId,activeId!),
    onSuccess:row=>cache.setQueryData(['route-batch',scope.labId,row.job_id],row),onError:cause=>setError(`取消回执未知：${message(cause)}；未认为已停发或释放。`)})
  const begin=()=>{try{
    if(!request||!plan)throw new Error('请先预览完整清单')
    const body=batchStartRequest(scope,request,plan),old=sessions.get(key)
    if(blocked&&!old)throw new Error('其他工作尚未结束')
    const attempt=batchStartAttempt(old?.attempt??null,body,crypto.randomUUID())
    if(!old)sessions.set(key,{attempt,release:beginWork('route-batch','批量开始回执未确认，禁止切换实验室')})
    else old.attempt=attempt
    setUnknown(true);start.mutate(attempt)
  }catch(cause){setError(message(cause))}}
  const frequencyList=frequencies.split(/[,，\s]+/).filter(Boolean).map(Number)
  const formBlocked=blocked||unknown||Boolean(activeId)||scope.dirty||scope.mode!=='mimo_ota'||history.isPending||history.isError
  const tone=current?batchToneState(current,childRecords):'unknown'
  const waiting=Boolean(current&&['waiting_manual','paused_failure'].includes(current.status))
  const renderJob=(row:BatchJobRecord,readonly:boolean)=>{
    const count=batchCounts(row)
    const savedChildren=row.items.flatMap(item=>{
      const record=item.run_id?cache.getQueryData<FixedRouteRecord>(['fixed-route-acquisition',scope.labId,item.run_id]):undefined
      return record?[record]:[]
    })
    const simulationEnded=batchPureSimulationEnded(row,savedChildren)
    return <Card withBorder data-testid={readonly?'batch-history-detail':'batch-active-detail'}><Stack gap="xs">
      <Text fw={600}>{readonly?'只读批历史':'活动批'}：{row.job_id}</Text>
      <Badge color={row.items.some(i=>i.status==='simulated')?'yellow':'blue'}>{statusLabels[row.status]??'未知'}</Badge>
      <Text>共{count.total}项 · 实测完成{count.completed} · 模拟{count.simulated} · 失败{count.failed}；单项完成不等于整套成功。</Text>
      <Text>外层控制释放：{row.f64_control_released===true?'服务器确认': '未确认'}；父子最终提交：{row.finalization_committed===true&&row.finalization_id?'服务器确认':'未确认'}</Text>
      {simulationEnded&&<Alert color="yellow">纯模拟软件任务已结束；未取得真实控制，未证明实物停发或真实控制释放。模拟结果不可采用。</Alert>}
      {row.error&&<Alert color="red">{row.error}</Alert>}
      {row.items.map((item,index)=><Card key={item.item_id} withBorder padding="xs"><Stack gap={3}>
        <Text size="sm">{index+1}. {item.request.chain_id} · {item.request.frequency_mhz} MHz · {item.request.reference_antenna}</Text>
        <Text size="sm" c={item.request.mock_input||item.status==='simulated'?'yellow':undefined}>{withSimulationMarker(statusLabels[item.status]??item.status,Boolean(item.request.mock_input)||item.status==='simulated')}{index===row.current_index?'（当前项）':''}</Text>
        {item.error&&<Text size="xs" c="red">{item.error}</Text>}
        <Text size="xs">所属批{row.job_id}；{row.f64_control_released===true&&row.finalization_committed&&row.finalization_id?'父批外层释放及最终提交已确认，仍需服务器逐项核验采用资格':'外层释放／最终提交未确认，不可采用'}</Text>
        {item.status==='simulated'&&<Text size="xs" c="yellow">模拟项只能结束软件流程，不证明实物停发，不能正式采用。</Text>}
        {item.run_id&&<Button size="xs" variant="light" onClick={()=>onInspectChild(item.run_id!,activeId?undefined:batchItemRoute(row.plan?.items.find(i=>i.item_id===item.item_id)))}>查看本项读数及原采用入口</Button>}
      </Stack></Card>)}
      <details><summary>冻结清单、接线声明与逐开关回执</summary><Code block style={{maxHeight:240,overflow:'auto',whiteSpace:'pre-wrap'}}>{JSON.stringify(row,null,2)}</Code></details>
    </Stack></Card>
  }
  return <Stack gap="sm" data-testid="route-batch-panel">
    <Title order={4}>同图多项校准工作台</Title>
    <Alert color="blue">使用本图保存路径，先完整预览再明确开始。自动切换仅限服务器核验支持的SP6T目标槽；SPDT／未知拒绝。固定直连零开关I/O、无需开关接线声明；换线或移动参考天线等待人工。声明不是RF认证。</Alert>
    <fieldset disabled={formBlocked||preview.isPending} style={{border:0,padding:0,minWidth:0}}><Stack gap="xs">
      <MultiSelect label="批量保存路径" value={ids} data={paths.map(p=>({value:p.chain_id,label:`${p.ce_port} → 探头${p.probe_id}${p.polarization} · ${p.chain_id}`}))}
        onChange={value=>{clearPreview();setIds(value)}}/>
      <TextInput label="批量频点（MHz，逗号分隔）" value={frequencies} onChange={e=>{clearPreview();setFrequencies(e.currentTarget.value)}}/>
      <TextInput label="批量请求功率（dBm，不作实测值）" value={power} onChange={e=>{clearPreview();setPower(e.currentTarget.value)}}/>
      <TextInput label="每项采样数（2–10）" value={samples} onChange={e=>{clearPreview();setSamples(e.currentTarget.value)}}/>
      <Checkbox label="批量模拟演练样本（CSV）" checked={mockEnabled} onChange={e=>{clearPreview();setMockEnabled(e.currentTarget.checked);setCsv('')}}/>
      {ids.flatMap(chainId=>frequencyList.filter(f=>Number.isFinite(f)&&f>0).map(frequency=>{
        const ref=references.find(r=>r.chainId===chainId&&r.frequency===frequency)??{chainId,frequency,antenna:'',cable:'',cableSource:''}
        const change=(field:'antenna'|'cable'|'cableSource',value:string)=>{clearPreview();setReferences(old=>[...old.filter(r=>r.chainId!==chainId||r.frequency!==frequency),{...ref,[field]:value}])}
        return <Card withBorder key={`${chainId}:${frequency}`} padding="xs"><Stack gap="xs"><Text size="sm">{chainId} · {frequency} MHz</Text>
          <TextInput label={`参考天线／位置 ${chainId} @${frequency}`} value={ref.antenna} onChange={e=>change('antenna',e.currentTarget.value)}/>
          <TextInput label={`接收线损（dB） ${chainId} @${frequency}`} value={ref.cable} readOnly={mockEnabled} onChange={e=>change('cable',e.currentTarget.value)}/>
          <TextInput label={`接收线依据 ${chainId} @${frequency}`} value={ref.cableSource} readOnly={mockEnabled} onChange={e=>change('cableSource',e.currentTarget.value)}/>
          {mockEnabled&&<Text size="xs" c="dimmed">接收线损与依据由CSV提供，为只读；修改CSV后重新预览。</Text>}
        </Stack></Card>
      }))}
      {mockEnabled&&<Stack gap="xs"><Alert color="yellow">仅导入所选路径×频点，样本编号须完整1..N；参考天线／位置须先明确填写。CSV线损与来源为空时只留样本，不计算损耗。expected仅显示差值，非PASS。</Alert>
        <Text size="xs">列：chain_id,frequency_mhz,sample_index,source_before_dbm,received_dbm,source_after_dbm,receive_cable_loss_db,receive_cable_source,expected_loss_db</Text>
        <TextInput label="选择模拟样本 CSV 文件" type="file" accept=".csv,text/csv" onChange={e=>{const file=e.currentTarget.files?.[0];clearPreview();setCsv('');const version=inputVersion.current;if(file)void file.text().then(text=>{if(inputVersion.current===version&&mounted.current)setCsv(text)}).catch(cause=>{if(inputVersion.current===version&&mounted.current)setError(message(cause))})}}/>
        <Textarea label="模拟样本 CSV 内容" minRows={5} value={csv} onChange={e=>{clearPreview();setCsv(e.currentTarget.value)}}/>
      </Stack>}
      <Checkbox label="已核对清单的固定接线条件" checked={fixed} onChange={e=>{clearPreview();setFixed(e.currentTarget.checked)}}/>
      <Checkbox label="已确认请求功率及现场安全条件" checked={safe} onChange={e=>{clearPreview();setSafe(e.currentTarget.checked)}}/>
      <Button loading={preview.isPending} onClick={()=>{clearPreview();try{
        let refs=references,matrix:BatchPlanRequest['mock_inputs']|undefined
        if(mockEnabled){
          const antennas:Record<string,string>={}
          for(const id of ids){const values=frequencyList.map(f=>references.find(r=>r.chainId===id&&r.frequency===f)?.antenna.trim()??'');if(!values[0]||values.some(v=>v!==values[0]))throw new Error(`${id}：CSV导入须先填写一致的已核对参考天线／位置`);antennas[id]=values[0]}
          const imported=parseMockCalibrationCsv(csv,{chainIds:ids,frequenciesMhz:frequencyList,sampleCount:Number(samples),referenceAntennas:antennas})
          matrix=imported.mockInputs;refs=imported.references.map(r=>({chainId:r.chain_id,frequency:r.frequency_mhz,antenna:r.reference_antenna,cable:r.receive_cable_loss_db==null?'':String(r.receive_cable_loss_db),cableSource:r.receive_cable_source??''}))
        }
        const body=buildBatchRequest(scope,paths,ids,frequencyList,refs,{power,samples,fixed,safe},matrix??undefined)
        if(mockEnabled)setReferences(refs)
        preview.mutate(body)
      }catch(cause){setError(message(cause))}}}>预览完整批清单</Button>
    </Stack></fieldset>
    {scope.dirty&&<Alert color="yellow">未保存草稿，批预览与开始均禁用。</Alert>}
    {plan&&request&&<Card withBorder data-testid="batch-plan"><Stack gap="xs"><Text fw={600}>服务器完整清单：{plan.items.length}项</Text>
      {plan.items.map((item,index)=>{const selected=batchItemRoute(item);return <Card key={item.item_id} padding="xs"><Text size="sm">{index+1}. {item.request.chain_id} · {item.request.frequency_mhz} MHz · {item.request.reference_antenna}</Text>
        {item.request.mock_input&&<Text size="sm" c="yellow">模拟演练（非实测）· {item.request.mock_input.samples.length}样本 · {item.request.receive_cable_loss_db==null||!item.request.receive_cable_source?'只留样本，不计算损耗':'只计算演练损耗，formal=false'}</Text>}
        <Text size="xs">正常段{item.route_selection.node_ids.join(' → ')}；参考段{item.route_selection.calibration_node_ids.join(' → ')}；{item.transition_reasons.join('；')}</Text>
        <Button size="xs" variant="subtle" disabled={Boolean(activeId)||!routeMatchesSaved(scope,selected)} onClick={()=>onSelectRoute(selected??null)}>原图高亮此项正常及参考段</Button></Card>})}
      {plan.switch_scope_digest&&<Stack gap="xs"><Text size="xs" style={{overflowWrap:'anywhere'}}>开关范围摘要：{plan.switch_scope_digest}</Text>
        <Code block style={{maxHeight:220,overflow:'auto',whiteSpace:'pre-wrap'}}>{JSON.stringify(plan.items.flatMap(i=>i.switch_steps),null,2)}</Code>
        <TextInput label="接线声明操作员（自述，非认证身份）" value={operator} disabled={formBlocked} onChange={e=>{setOperator(e.currentTarget.value);setRequest(old=>old?{...old,switch_wiring_confirmation:null}:null)}}/>
        <TextInput label="接线核对说明" value={note} disabled={formBlocked} onChange={e=>{setNote(e.currentTarget.value);setRequest(old=>old?{...old,switch_wiring_confirmation:null}:null)}}/>
        <Button disabled={formBlocked||!operator.trim()||!note.trim()} loading={preview.isPending} onClick={()=>{
          preview.mutate({...request,preview_digest:null,switch_wiring_confirmation:{operator:operator.trim(),note:note.trim(),confirmed_at:new Date().toISOString(),switch_scope_digest:plan.switch_scope_digest!}})
        }}>确认本范围接线声明并重新预览</Button>
        <Text size="xs">声明带时区时间并进入新摘要。路径、频点或参考输入改变后须重新核对。</Text>
      </Stack>}
      <Text size="xs" style={{overflowWrap:'anywhere'}}>预览摘要：{plan.preview_digest}</Text>
      <Button disabled={formBlocked||preview.isPending||Boolean(plan.switch_scope_digest&&(!plan.switch_wiring_confirmation||!request.switch_wiring_confirmation))} loading={start.isPending} onClick={begin}>明确开始此批校准</Button>
    </Stack></Card>}
    {unknown&&!activeId&&<Alert color="yellow"><Text>启动回执未知，空历史不代表未启动。保持请求及UUID不变；锁未释放。</Text>
      <Button loading={start.isPending} disabled={!sessions.get(key)?.attempt} onClick={()=>{const attempt=sessions.get(key)?.attempt;if(attempt)start.mutate(attempt)}}>用同一幂等键重读开始回执</Button></Alert>}
    <Button variant="light" loading={history.isFetching} onClick={()=>{void history.refetch();if(activeId)void active.refetch();if(viewId)void viewed.refetch()}}>读取批历史／恢复活动批</Button>
    {error&&<Alert color="red">{error}</Alert>}
    {activeId&&(!current||active.isError)&&<Alert color="yellow">活动批状态未知，保留锁与取消入口，不认为停发、释放或最终提交。</Alert>}
    {current&&renderJob(current,false)}
    {current&&<MockCalibrationResult key={`${scope.labId}:${current.job_id}`} records={childRecords.filter(r=>r.lab_profile_id===scope.labId&&current.items.some(i=>i.run_id===r.run_id))}/>}
    {waiting&&current&&<Alert color={tone==='simulated'?'yellow':'blue'} data-testid="batch-manual"><Stack gap="xs">
      <Text>{current.status==='paused_failure'?'失败暂停：确认后只跳过失败项，不重测':'等待当前参考位置与接线确认'}</Text>
      <Text>{tone==='simulated'?'模拟人工步骤；未确认实物停发或换线安全':tone==='confirmed'?'已读取所有已启动项的真实单音清理确认；仅可核对此步骤接线／位置':'单音清理未知，禁止换线或移动参考天线，也不允许继续。'}</Text>
      <Text>当前参考位置：{current.items[current.current_index??-1]?.request.reference_antenna??'未知'}</Text>
      <TextInput label="重新输入当前参考位置" value={position} onChange={e=>setPosition(e.currentTarget.value)}/>
      <Checkbox label="确认仅对应当前项和当前人工步骤" checked={manual} onChange={e=>setManual(e.currentTarget.checked)}/>
      <Button disabled={tone==='unknown'||!manual||!transition} loading={resume.isPending} onClick={()=>{try{
        const body=buildBatchContinue(current,childRecords,transition!.item,transition!.id,position,manual);resume.mutate(body)
      }catch(cause){setError(message(cause))}}}>{current.status==='paused_failure'?'跳过失败项并继续':'确认当前步骤并继续'}</Button>
    </Stack></Alert>}
    {activeId&&<Button color="red" loading={cancel.isPending} onClick={()=>cancel.mutate()}>取消批校准并等待真实停发／释放</Button>}
    {history.isError&&<Alert color="red">批历史读取失败：{message(history.error)}；没有据此解锁。</Alert>}
    <Title order={5}>批历史（不覆盖活动身份）</Title>
    {history.data?.map(row=><Group key={row.job_id} justify="space-between"><Text size="xs">{row.job_id} · {statusLabels[row.status]}{row.items.some(i=>i.request.mock_input||i.status==='simulated')?' · 模拟演练（非实测）':''}</Text><Button size="xs" variant="subtle" onClick={()=>setViewId(row.job_id)}>只读查看</Button></Group>)}
    {!history.data?.length&&!history.isError&&<Text size="sm">暂无批历史；不是停发或未启动的证明。</Text>}
    {viewed.isError&&<Alert color="red">只读历史读取失败：{message(viewed.error)}</Alert>}
    {viewed.data&&!viewed.isError&&renderJob(viewed.data,true)}
    {viewed.data&&!viewed.isError&&!viewed.isPaused&&!viewedChildren.isError&&!viewedChildren.isPaused&&<MockCalibrationResult key={`${scope.labId}:${viewId}`} records={(viewedChildren.data??[]).filter(r=>r.lab_profile_id===scope.labId&&viewed.data!.items.some(i=>i.run_id===r.run_id))}/>}
  </Stack>
}
