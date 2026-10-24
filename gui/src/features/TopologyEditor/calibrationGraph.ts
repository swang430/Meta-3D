import { MarkerType } from '@xyflow/react'
import type { Node, Edge } from '@xyflow/react'
import type { SwitchTopology, TopologyNode, TopologyConnection } from '../../api/switchTopologyService'
import type { CalibrationScopeSnapshot, FixedRouteRecord } from '../../types/api'
import { fixedRouteDisplay } from '../LabWorkspace/fixedRouteDisplay'

type Chain = CalibrationScopeSnapshot['payload']['chains'][number]
export type CalibrationNodeData = Record<string, unknown> & {
  title: string; role: string; reading: string; detail?: string; chains?: Chain[]
}
export interface CalibrationGraph {
  nodes: Node<CalibrationNodeData>[]; edges: Edge<{ label: string }>[]
  highlightedConnectionIds: string[]; problem: string | null; notice: string | null
}

/** 只转换已保存连接。测量用空口/参考节点不进入拓扑PATCH，也不重算任何损耗。 */
export function buildCalibrationGraph(topology: SwitchTopology, scope: CalibrationScopeSnapshot,
  labId: string, chainId: string | null, record?: FixedRouteRecord): CalibrationGraph {
  const graph: CalibrationGraph = { nodes: [], edges: [], highlightedConnectionIds: [], problem: null, notice: null }
  const reject = (message: string) => ({ ...graph, problem: message })
  if (scope.payload.lab_profile_id !== labId || scope.payload.chamber_id !== topology.chamber_id
    || scope.payload.topology.id !== topology.id || scope.payload.operating_mode !== 'mimo_ota') {
    return reject('当前拓扑与实验室的测量配置不一致，请重新读取配置。')
  }
  // 图示与实际请求都以同一保存快照为准；编辑器旧对象仅提供不影响测量的屏幕坐标。
  const saved=scope.payload.topology
  if(!Array.isArray(saved.nodes)||!Array.isArray(saved.connections)||!Array.isArray(saved.active_connections))
    return reject('保存配置缺少完整接线图，请重新读取配置。')
  const nodes:TopologyNode[]=saved.nodes.map((raw: unknown)=>{
    const n=raw as TopologyNode & {parameters:Record<string,unknown>}
    return {...n,params:n.parameters,position:topology.nodes.find(old=>old.id===n.id)?.position??{x:0,y:0}}
  })
  const active=saved.active_connections
  const connections=(saved.connections as TopologyConnection[]).filter(value=>active.includes(value.id))
  if (connections.some(e => !nodes.some(n=>n.id===e.source) || !nodes.some(n=>n.id===e.target))) {
    return reject('保存接线中有不存在的节点，请先在连接编辑中修正。')
  }
  const chain = scope.payload.chains.find(value => value.chain_id === chainId)
  const terminal = connections.find(value => value.id === chainId)
  if (chainId && (!chain || !terminal || !nodes.some(n => n.id === terminal.target))) {
    return reject('所选通路没有唯一的已保存连接，不能在图上开始测量。')
  }
  const selectedEdges = terminal ? [terminal] : []
  if (terminal) {
    let source = terminal.source
    const visited = new Set([terminal.id])
    // 无法确定完整上游时拒绝测量，不把残缺路径当作完整通路。
    while (!['ce_port', 'channel_emulator'].includes(nodes.find(n => n.id === source)?.type ?? '')) {
      const incoming = connections.filter(e => e.target === source && !visited.has(e.id))
      if (incoming.length !== 1) return reject('无法确定从F64输出到探头的唯一完整通路，请先核对保存接线。')
      selectedEdges.unshift(incoming[0]); visited.add(incoming[0].id); source = incoming[0].source
    }
  }
  graph.highlightedConnectionIds = selectedEdges.map(e => e.id)
  const firstNode = nodes.find(n=>n.id===selectedEdges[0]?.source)
  const port=firstNode?.params?.ce_port ?? firstNode?.label
  if (chain && firstNode?.type==='ce_port' && (typeof port!=='string'||port.trim()!==chain.ce_port.trim())) {
    return reject('图中F64输出口与服务器解析的通路不一致，请先核对保存接线。')
  }
  const visibleEdges = chain ? selectedEdges : connections
  const visibleIds = new Set(visibleEdges.flatMap(e => [e.source, e.target]))
  const orderedIds = chain ? [...new Set(selectedEdges.flatMap(e => [e.source, e.target]))] : [...visibleIds]
  const result = record?.result
  const identityMatches = record?.lab_profile_id === labId && result?.request.chain_id === chainId
    && result?.configuration?.chain && typeof result.configuration.chain === 'object'
    && !Array.isArray(result.configuration.chain)
    && 'chain_id' in result.configuration.chain && result.configuration.chain.chain_id === chainId
    && 'ce_port' in result.configuration.chain && result.configuration.chain.ce_port === chain?.ce_port
    && 'probe_id' in result.configuration.chain && result.configuration.chain.probe_id === chain?.probe_id
    && 'polarization' in result.configuration.chain && result.configuration.chain.polarization === chain?.polarization
  const recordMatches = identityMatches && result?.request.configuration_digest === scope.digest
  if (record && !recordMatches) graph.notice = '历史测量的通路或配置与当前不同；数值只在历史详情展示，不覆盖当前图。是否重新校准由操作员判断。'
  const shown = recordMatches && record ? fixedRouteDisplay(record) : null
  const positionFor=(index:number)=>({x:(Math.floor(index/4)%2?3-index%4:index%4)*240,y:40+Math.floor(index/4)*210})
  const uniquePositions=new Set(nodes.map(n=>`${n.position?.x??0}:${n.position?.y??0}`)).size===nodes.length
  graph.nodes = orderedIds.map((id, index) => {
    const node = nodes.find(value => value.id === id)!
    const choices = scope.payload.chains.filter(value => connections.some(e => e.id === value.chain_id && e.target === id))
    const isStart = Boolean(chain && index === 0 && ['ce_port','channel_emulator'].includes(node.type))
    return { id, type: 'calibration', position: chain ? positionFor(index)
      : uniquePositions && node.position ? node.position : { x: index % 3 * 260, y: Math.floor(index / 3) * 200 },
      data: { title: isStart && node.type === 'ce_port' ? `F64 输出 ${chain!.ce_port}` : node.label,
        role: node.type, reading: isStart ? shown?.source ?? '无实测读数' : '',
        reverse:chain?Math.floor(index/4)%2===1:false,
        detail: isStart && chain ? `保存的输出口 ${chain.ce_port}` : undefined, chains: choices } }
  })
  graph.edges = visibleEdges.map(edge => ({ id: edge.id, source: edge.source, target: edge.target,
    data: { label: `配置损耗 ${Number(edge.calibrated_loss_db ?? edge.cable_loss_db ?? 0).toFixed(2)} dB` },
    type: 'smoothstep', markerEnd:{type:MarkerType.ArrowClosed}, label: `配置损耗 ${Number(edge.calibrated_loss_db ?? edge.cable_loss_db ?? 0).toFixed(2)} dB`,
    style: { stroke: chain ? '#2563eb' : '#94a3b8', strokeWidth: chain ? 3 : 1.5 } }))
  if (chain && terminal) {
    const extensions = [
      {role:'air',title:'空口传播',detail:'发射探头到参考天线'},
      {role:'reference',title:'参考天线',detail: recordMatches ? result?.request.reference_antenna : '位置和身份由操作员确认'},
      {role:'receive_cable',title:'接收线缆',detail:'只修正参考天线到分析仪这一段'},
      {role:'analyzer',title:'信号分析仪',detail:'输入口实测功率'},
    ]
    extensions.forEach((value,index) => {
      const id = `measurement:${value.role}`
      graph.nodes.push({ id, type:'calibration',position:positionFor(orderedIds.length+index),data:{...value,
        reverse:Math.floor((orderedIds.length+index)/4)%2===1,
        reading:value.role==='analyzer' ? shown?.received ?? '无实测读数' : ''} })
      graph.edges.push({id:`measurement:link:${index}`, source:index===0 ? terminal.target : `measurement:${extensions[index-1].role}`,
        target:id,type:'smoothstep',markerEnd:{type:MarkerType.ArrowClosed},label:index===0?'空口（纳入整条通路）':'测量连接',data:{label:'测量参考连接'},
        style:{stroke:'#0f766e',strokeWidth:2,strokeDasharray:'6 4'}})
    })
    graph.nodes.push({id:'measurement:total',type:'calibration',position:{x:100,y:Math.ceil((orderedIds.length+4)/4)*210+40},
      data:{title:'整条通路测量',role:'total',reading:shown?.loss ?? '未计算',
        detail:`F64 输出 ${chain.ce_port} → 已保存接线 → 空口 → 参考天线；不是某段电缆损耗`}})
  }
  return graph
}
