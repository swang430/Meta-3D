import type { FixedRouteRequest, FixedRouteRecord, RouteSelection, RouteApplicationPreview, ConfirmRouteApplication,
  BatchPlanRequest, BatchPlan, BatchJobRecord, BatchContinueRequest } from '../../types/api'
import type { SwitchTopology } from '../../api/switchTopologyService'
import { getDraftModeConnectionIds } from './topologyDraft'

export type RouteScope = { labId:string; topologyId:string; mode:string; dirty:boolean; graph:SwitchTopology }
export type RouteFields = {frequency:string;power:string;antenna:string;cable:string;cableSource:string;samples:string;fixed:boolean;safe:boolean}

export function routeMatchesSaved(scope:RouteScope,route:RouteSelection|null|undefined) {
  return !scope.dirty && scope.mode!=='calibration' && Boolean(route && route.lab_profile_id===scope.labId &&
    route.topology_id===scope.topologyId && route.operating_mode===scope.mode && route.route_digest &&
    route.configuration_digest && route.node_ids.length>=2 && route.connection_ids.length && routeGraphMatchesSaved(scope.graph,route))
}

export function routeGraphMatchesSaved(graph:SwitchTopology,route:RouteSelection) {
  // 比较已有服务器快照，不在客户端重算摘要/校准资格。参数投影沿Task1的非展示声明。
  const sorted=(value:any):any=>Array.isArray(value)?value.map(sorted):value&&typeof value==='object'?
    Object.fromEntries(Object.entries(value).filter(([,v])=>v!==undefined).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>[k,sorted(v)])):value
  const equal=(a:unknown,b:unknown)=>JSON.stringify(sorted(a))===JSON.stringify(sorted(b))
  const params=(node:any)=>Object.fromEntries(Object.entries(node.params??{}).filter(([key])=>
    !['visible_modes','description','notes','ports','port_roles',...(node.id===route.node_ids[0]?['ce_port']:[])].includes(key)))
  const allNodes=[...route.nodes,...route.calibration_nodes]
  if(allNodes.some(node=>{const view=graph.nodes.find(item=>item.id===node.id);return !view||view.type!==node.type||!equal(params(view),params(node))}))return false
  const normal=new Set(getDraftModeConnectionIds(graph,route.operating_mode)),reference=new Set(getDraftModeConnectionIds(graph,'calibration'))
  const pairs=[...route.connections.map(edge=>({edge,active:normal})),...route.calibration_connections.map(edge=>({edge,active:reference}))]
  for(const {edge,active} of pairs){
    const view=graph.connections.find(item=>item.id===edge.id)
    if(!view||!active.has(view.id)||view.source!==edge.source||view.target!==edge.target||
      (view.source_pin??'out')!==(edge.source_pin??'out')||(view.target_pin??'in')!==(edge.target_pin??'in'))return false
    for(const [id,pin] of [[view.source,view.source_pin??'out'],[view.target,view.target_pin??'in']]){
      const current=graph.nodes.find(node=>node.id===id)!,snapshot=allNodes.find(node=>node.id===id)!
      const port=(node:any)=>({declared:Array.isArray(node.params?.ports)?node.params.ports.includes(pin):null,role:node.params?.port_roles?.[pin]??null})
      if(!equal(port(current),port(snapshot)))return false
    }
  }
  const declared=route.connection_ids.map(id=>graph.connections.find(edge=>edge.id===id)?.ce_port).filter(value=>value!=null).map(value=>String(value).trim())
  const root=graph.nodes.find(node=>node.id===route.node_ids[0])!
  // CE标签仅在Task1规定的ce_port节点、且无显式端口声明时参与身份，不比较其他展示文案。
  return declared.length?declared.every(port=>port===route.ce_port):
    String(root.params?.ce_port??(root.type==='ce_port'?root.label:'' )).trim()===route.ce_port
}

export function buildRouteAcquisitionRequest(scope:RouteScope,route:RouteSelection,form:RouteFields):FixedRouteRequest {
  const frequency=Number(form.frequency),power=Number(form.power),count=Number(form.samples)
  if (!routeMatchesSaved(scope,route) || !form.frequency.trim() || !form.power.trim() ||
    !Number.isFinite(frequency) || frequency<=0 || !Number.isFinite(power) || power< -100 || power>0 ||
    !Number.isInteger(count) || count<2 || count>10 || !form.antenna.trim() || !form.fixed || !form.safe ||
    (form.cable.trim() && !Number.isFinite(Number(form.cable)))) throw new Error('请先保存拓扑、选择当前完整路径，填写有效采集参数并确认固定接线和安全条件。')
  return {chain_id:route.chain_id,topology_id:route.topology_id,operating_mode:route.operating_mode,
    route_digest:route.route_digest,configuration_digest:route.configuration_digest!,frequency_mhz:frequency,
    requested_power_dbm:power,sample_count:count,reference_antenna:form.antenna.trim(),
    receive_cable_loss_db:form.cable.trim()?Number(form.cable):null,receive_cable_source:form.cableSource.trim()||null,
    fixed_route_confirmed:true,safety_confirmed:true}
}

export function runningRouteIdentity(record:FixedRouteRecord|undefined) {
  return record?.result?.version===2 ? record.result.configuration?.route_selection as RouteSelection|undefined : undefined
}

export function canReleaseRouteStart(pending:boolean,status:number|undefined,history:FixedRouteRecord[]|undefined) {
  return !pending && typeof status==='number' && status>=400 && status<500 && Array.isArray(history) &&
    !history.some(row=>row.status==='running')
}

export function routePreviewDisplay(preview:RouteApplicationPreview) {
  const db=(value:number|null|undefined)=>typeof value==='number' && Number.isFinite(value)?`${value.toFixed(2)} dB`:'未知'
  return {old:db(preview.old_value_db),next:db(preview.new_net_loss_db),delta:db(preview.delta_db)}
}

export function canAdoptRoute(scope:RouteScope,route:RouteSelection|null|undefined,preview:RouteApplicationPreview|undefined,runId?:string) {
  return Boolean(routeMatchesSaved(scope,route) && preview && preview.selection &&
    (!runId || preview.acquisition_run_id===runId) && preview.selection.lab_profile_id===scope.labId &&
    preview.selection.topology_id===scope.topologyId && preview.selection.operating_mode===scope.mode &&
    preview.selection.chain_id===route?.chain_id && preview.selection.route_digest===route?.route_digest &&
    preview.eligibility.eligible_for_adoption && preview.eligibility.measurement_provenance==='real')
}

export function buildRouteConfirmation(scope:RouteScope,route:RouteSelection,preview:RouteApplicationPreview,deadline:string,key:string):ConfirmRouteApplication {
  const until=new Date(deadline)
  if (!canAdoptRoute(scope,route,preview) || !deadline.trim() || !Number.isFinite(until.getTime()) || until.getTime()<=Date.now())
    throw new Error('请选择仍适用的服务器真实记录，并明确填写未来的选用截止时间。')
  return {acquisition_run_id:preview.acquisition_run_id,route_digest:preview.selection!.route_digest,
    expected_current_application_id:preview.expected_current_application_id??null,idempotency_key:key,
    confirmed:true,adoption_valid_until:until.toISOString()}
}

export type BatchReferenceFields={chainId:string;frequency:number;antenna:string;cable:string;cableSource:string}
export function buildBatchRequest(scope:RouteScope,paths:RouteSelection[],ids:string[],frequencies:number[],references:BatchReferenceFields[],fields:Pick<RouteFields,'power'|'samples'|'fixed'|'safe'>):BatchPlanRequest {
  if(scope.mode!=='mimo_ota'||!ids.length||new Set(ids).size!==ids.length||!frequencies.length||
    new Set(frequencies).size!==frequencies.length||frequencies.some(f=>!Number.isFinite(f)||f<=0))throw new Error('请选择已保存的MIMO完整路径及不重复的正频点。')
  const rows=ids.flatMap(id=>frequencies.map(frequency=>{
    const route=paths.find(p=>p.chain_id===id),reference=references.find(r=>r.chainId===id&&r.frequency===frequency)
    if(!route||!reference||!reference.cable.trim()||!reference.cableSource.trim())throw new Error('每条路径、每个频点均须填写参考位置、接收线损与来源。')
    const single=buildRouteAcquisitionRequest(scope,route,{...fields,frequency:String(frequency),antenna:reference.antenna,cable:reference.cable,cableSource:reference.cableSource})
    return {chain_id:id,frequency_mhz:frequency,reference_antenna:single.reference_antenna,
      receive_cable_loss_db:single.receive_cable_loss_db!,receive_cable_source:single.receive_cable_source!}
  }))
  return {topology_id:scope.topologyId,operating_mode:'mimo_ota',chain_ids:[...ids],frequencies_mhz:[...frequencies],references:rows,
    requested_power_dbm:Number(fields.power),sample_count:Number(fields.samples),fixed_route_confirmed:true,safety_confirmed:true}
}

export function batchStartRequest(scope:RouteScope,request:BatchPlanRequest,plan:BatchPlan):BatchPlanRequest {
  if(scope.dirty||scope.mode!=='mimo_ota'||plan.lab_profile_id!==scope.labId||plan.topology_id!==scope.topologyId||
    plan.operating_mode!==scope.mode||!plan.preview_digest)throw new Error('请保存当前图并重新预览。')
  if(plan.switch_scope_digest&&(!request.switch_wiring_confirmation||
    request.switch_wiring_confirmation.switch_scope_digest!==plan.switch_scope_digest||
    JSON.stringify(request.switch_wiring_confirmation)!==JSON.stringify(plan.switch_wiring_confirmation)))
    throw new Error('须先核对具体开关绑定及映射，提交接线声明后重新预览；旧摘要不能启动。')
  return {...request,preview_digest:plan.preview_digest}
}

export type BatchStartAttempt={request:BatchPlanRequest;key:string}
export function batchStartAttempt(previous:BatchStartAttempt|null,request:BatchPlanRequest,key:string):BatchStartAttempt {
  if(previous&&JSON.stringify(previous.request)!==JSON.stringify(request))throw new Error('先核对未知启动回执；不能改请求另起一次单音。')
  return previous??{request:structuredClone(request),key}
}
export function batchRejectionCanRelease(status:number|undefined,history:BatchJobRecord[]|undefined,key:string) {
  return (status===400||status===422)&&Array.isArray(history)&&
    !history.some(row=>row.idempotency_key===key)&&!findUnsettledBatch(history)
}
export function batchCanRelease(job:BatchJobRecord|undefined,records:FixedRouteRecord[]=[]) {
  if(job?.items.some(i=>['running','measuring'].includes(i.status)||['completed','simulated'].includes(i.status)&&!i.run_id))return false
  const started=job?.items.filter(i=>i.run_id)??[]
  const eachStartedSettled=started.length>0&&started.every(i=>i.status==='simulated'||records.some(r=>
    r.run_id===i.run_id&&r.status!=='running'&&r.result?.status!=='running'&&r.result?.cleanup_confirmed===true))
  return Boolean(job&&['completed','failed','cancelled'].includes(job.status)&&job.finalization_committed===true&&
    job.finalization_id&&job.f64_control_released===true&&(job.all_started_cleanup_confirmed===true||eachStartedSettled))
}
export function findUnsettledBatch(history:BatchJobRecord[]|undefined,records:FixedRouteRecord[]=[]) {
  // 恢复与运行中释放读同一个服务器安全结束判据；中断或缺损不是已停发。
  return history?.find(row=>!batchCanRelease(row,records))
}
export function batchCounts(job:BatchJobRecord) {
  return {total:job.items.length,completed:job.items.filter(i=>i.status==='completed').length,
    simulated:job.items.filter(i=>i.status==='simulated').length,failed:job.items.filter(i=>i.status==='failed').length}
}
export function batchToneState(job:BatchJobRecord,records:FixedRouteRecord[]):'confirmed'|'simulated'|'unknown' {
  // failed/cancelled可发生在启动前；其余已执行状态缺身份不能按“从未启动”跳过。
  if(job.items.some(i=>['completed','simulated','measuring','running','cleanup_unconfirmed','interrupted','incomplete'].includes(i.status)&&!i.run_id))return 'unknown'
  const started=job.items.filter(i=>i.run_id)
  if(started.some(i=>!records.some(r=>r.run_id===i.run_id)))return 'unknown'
  const children=started.map(i=>records.find(r=>r.run_id===i.run_id)!)
  if(children.some(r=>r.status==='running'||r.result?.status==='running'))return 'unknown'
  if(children.some(r=>r.status==='simulated'&&r.result?.status==='simulated')){
    return children.every(r=>r.status==='simulated'&&r.result?.status==='simulated')?'simulated':'unknown'
  }
  return children.every(r=>r.result?.cleanup_confirmed===true)?'confirmed':'unknown'
}
export function buildBatchContinue(job:BatchJobRecord,records:FixedRouteRecord[],itemId:string,transitionId:string,reference:string,confirmed:boolean):BatchContinueRequest {
  const item=job.items[job.current_index??-1]
  if(!['waiting_manual','paused_failure'].includes(job.status)||!item||item.item_id!==itemId||!transitionId||job.transition_id!==transitionId||
    reference.trim()!==item.request.reference_antenna||!confirmed||batchToneState(job,records)==='unknown')
    throw new Error('请重新读取当前人工步骤；仅确认当前项/transition，单音清理未知禁止换线或继续。')
  return {item_id:itemId,transition_id:transitionId,reference_antenna:reference.trim(),manual_confirmed:true,skip_failed:job.status==='paused_failure'}
}
export function batchChildReady(record:FixedRouteRecord|undefined) {
  if(!record)return false
  const context=record.batch_context,states=record.result?.states
  if(!context)return !states?.batch_job_id
  return context.active===false&&context.finalized===true&&Boolean(context.job_id&&context.lease_id&&context.finalization_id)
}
export function routeCanvasConnections(graph:SwitchTopology,mode:string,route:RouteSelection|null) {
  const normal=getDraftModeConnectionIds(graph,mode)
  return route&&route.operating_mode===mode&&routeGraphMatchesSaved(graph,route)?
    [...new Set([...normal,...route.calibration_connection_ids])]:normal
}
export function probePathDeclaration(graph:SwitchTopology,probeId:string,ids:string[],mappings:{node_id:string;path_name:string}[]) {
  const edges=ids.map(id=>graph.connections.find(e=>e.id===id))
  if(!ids.length||new Set(ids).size!==ids.length||edges.some(e=>!e||!e.source_pin?.trim()||!e.target_pin?.trim()))
    throw new Error('显式路径须选择不重复的有序连线，并保存每端实际端口。')
  const known=edges as SwitchTopology['connections']
  const nodes=[known[0].source,...known.map(e=>e.target)]
  const root=graph.nodes.find(n=>n.id===nodes[0])
  const switches=nodes.filter(id=>graph.nodes.some(n=>n.id===id&&n.type==='switch_slot'))
  if(!['ce_port','channel_emulator'].includes(root?.type??'')||nodes.at(-1)!==probeId||
    known.some((e,index)=>index>0&&e.source!==known[index-1].target)||new Set(nodes).size!==nodes.length||
    mappings.length!==switches.length||new Set(mappings.map(m=>m.node_id)).size!==switches.length||
    mappings.some(m=>!switches.includes(m.node_id)||!m.path_name.trim()))throw new Error('路径须按CE→探头连续顺序，逐开关填写已保存映射名；最终资格仍由服务器核验。')
  return {connection_ids:[...ids],switch_mappings:mappings.map(m=>({node_id:m.node_id,path_name:m.path_name.trim()}))}
}
