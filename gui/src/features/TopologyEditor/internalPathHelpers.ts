import type {SwitchTopology,TopologyNode} from '../../api/switchTopologyService';
import {isBaseStation,resolveNodePorts,validateNodePortDeclaration} from './nodePortHelpers';

const twoPortTypes=new Set(['amplifier','pad','cable','receive_cable']);
export const noInternalForwardingTypes=new Set(['termination','ce_port','channel_emulator','bse_port',
  'communication_tester','sa_port','signal_analyzer','vna','emcenter']);

/** 只验证操作员声明；不补pair、不推导硬件能力，unknown允许留作草稿。 */
export function validateNodeInternalPaths(node:TopologyNode):void {
  if(!Object.hasOwn(node.params,'internal_paths'))return;
  const paths:unknown=node.params.internal_paths,parsed=resolveNodePorts(node);
  if(!Array.isArray(paths))throw new Error(`器件 ${node.id} internal_paths 必须是非null列表`);
  if(paths.length&&noInternalForwardingTypes.has(node.type))throw new Error(`器件 ${node.id} 类型不允许非空内部通路`);
  if(paths.length&&!parsed.declared)throw new Error(`器件 ${node.id} 内部通路须引用显式端口`);
  if(paths.length&&twoPortTypes.has(node.type)&&parsed.ports.length!==2)
    throw new Error(`器件 ${node.id} 内部通路须恰有两个显式端口；请核对 ${JSON.stringify(paths)}`);
  if(node.type==='amplifier'&&paths.length>1)throw new Error(`器件 ${node.id} 放大器仅允许一条单向内部通路`);
  if(paths.length)validateNodePortDeclaration(node);
  const seen=new Set<string>();
  for(const pair of paths){
    if(!pair||typeof pair!=='object'||Array.isArray(pair)||Object.keys(pair).sort().join(',')!=='from_port,to_port')
      throw new Error(`器件 ${node.id} 内部通路每行只能含 from_port/to_port`);
    const {from_port:from,to_port:to}=pair;
    if([from,to].some(id=>typeof id!=='string'||!id||id.trim()!==id||!parsed.ports.includes(id))||from===to)
      throw new Error(`器件 ${node.id} 内部通路 ${from}→${to} 引用无效端口或自环`);
    const key=JSON.stringify([from,to]);
    if(seen.has(key))throw new Error(`器件 ${node.id} 内部通路 ${from}→${to} 重复`);
    seen.add(key);
    if(parsed.effectiveDirections[from]==='output'||parsed.effectiveDirections[to]==='input')
      throw new Error(`器件 ${node.id} 内部通路 ${from}→${to} 与已声明方向冲突`);
  }
}

const contract=(node:TopologyNode)=>[node.type,...['ports','port_directions','internal_paths','rf_path_selection',
  ...(isBaseStation(node)?['port_roles']:[])].map(key=>[Object.hasOwn(node.params,key),node.params[key]])];
const edgeContract=(edge:SwitchTopology['connections'][number])=>[edge.source,edge.target,
  edge.source_pin,edge.target_pin,edge.modes];
const equal=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b);
const modeIds=(graph:SwitchTopology,mode:string)=>{
  const declaration=graph.operating_modes.find(m=>m.id===mode);
  if(!declaration)return [];
  return declaration?.active_connections?.length?declaration.active_connections:graph.connections.filter(e=>e.modes?.includes(mode)).map(e=>e.id);
};

/** 原子应用前遍历所有模式和显式探头引用；不把未接完草稿当成可运行链。 */
export function validateDraftInternalPaths(draft:SwitchTopology,previous:SwitchTopology):void {
  for(const node of draft.nodes)validateNodeInternalPaths(node);
  const oldNodes=new Map(previous.nodes.map(n=>[n.id,n])),oldEdges=new Map(previous.connections.map(e=>[e.id,e]));
  const changedNodes=new Set(draft.nodes.filter(n=>!oldNodes.has(n.id)||!equal(contract(n),contract(oldNodes.get(n.id)!))).map(n=>n.id));
  const changedEdges=new Set([...draft.connections.filter(e=>!oldEdges.has(e.id)||!equal(edgeContract(e),edgeContract(oldEdges.get(e.id)!))).map(e=>e.id),
    ...previous.connections.filter(e=>!draft.connections.some(n=>n.id===e.id)).map(e=>e.id)]);
  const modes=new Set([...draft.operating_modes,...previous.operating_modes].map(m=>m.id));
  const references:string[]=[];
  for(const probe of draft.nodes){
    const ids=probe.type==='probe'?probe.params.rf_path_selection?.connection_ids:undefined;
    if(!Array.isArray(ids)||!ids.length)continue;
    const edges=ids.map(id=>draft.connections.find(e=>e.id===id));
    if(edges.some(e=>!e))throw new Error(`探头 ${probe.id} 显式路径引用缺失连线 ${ids.join('、')}`);
    const path=[edges[0]!.source,...edges.map(e=>e!.target)];
    const relevantModes=[...modes].filter(mode=>ids.every(id=>modeIds(draft,mode).includes(id))||ids.every(id=>modeIds(previous,mode).includes(id)));
    const modeChanged=[...modes].some(mode=>ids.some(id=>modeIds(draft,mode).includes(id)!==modeIds(previous,mode).includes(id)));
    const incidentChanged=relevantModes.some(mode=>{
      const before=modeIds(previous,mode),after=modeIds(draft,mode);
      const touched=new Set([...changedEdges,...before.filter(id=>!after.includes(id)),...after.filter(id=>!before.includes(id))]);
      return [...touched].some(id=>(after.includes(id)||before.includes(id))&&
        [draft.connections.find(e=>e.id===id),oldEdges.get(id)].some(e=>e&&(path.includes(e.source)||path.includes(e.target))));
    });
    if(!modeChanged&&!incidentChanged&&!path.some(id=>changedNodes.has(id))&&!ids.some(id=>changedEdges.has(id)))continue;
    for(let i=1;i<path.length-1;i++){
      const node=draft.nodes.find(n=>n.id===path[i]);if(!node)continue;
      const old=oldNodes.get(node.id),declared=Object.hasOwn(node.params,'internal_paths');
      // 未触及声明的旧图保持缺键；主动撤销不能借此恢复旧推断。
      if(!declared&&old&&!Object.hasOwn(old.params,'internal_paths')&&node.type==='switch_slot')continue;
      const from=edges[i-1]!.target_pin,to=edges[i]!.source_pin;
      if(!declared||!from||!to||!node.params.internal_paths.some((p:any)=>p.from_port===from&&p.to_port===to))
        references.push(`探头 ${probe.id} 连线 ${edges[i-1]!.id}/${edges[i]!.id}：器件 ${node.id} 未声明内部通路 ${from??'?'}→${to??'?'}（模式 ${relevantModes.join('、')||'未组成完整路径'}）`);
    }
  }
  if(references.length)throw new Error(references.join('；'));
}
