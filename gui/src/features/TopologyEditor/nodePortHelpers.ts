/**
 * Explicit declaration parsing for forms, handles and connection validation.
 *
 * Why this exists: source_pin / target_pin used to be free-text, which let
 * 这里描述画布端点，不是厂商能力清单，也不构成真实仪器端口或自动控制资格。
 *
 * getNodePorts/defaults below are ONLY legacy visual suggestions. New connection
 * candidates and quantities use resolveNodePorts, never that fallback table.
 */
import type { TopologyNode, TopologyConnection, TopologyPortDirection } from '../../api/switchTopologyService'
import {resolvePortHandles} from './baseStationPorts'

export const isBaseStation = (node: Pick<TopologyNode,'type'>) => ['communication_tester','bse_port'].includes(node.type)
export const directionLabels: Record<TopologyPortDirection,string> = {
  input:'输入',output:'输出',bidirectional:'双向声明',unknown:'方向未声明，非双向能力',
}
const directions=new Set(Object.keys(directionLabels))
const objectMap=(value:unknown):value is Record<string,unknown>=>Boolean(value)&&typeof value==='object'&&!Array.isArray(value)

/** 只解析明确合法的清单；旧示意不能成为数量、候选端口或能力声明。 */
export function resolveNodePorts(node: TopologyNode | undefined) {
  const value=node?.params?.ports
  const declared=Array.isArray(value)&&value.length>0&&value.every(p=>typeof p==='string'&&p.length>0&&p.trim()===p)&&new Set(value).size===value.length
  const ports:string[]=declared?[...value]:[]
  const bse=new Map(node&&isBaseStation(node)?resolvePortHandles({...node.params,ports}).map(p=>[p.id,p.handleType==='source'?'output':'input'] as const):[])
  const resolved=ports.map(id=>{
    const explicit=node?.params?.port_directions?.[id]
    const direction:TopologyPortDirection=bse.get(id)??(typeof explicit==='string'&&directions.has(explicit)?explicit as TopologyPortDirection:'unknown')
    const source:'BSE'|'explicit'|'unknown'=bse.has(id)?'BSE':typeof explicit==='string'&&directions.has(explicit)?'explicit':'unknown'
    return {id,direction,source}
  })
  const effectiveDirections=Object.fromEntries(resolved.map(p=>[p.id,p.direction]))
  const directionSources=Object.fromEntries(resolved.map(p=>[p.id,p.source]))
  return {ports,declared,effectiveDirections,directionSources}
}

export function portCountLabel(node:TopologyNode) {
  const parsed=resolveNodePorts(node)
  if(!parsed.declared)return '端口数量未声明/旧版示意'
  const count=parsed.ports.length
  return isBaseStation(node)?`已声明逻辑端口 ${count}；物理连接器见运行映射`:
    node.type==='air_path'?`已声明虚拟参考端点 ${count}`:`已声明端口 ${count}（未核验硬件）`
}

/** 主动声明的写校验；旧值只有未动时才可保形读取。 */
export function validateNodePortDeclaration(node:TopologyNode):void {
  const parsed=resolveNodePorts(node)
  if(!parsed.declared)throw new Error(`器件 ${node.id} 必须声明非空且不重复的端口清单`)
  for(const key of ['port_directions',...(isBaseStation(node)?['port_roles']:[])]){
    if(!Object.hasOwn(node.params,key))continue
    const map=node.params[key],allowed=key==='port_roles'?new Set(['dl','ul']):directions
    if(!objectMap(map))throw new Error(`器件 ${node.id} 的 ${key} 必须是非null对象`)
    for(const [id,value] of Object.entries(map))if(!parsed.ports.includes(id)||typeof value!=='string'||!allowed.has(value))throw new Error(`器件 ${node.id} 端口 ${id} 的 ${key} 无效`)
  }
  if(isBaseStation(node))for(const id of parsed.ports){
    const role=node.params.port_roles?.[id],explicit=node.params.port_directions?.[id]
    if((role==='dl'||role==='ul')&&explicit!==undefined&&explicit!=='unknown'&&explicit!==(role==='dl'?'output':'input'))
      throw new Error(`器件 ${node.id} 端口 ${id} 的通用方向与BSE角色冲突`)
  }
}

export function validateConnectionPorts(nodes:TopologyNode[],edge:TopologyConnection):void {
  for(const [end,forbidden,defaultPin] of [['source','input','out'],['target','output','in']] as const){
    const node=nodes.find(n=>n.id===edge[end]),pin=edge[`${end}_pin`]??defaultPin,parsed=resolveNodePorts(node)
    if(!node||!parsed.declared||!parsed.ports.includes(pin))throw new Error(`连线 ${edge.id} ${end} 器件 ${edge[end]} 端口 ${pin} 未列入显式声明`)
    if(parsed.effectiveDirections[pin]===forbidden)throw new Error(`连线 ${edge.id} 器件 ${node.id} 端口 ${pin} 方向 ${forbidden} 不允许此接线`)
  }
}

export function edgePortPresentation(nodes:TopologyNode[],edge:TopologyConnection) {
  try{validateConnectionPorts(nodes,edge)}catch{return {arrowEnd:false,arrowStart:false,warning:'旧接线不合法或端口未声明；请核对器件/端口'}}
  const source=resolveNodePorts(nodes.find(n=>n.id===edge.source)).effectiveDirections[edge.source_pin??'out']
  const target=resolveNodePorts(nodes.find(n=>n.id===edge.target)).effectiveDirections[edge.target_pin??'in']
  if(source==='unknown'||target==='unknown')return {arrowEnd:false,arrowStart:false,warning:'方向未声明，非双向能力'}
  return {arrowEnd:true,arrowStart:source==='bidirectional'&&target==='bidirectional'&&edge.direction==='Bi-Di',warning:null}
}

const DEFAULT_PORTS_BY_TYPE: Record<string, string[]> = {
  ce_port: ['out'],
  bse_port: ['out'],
  sa_port: ['in'],
  switch_slot: ['P1', 'P2', 'P3', 'P4'],
  probe: ['in'],
  channel_emulator: ['in1', 'in2', 'in3', 'in4', 'out'],
  communication_tester: [],
  emcenter: ['switch_in', 'pa_out', 'sw_out', 'pa_in'],
  reference_antenna: ['rf'],
  signal_analyzer: ['rf_in'],
  vna: ['Port1', 'Port2'],
  amplifier: ['in', 'out'],
  combiner: ['in1', 'in2', 'in3', 'in4', 'out'],
  pad: ['in', 'out'],
  antenna: ['P1'],
  termination: ['in'],
}

export function getNodePorts(node: TopologyNode | undefined): string[] {
  if (!node) return ['out', 'in']
  const declared = node.params?.ports
  if (Array.isArray(declared) && declared.every((p) => typeof p === 'string')) {
    return declared as string[]
  }
  return DEFAULT_PORTS_BY_TYPE[node.type] || ['out', 'in']
}

/** 仅供新增线缆表单建议，须核对并应用；不是默认端口能力。 */
export function suggestedPassivePorts(type: string): string[] {
  return ['cable', 'receive_cable'].includes(type) ? ['A', 'B'] : []
}

/** Convenience: map node port list to Mantine Select options. */
export function nodePortsToSelectOptions(node: TopologyNode | undefined, end?:'source'|'target') {
  const parsed=resolveNodePorts(node)
  return parsed.ports.filter(id=>!end||parsed.effectiveDirections[id]!== (end==='source'?'input':'output'))
    .map(id=>({value:id,label:`${id} · ${directionLabels[parsed.effectiveDirections[id]]}`}))
}
