import type { SwitchTopology, TopologyNode, TopologyConnection } from '../../api/switchTopologyService';
import { resolveNodePorts, validateNodePortDeclaration, validateConnectionPorts, isBaseStation } from './nodePortHelpers';

export const CALIBRATION_MODE = 'calibration';
// 与 TopologyService.resolve_paths/get_mode_connections 一致；空列表仍有历史标签回退语义。
export function getDraftModeConnectionIds(draft: SwitchTopology, mode: string): string[] {
  const configured=draft.operating_modes.find(m=>m.id===mode);
  if (!configured) return [];
  const active=configured.active_connections;
  return active?.length ? [...active] : draft.connections.filter(c=>c.modes?.includes(mode)).map(c=>c.id);
}
function synchronizeModeDeclarations(draft: SwitchTopology, changed: Set<string>): SwitchTopology {
  return {...draft,connections:draft.connections.map(connection=>({...connection,modes:[
    ...(connection.modes||[]).filter(id=>!changed.has(id)),
    ...draft.operating_modes.filter(m=>changed.has(m.id)&&m.active_connections?.includes(connection.id)).map(m=>m.id),
  ]}))};
}
export function addDraftNode(draft: SwitchTopology, node: TopologyNode, mode: string): SwitchTopology {
  return {...draft, nodes: [...draft.nodes, {...node, params: {...node.params, visible_modes: [mode]}}]};
}
export function addDraftConnection(draft: SwitchTopology, connection: TopologyConnection, mode: string): SwitchTopology {
  if (!draft.operating_modes.some(m=>m.id===mode)) throw new Error('请先选择接线模式');
  validateConnectionPorts(draft.nodes,connection);
  for (const [id, pin] of [[connection.source, connection.source_pin], [connection.target, connection.target_pin]]) {
    const node = draft.nodes.find(n=>n.id===id);
    if (!node || !pin || !resolveNodePorts(node).ports.includes(pin)) throw new Error('请选择已声明的器件端口');
    if (node.params.connection_scope === 'calibration' && mode !== CALIBRATION_MODE) throw new Error('校准器件只能在校准接线模式中连接');
  }
  return synchronizeModeDeclarations({...draft,connections:[...draft.connections,{...connection,modes:[mode]}],operating_modes:draft.operating_modes.map(m=>m.id===mode?{...m,active_connections:[...getDraftModeConnectionIds(draft,m.id),connection.id]}:m)},new Set([mode]));
}
function assertUnreferencedConnections(draft: SwitchTopology, ids: string[], removedNodeIds: string[] = []): void {
  const changed = new Set(ids), removed = new Set(removedNodeIds);
  const probes = draft.nodes.filter(node=>node.type==='probe' && !removed.has(node.id) &&
    Array.isArray(node.params.rf_path_selection?.connection_ids) &&
    node.params.rf_path_selection.connection_ids.some((id: string)=>changed.has(id)));
  if (probes.length) throw new Error(`探头 ${probes.map(p=>`${p.label}（${p.id}）`).join('、')}` +
    ` 显式路径引用连线 ${ids.join('、')}，请先在探头属性重新声明路径`);
}
export function updateDraftConnection(draft: SwitchTopology, connection: TopologyConnection): SwitchTopology {
  const old = draft.connections.find(edge=>edge.id===connection.id);
  if (!old) throw new Error('连线已不存在，请重新选择');
  if (old.source!==connection.source || old.target!==connection.target ||
    (old.source_pin??'out')!==(connection.source_pin??'out') ||
    (old.target_pin??'in')!==(connection.target_pin??'in')) {
    assertUnreferencedConnections(draft,[connection.id]);
    validateConnectionPorts(draft.nodes,connection);
  }
  return {...draft,connections:draft.connections.map(edge=>edge.id===connection.id?{...connection}:edge)};
}
export function removeDraftConnections(draft: SwitchTopology, ids: string[]): SwitchTopology {
  assertUnreferencedConnections(draft,ids);
  const removed = new Set(ids);
  const changed = new Set(draft.operating_modes.filter(m=>getDraftModeConnectionIds(draft,m.id).some(id=>removed.has(id))).map(m=>m.id));
  const affected = new Set(draft.connections.filter(c=>removed.has(c.id)).flatMap(c=>[c.source,c.target]));
  const nodes = draft.nodes.map(node=>{
    if (!affected.has(node.id) || Array.isArray(node.params.visible_modes)) return node;
    // 删除接线只删接线，不撤掉历史器件在原模式中的唯一编辑入口。
    const incident = new Set(draft.connections.filter(c=>c.source===node.id||c.target===node.id).map(c=>c.id));
    const visible_modes = draft.operating_modes.filter(mode=>
      (node.params.connection_scope!=='calibration' || mode.id===CALIBRATION_MODE) &&
      getDraftModeConnectionIds(draft,mode.id).some(id=>incident.has(id))
    ).map(mode=>mode.id);
    return {...node,params:{...node.params,visible_modes}};
  });
  return synchronizeModeDeclarations({...draft,nodes,connections:draft.connections.filter(c=>!removed.has(c.id)),operating_modes:draft.operating_modes.map(m=>changed.has(m.id)?{...m,active_connections:getDraftModeConnectionIds(draft,m.id).filter(id=>!removed.has(id))}:m)},changed);
}
export function removeDraftNodes(draft: SwitchTopology, ids: string[]): SwitchTopology {
  const removed = new Set(ids);
  const connectionIds = draft.connections.filter(c=>removed.has(c.source)||removed.has(c.target)).map(c=>c.id);
  assertUnreferencedConnections(draft,connectionIds,ids);
  return removeDraftConnections({...draft,nodes:draft.nodes.filter(n=>!removed.has(n.id))},connectionIds);
}
export function updateDraftNode(draft: SwitchTopology, node: TopologyNode, declaredPorts?: string[]): SwitchTopology {
  // 历史未声明模式保持原语义；显式应用必须保留至少一个可恢复的有效入口。
  const modes=node.params.visible_modes;
  if (Array.isArray(modes) && (!modes.length || modes.some(mode=>!draft.operating_modes.some(item=>item.id===mode)))) {
    throw new Error('至少选择一个有效显示模式；可从器件列表恢复隐藏器件');
  }
  if (node.params.connection_scope==='calibration' && Array.isArray(modes) && (modes.length!==1 || modes[0]!==CALIBRATION_MODE)) {
    throw new Error('校准器件只能显示在校准接线模式');
  }
  const previous=draft.nodes.find(n=>n.id===node.id);
  // 只改名称或显示模式时，不把历史图的默认画布端点写成新的端口声明。
  if (declaredPorts !== undefined) {
    node={...node,params:{...node.params,ports:declaredPorts}};
  }
  const declarationChanged=!previous||previous.type!==node.type||['ports','port_directions',...(isBaseStation(node)?['port_roles']:[])].some(key=>JSON.stringify(previous.params[key])!==JSON.stringify(node.params[key]));
  if (declarationChanged || declaredPorts !== undefined) {
    validateNodePortDeclaration(node);
    const ports = resolveNodePorts(node).ports;
    for (const c of draft.connections) {
      // 缺省端口沿用 TopologyConnection schema / TopologyService 的 out/in，非新猜设备能力。
      if ((c.source===node.id && !ports.includes(c.source_pin ?? 'out')) || (c.target===node.id && !ports.includes(c.target_pin ?? 'in'))) throw new Error(`器件 ${node.id} 端口仍有连线 ${c.id}，请先删除或改接连线`);
      if(c.source===node.id||c.target===node.id)validateConnectionPorts(draft.nodes.map(n=>n.id===node.id?node:n),c);
    }
  }
  return {...draft,nodes:draft.nodes.map(n=>n.id===node.id?node:n)};
}
