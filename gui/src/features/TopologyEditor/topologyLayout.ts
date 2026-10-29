import type {SwitchTopology,TopologyNode} from '../../api/switchTopologyService';
import {getNodePorts} from './nodePortHelpers';

type Point={x:number;y:number};
type Size={width:number;height:number};
export type LayoutUndo={context:string;id:SwitchTopology['id'];revision:number;positions:Map<string,Point|undefined>};
const natural=new Intl.Collator('en',{numeric:true,sensitivity:'base'});
const compare=(a:string,b:string)=>natural.compare(a,b)||a.localeCompare(b);
/** 纯显示尺寸；不新增端口或推断射频能力。隐藏节点使用保守尺寸，可见节点取实测较大值。 */
export function layoutNodeSize(node:TopologyNode,measured?:Partial<Size>):Size {
  return {width:Math.max(240,measured?.width??0),height:Math.max(100,(getNodePorts(node).length+1)*28,measured?.height??0)};
}
export function captureLayoutUndo(graph:SwitchTopology,context:string):LayoutUndo {
  return {context,id:graph.id,revision:graph.revision,positions:new Map(graph.nodes.map(node=>[node.id,node.position?{...node.position}:undefined]))};
}
/** 只撤回位置，绝不把旧节点/属性/接线快照覆盖当前草稿。 */
export function restoreLayoutPositions(graph:SwitchTopology,undo:LayoutUndo,context:string):SwitchTopology {
  if(undo.context!==context||undo.id!==graph.id||undo.revision!==graph.revision)return graph;
  return {...graph,nodes:graph.nodes.map(node=>{
    if(!undo.positions.has(node.id))return node;
    const {position:_,...rest}=node,position=undo.positions.get(node.id);
    // 运行时历史JSON可能无position；撤回必须恢复缺键，不伪造默认位置。
    return position?{...rest,position:{...position}}:rest as TopologyNode;
  })};
}
/** 全模式共享图：实际有向边分层，强连通分量同层；端口自然序只影响显示，不改任何业务数据。 */
export function layoutTopology(graph:SwitchTopology,measured=new Map<string,Partial<Size>>()):SwitchTopology {
  const ids=graph.nodes.map(n=>n.id).sort(compare),known=new Set(ids);
  const outgoing=new Map(ids.map(id=>[id,graph.connections.filter(c=>c.source===id&&known.has(c.target))
    .sort((a,b)=>compare(a.source_pin??'',b.source_pin??'')||compare(a.target,b.target)||compare(a.id,b.id))]));
  const reach=new Map(ids.map(id=>{
    const seen=new Set<string>(),queue=[id];
    for(let i=0;i<queue.length;i++)for(const edge of outgoing.get(queue[i])??[])if(!seen.has(edge.target)){seen.add(edge.target);queue.push(edge.target);}
    return [id,seen] as const;
  }));
  const groups:string[][]=[],groupOf=new Map<string,number>();
  for(const id of ids)if(!groupOf.has(id)){
    const members=ids.filter(other=>other===id||(reach.get(id)!.has(other)&&reach.get(other)!.has(id)));
    const index=groups.length;groups.push(members);members.forEach(member=>groupOf.set(member,index));
  }
  const successors=groups.map(()=>new Set<number>()),indegree=groups.map(()=>0),rank=groups.map(()=>0);
  for(const edge of graph.connections){const a=groupOf.get(edge.source),b=groupOf.get(edge.target);
    if(a!==undefined&&b!==undefined&&a!==b&&!successors[a].has(b)){successors[a].add(b);indegree[b]++;}}
  const queue=groups.map((_,i)=>i).filter(i=>!indegree[i]),order=new Map<string,string>();
  queue.forEach(i=>groups[i].forEach(id=>order.set(id,id)));
  for(let i=0;i<queue.length;i++){
    const g=queue[i];
    for(const id of groups[g])for(const edge of outgoing.get(id)??[]){
      const target=groupOf.get(edge.target)!;if(target===g)continue;
      const key=`${order.get(id)??id}/${edge.source_pin??''}/${edge.target_pin??''}/${edge.target}`;
      for(const member of groups[target])if(!order.has(member)||compare(key,order.get(member)!)<0)order.set(member,key);
    }
    for(const next of successors[g]){rank[next]=Math.max(rank[next],rank[g]+1);if(!--indegree[next])queue.push(next);}
  }
  const byId=new Map(graph.nodes.map(node=>[node.id,node])),sizes=new Map(ids.map(id=>[id,layoutNodeSize(byId.get(id)!,measured.get(id))]));
  const depth=groups.map(()=>0);
  for(const g of [...queue].reverse())for(const next of successors[g])depth[g]=Math.max(depth[g],depth[next]+1);
  const layers=new Map<number,string[]>();
  ids.forEach(id=>{const r=rank[groupOf.get(id)!];layers.set(r,[...(layers.get(r)??[]),id]);});
  const positions=new Map<string,Point>();let x=80;
  const portOffset=(id:string,pin:string|undefined)=>{
      const ports=getNodePorts(byId.get(id)!),index=pin?ports.indexOf(pin):-1;
      return sizes.get(id)!.height*(index<0?0.5:(index+1)/(ports.length+1));
  };
  for(const [,layer] of [...layers].sort((a,b)=>a[0]-b[0])){
    const preferred=new Map(layer.map(id=>{
      const incoming=graph.connections.filter(edge=>edge.target===id&&positions.has(edge.source)).sort((a,b)=>compare(a.id,b.id));
      const anchors=incoming.map(edge=>positions.get(edge.source)!.y+portOffset(edge.source,edge.source_pin)-portOffset(id,edge.target_pin));
      return [id,anchors.length?Math.max(80,anchors.reduce((sum,y)=>sum+y,0)/anchors.length):80] as const;
    }));
    // 优先连续链，避免同层其他模式的终点先占满整列、把PA链整体挤到下方。
    layer.sort((a,b)=>depth[groupOf.get(b)!]-depth[groupOf.get(a)!]||preferred.get(a)!-preferred.get(b)!||compare(order.get(a)??a,order.get(b)??b)||compare(a,b));let y=80;
    for(const id of layer){y=Math.max(y,preferred.get(id)!);positions.set(id,{x,y});y+=sizes.get(id)!.height+100;}
    // 端口标签与线缆标签保留独立水平走线空间。
    x+=Math.max(...layer.map(id=>sizes.get(id)!.width))+500;
  }
  // 单入单出的连续段反向对齐下游端口；保留同列不重叠，不要求回路或汇合点零交叉。
  for(const [,layer] of [...layers].sort((a,b)=>b[0]-a[0])){
    const preferred=new Map(layer.map(id=>{
      const edges=outgoing.get(id)!;
      const edge=edges.length===1?edges[0]:undefined;
      const target=edge?positions.get(edge.target):undefined;
      return [id,edge&&target&&target.x>positions.get(id)!.x&&graph.connections.filter(c=>c.target===edge.target).length===1
        ?target.y+portOffset(edge.target,edge.target_pin)-portOffset(id,edge.source_pin):positions.get(id)!.y] as const;
    }));
    layer.sort((a,b)=>preferred.get(a)!-preferred.get(b)!||compare(order.get(a)??a,order.get(b)??b));let y=80;
    for(const id of layer){y=Math.max(y,preferred.get(id)!);positions.get(id)!.y=y;y+=sizes.get(id)!.height+100;}
  }
  return {...graph,nodes:graph.nodes.map(node=>({...node,position:positions.get(node.id)!}))};
}
