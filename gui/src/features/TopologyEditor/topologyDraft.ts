import type { SwitchTopology, TopologyNode, TopologyConnection } from '../../api/switchTopologyService';
import { getNodePorts } from './nodePortHelpers';

export const CALIBRATION_MODE = 'calibration';
export function addDraftNode(draft: SwitchTopology, node: TopologyNode, mode: string): SwitchTopology {
  return {...draft, nodes: [...draft.nodes, {...node, params: {...node.params, visible_modes: [mode]}}]};
}
export function addDraftConnection(draft: SwitchTopology, connection: TopologyConnection, mode: string): SwitchTopology {
  if (!draft.operating_modes.some(m=>m.id===mode)) throw new Error('请先选择接线模式');
  for (const [id, pin] of [[connection.source, connection.source_pin], [connection.target, connection.target_pin]]) {
    const node = draft.nodes.find(n=>n.id===id);
    if (!node || !pin || !getNodePorts(node).includes(pin)) throw new Error('请选择已声明的器件端口');
    if (node.params.connection_scope === 'calibration' && mode !== CALIBRATION_MODE) throw new Error('校准器件只能在校准接线模式中连接');
  }
  return {...draft, connections:[...draft.connections,{...connection,modes:[mode]}], operating_modes:draft.operating_modes.map(m=>m.id===mode?{...m,active_connections:[...(m.active_connections||[]),connection.id]}:m)};
}
export function removeDraftConnections(draft: SwitchTopology, ids: string[]): SwitchTopology {
  const removed = new Set(ids);
  return {...draft,connections:draft.connections.filter(c=>!removed.has(c.id)),operating_modes:draft.operating_modes.map(m=>({...m,active_connections:(m.active_connections||[]).filter(id=>!removed.has(id))}))};
}
export function removeDraftNodes(draft: SwitchTopology, ids: string[]): SwitchTopology {
  const removed = new Set(ids);
  const cleaned = removeDraftConnections(draft,draft.connections.filter(c=>removed.has(c.source)||removed.has(c.target)).map(c=>c.id));
  return {...cleaned,nodes:cleaned.nodes.filter(n=>!removed.has(n.id))};
}
export function updateDraftNode(draft: SwitchTopology, node: TopologyNode): SwitchTopology {
  const ports = getNodePorts(node);
  for (const c of draft.connections) {
    if ((c.source===node.id && !ports.includes(c.source_pin||'')) || (c.target===node.id && !ports.includes(c.target_pin||''))) throw new Error('该端口仍有连线，请先删除或改接连线');
  }
  return {...draft,nodes:draft.nodes.map(n=>n.id===node.id?node:n)};
}
