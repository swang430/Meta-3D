import type { FixedRouteRequest, FixedRouteRecord, RouteSelection, RouteApplicationPreview, ConfirmRouteApplication } from '../../types/api'
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
