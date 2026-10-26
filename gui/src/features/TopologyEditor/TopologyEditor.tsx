import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  ReactFlow, 
  Background, 
  Controls, 
  MiniMap,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  MarkerType,
  useReactFlow,
} from '@xyflow/react';
import type { Connection, Edge, Node, NodeChange, EdgeChange } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { 
  Group, 
  Select, 
  Button, 
  Text, 
  Paper, 
  Loader, 
  Center,
  Badge,
  Stack,
  Alert,
  Card,
  Title,
  Drawer,
  TextInput,
  NumberInput,
  Divider,
  MultiSelect,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { 
  IconDeviceFloppy, 
  IconAlertCircle, 
  IconTopologyRing, 
  IconCheck, 
  IconAlertTriangle,
  IconX,
  IconCircleDot,
  IconRefresh,
} from '@tabler/icons-react';

import { useOperationalLab, useOperationalLabSwitchGuard } from '../OperationalLab';
import { customNodeTypes } from './CustomNodes';
import { customEdgeTypes } from './CustomEdges';
import {NominalPropertyFields} from './NominalPropertyFields';
import {nominalFieldsForNode, edgeNominalFields, cableNominalFields, setNodeNominal, setEdgeNominal} from './nominalProperties';
import { RouteCalibrationPanel } from './RouteCalibrationPanel';
import { routeCanvasConnections, probePathDeclaration } from './routeCalibrationState';
import { routeGraphMatchesSaved } from './routeCalibrationState';
import type { RouteSelection } from '../../types/api';
import { getNodePorts, nodePortsToSelectOptions, suggestedPassivePorts } from './nodePortHelpers';
import { addDraftNode, addDraftConnection, removeDraftNodes, removeDraftConnections, updateDraftNode, updateDraftConnection, getDraftModeConnectionIds, CALIBRATION_MODE } from './topologyDraft';
import { switchTopologyService, topologyUpdatePayload, mergeConnectionDeclarations } from '../../api/switchTopologyService';
import type { SwitchTopology, TopologyConnection, TopologyNode, ConnectionNumericField, ConnectionNumericDeclarations } from '../../api/switchTopologyService';
import apiClient from '../../api/client';
import { logFrontendEvent } from '../../observability/frontendLogger';


// ── Types ──────────────────────────────────────────────────────
interface SwitchOption {
  value: string;
  label: string;
  key: string;
}

interface TopologyEditorProps {
  switchCategoryId?: string;
}

const nodeTypeOptions = [
  ['channel_emulator','信道仿真器'],['communication_tester','基站仿真器'],['emcenter','射频开关及功放'],
  ['probe','测试探头'],['reference_antenna','校准参考天线'],['signal_analyzer','校准分析仪'],['vna','矢量网络分析仪'],
  ['pad','衰减器'],['amplifier','功放'],['combiner','合路器'],['cable','线缆'],['receive_cable','校准接收线缆'],['air_path','校准空气传播段'],['termination','负载'],
].map(([value,label])=>({value,label}));

// ── Inner: ReactFlow canvas with editing ────────────────────────

interface TopologyFlowProps {
  topology: SwitchTopology;
  labProfileId: string;
  onTopologyUpdated: (t: SwitchTopology) => void;
  /** P1-57：dirty 状态上报给外层，用于注册 LabProfile 切换阻断。 */
  onDirtyChange: (dirty: boolean) => void;
  onBusyChange: (busy:boolean)=>void;
}

const TopologyFlow = ({ topology, labProfileId, onTopologyUpdated, onDirtyChange, onBusyChange }: TopologyFlowProps) => {
  const { screenToFlowPosition, setCenter } = useReactFlow();
  const [activeMode, setActiveMode] = useState<string>(
    topology.operating_modes.length > 0 ? topology.operating_modes[0].id : ''
  );
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<'idle' | 'saved' | 'failed'>('idle');
  const { beginWork } = useOperationalLab();
  const [selectedEdge, setSelectedEdge] = useState<TopologyConnection | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [draft, setDraft] = useState(topology);
  const [numericDeclarations,setNumericDeclarations]=useState<ConnectionNumericDeclarations>({});
  const [edgeNumericDeclarations,setEdgeNumericDeclarations]=useState<ConnectionNumericField[]>([]);
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [nodeDrawerOpen, setNodeDrawerOpen] = useState(false);
  const [newNodeType, setNewNodeType] = useState<string>('pad');
  const [portText, setPortText] = useState('');
  const [nodeNominalValid,setNodeNominalValid]=useState(true);
  const [edgeNominalValid,setEdgeNominalValid]=useState(true);
  const [cableNominalValid,setCableNominalValid]=useState(true);
  const [selectedConnectionId,setSelectedConnectionId]=useState<string|null>(null);
  const [catalog, setCatalog] = useState<{value:string;label:string}[]>([]);
  const savingRef = useRef(false);
  const collectionBusyRef=useRef(false);
  const [collectionBusy,setCollectionBusy]=useState(false);
  const [highlightedRoute,setHighlightedRoute]=useState<RouteSelection|null>(null);
  const editingBlocked=saving||collectionBusy;
  const handleCollectionBusy=useCallback((busy:boolean)=>{
    collectionBusyRef.current=busy;setCollectionBusy(busy);onBusyChange(busy);
    if(busy){setDrawerOpen(false);setNodeDrawerOpen(false);setEdgeNumericDeclarations([]);}
  },[onBusyChange]);
  const handleRunningRoute=useCallback((route:RouteSelection)=>{
    if(route.lab_profile_id===labProfileId && route.topology_id===topology.id){setActiveMode(route.operating_mode);setHighlightedRoute(routeGraphMatchesSaved(topology,route)?route:null)}
  },[labProfileId,topology]);

  useEffect(() => {
    apiClient.get('/instruments/catalog').then(response => {
      setCatalog((response.data.categories || []).map((item: any) => ({value:item.categoryId || item.key,label:item.label})));
    }).catch(() => setCatalog([]));
  }, []);

  // Reset refs when topology prop changes (e.g. after save refresh)
  useEffect(() => {
    setDraft(topology);
    setDirty(false);
    setSaveResult('idle');
    setNumericDeclarations({});
    setEdgeNumericDeclarations([]);
    setDrawerOpen(false);
    setSelectedEdge(null);
    setSelectedConnectionId(null);
  }, [topology.id,labProfileId]);

  // P1-57：dirty 变化上报外层（含卸载复位）—— 外层据此阻断 LabProfile 切换
  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);

  const initialNodes: Node[] = React.useMemo(() => {
    const activeConnectionIds = new Set(routeCanvasConnections(draft,activeMode,highlightedRoute));

    // Collect node IDs that have at least one active connection
    const activeNodeIds = new Set<string>();
    const located=draft.connections.find(c=>c.id===selectedConnectionId);
    if(located){activeNodeIds.add(located.source);activeNodeIds.add(located.target)}
    for (const c of draft.connections) {
      if (activeConnectionIds.has(c.id)) {
        activeNodeIds.add(c.source);
        activeNodeIds.add(c.target);
      }
    }

    return draft.nodes
      .filter((n) => {
        if(located&&(n.id===located.source||n.id===located.target))return true;
        if(highlightedRoute?.calibration_node_ids.includes(n.id)&&activeNodeIds.has(n.id))return true;
        // If node has visible_modes restriction, check if current mode is in the list
        const visibleModes = n.params?.visible_modes;
        if (visibleModes && Array.isArray(visibleModes)) {
          return visibleModes.includes(activeMode);
        }
        // Otherwise, show node if it participates in any active connection
        return activeNodeIds.has(n.id);
      })
      .map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position || { x: 0, y: 0 },
        data: { label: n.label, params: n.params },
        style:highlightedRoute?.node_ids.includes(n.id)?{outline:'3px solid var(--mantine-color-blue-5)',outlineOffset:3}:
          highlightedRoute?.calibration_node_ids.includes(n.id)?{outline:'3px solid var(--mantine-color-orange-5)',outlineOffset:3}:undefined,
      }));
  }, [draft, activeMode, highlightedRoute, selectedConnectionId]);

  const initialEdges: Edge[] = React.useMemo(() => {
    const activeConnectionIds = new Set(routeCanvasConnections(draft,activeMode,highlightedRoute));

    return draft.connections
      .filter((c) => activeConnectionIds.has(c.id)||c.id===selectedConnectionId)
      .map((c) => {
      return {
        id: c.id,
        source: c.source,
        sourceHandle: c.source_pin,
        target: c.target,
        targetHandle: c.target_pin,
        type: 'signal',
        data: { 
          cable_loss_db: c.cable_loss_db,
          calibrated_loss_db: c.calibrated_loss_db,
          pa_gain_db: c.pa_gain_db,
          direction: c.direction,
        },
        animated: true,
        selected:selectedConnectionId===c.id,
        style:selectedConnectionId===c.id?{filter:'drop-shadow(0 0 5px var(--mantine-color-yellow-5))'}:
          highlightedRoute?.connection_ids.includes(c.id)?{filter:'drop-shadow(0 0 5px var(--mantine-color-blue-5))'}:
          highlightedRoute?.calibration_connection_ids.includes(c.id)?{filter:'drop-shadow(0 0 5px var(--mantine-color-orange-5))'}:undefined,
        markerEnd: { 
          type: MarkerType.ArrowClosed, 
          color: c.direction === 'UL' ? '#D946EF' : (c.calibrated_loss_db != null ? '#10B981' :
            (typeof c.pa_gain_db === 'number' && Number.isFinite(c.pa_gain_db) ? '#F59E0B' : '#3B82F6'))
        },
      };
    });
  }, [draft, activeMode, highlightedRoute, selectedConnectionId]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const openNode = (id: string) => {
    if (savingRef.current || collectionBusyRef.current) return;
    const item=draft.nodes.find(node=>node.id===id);
    if (item) {
      setSelectedNode({...item,params:{...item.params}});
      setNodeNominalValid(true);
      setPortText(getNodePorts(item).join(', '));
      setNodeDrawerOpen(true);
    }
  };

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const changeDraft = useCallback((change: (current: SwitchTopology) => SwitchTopology): boolean => {
    if (savingRef.current || collectionBusyRef.current) return false;
    try {
      const next = change(draft);
      setDraft(next);
      setNumericDeclarations(current=>topologyUpdatePayload(next,current).connection_numeric_declarations??{});
      setDirty(true);
      setSaveResult('idle');
      return true;
    } catch (error) {
      notifications.show({color:'red',message:String(error)});
      return false;
    }
  }, [draft]);
  const onConnect = useCallback((params: Connection) => {
    if (savingRef.current || collectionBusyRef.current) return;
    try {
      const next = addDraftConnection(draft, {id:crypto.randomUUID(),source:params.source,target:params.target,
        source_pin:params.sourceHandle || undefined,target_pin:params.targetHandle || undefined}, activeMode);
      changeDraft(() => next);
    } catch (error) {
      notifications.show({color:'red',message:String(error)});
    }
  }, [draft, activeMode, changeDraft]);

  const deleteNodes = useCallback((ids: string[]) => {
    if (savingRef.current || collectionBusyRef.current) return;
    const count = draft.connections.filter(c=>ids.includes(c.source)||ids.includes(c.target)).length;
    if (window.confirm(`删除 ${ids.length} 个拓扑器件及 ${count} 条关联连线？不会删除仪器资源或历史记录。`)) {
      if (changeDraft(current=>removeDraftNodes(current,ids))) setNodeDrawerOpen(false);
    }
  }, [draft, changeDraft]);

  // ── Node drag → update position in ref, mark dirty ──
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    if (savingRef.current || collectionBusyRef.current) return;
    const removed = changes.filter(c=>c.type==='remove').map(c=>c.id);
    if (removed.length) deleteNodes(removed);
    onNodesChange(changes.filter(c=>c.type!=='remove'));
    // 同一事件的多节点位置一次应用，避免事件层计算覆盖同批其他节点。
    const positions = new Map(changes.flatMap(change=>
      change.type==='position' && change.position && !change.dragging ? [[change.id,{...change.position}] as const] : []));
    if (positions.size) changeDraft(current=>({...current,nodes:current.nodes.map(node=>
      positions.has(node.id)?{...node,position:positions.get(node.id)!}:node)}));
  }, [onNodesChange, deleteNodes, changeDraft]);

  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    if (savingRef.current || collectionBusyRef.current) return;
    const removed = changes.filter(c=>c.type==='remove').map(c=>c.id);
    if (removed.length) changeDraft(current=>removeDraftConnections(current,removed));
    onEdgesChange(changes.filter(c=>c.type!=='remove'));
  }, [onEdgesChange, changeDraft]);

  // ── Edge click → open parameter drawer ──
  const openConnection = useCallback((id: string) => {
    if (savingRef.current || collectionBusyRef.current) return;
    const conn = draft.connections.find(c => c.id === id);
    if (conn) {
      setSelectedEdge({ ...conn });
      setSelectedConnectionId(id);
      setEdgeNominalValid(true);setCableNominalValid(true);
      setEdgeNumericDeclarations([]);
      setDrawerOpen(true);
    }
  }, [draft]);
  const handleEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => openConnection(edge.id),[openConnection]);

  // ── Update connection parameter ──
  const updateConnectionParam = useCallback((field: keyof TopologyConnection, value: any) => {
    if (!selectedEdge || savingRef.current || collectionBusyRef.current) return;
    setSelectedEdge(prev => prev ? { ...prev, [field]: value } : null);
    if(field==='cable_loss_db'||field==='cable_length_m') {
      setEdgeNumericDeclarations(current=>[...new Set([...current,field])]);
    }
  }, [selectedEdge]);

  const applyConnectionEdit = useCallback(() => {
    if (!selectedEdge || !edgeNominalValid || !cableNominalValid) return;
    if (changeDraft(current=>updateDraftConnection(current,selectedEdge))) {
      setNumericDeclarations(current=>mergeConnectionDeclarations(current,selectedEdge.id,edgeNumericDeclarations));
      setEdgeNumericDeclarations([]);
      setDrawerOpen(false);
      notifications.show({
        message: `连线 ${selectedEdge.id} 参数已更新`,
        color: 'blue',
        autoClose: 2000,
      });
    }
  }, [selectedEdge, changeDraft, edgeNumericDeclarations, edgeNominalValid, cableNominalValid]);

  // ── Save: validate then PATCH ──
  const handleSave = useCallback(async () => {
    if (!topology.id || savingRef.current || collectionBusyRef.current) return;
    savingRef.current = true;
    setSaving(true);
    const release = beginWork('topology-save', '拓扑保存尚未结束');

    try {
      // 2. Build update payload with current positions + edited connections.
      // P1-57：不再提交 chamber_id —— 暗室由后端从 lab_profile_id 派生，
      // 客户端提交只会造出"写进错暗室"的口子。
      // 实际拖动已经写入draft，ReactFlow的视图默认位置不得反写。
      const payload = topologyUpdatePayload(draft,numericDeclarations);

      // 3. PATCH to backend
      const updated = await switchTopologyService.updateTopology(topology.id, labProfileId, payload);
      setDraft(updated);
      setNumericDeclarations({});
      setEdgeNumericDeclarations([]);
      setDirty(false);
      setSaveResult('saved');
      onTopologyUpdated(updated);

      notifications.show({
        title: '保存成功',
        message: `拓扑 "${topology.name}" 已保存`,
        color: 'green',
        icon: <IconCheck size={16} />,
        autoClose: 3000,
      });
      logFrontendEvent({
        action: 'switch_topology.saved',
        component: 'TopologyEditor',
        message: `topology=${topology.id} lab=${labProfileId} nodes=${draft.nodes.length} conns=${draft.connections.length}`,
      });
    } catch (err: any) {
      setSaveResult('failed');
      const detail = err.response?.data?.detail || err.message;
      notifications.show({
        title: '保存失败',
        message: typeof detail === 'string' ? detail : JSON.stringify(detail),
        color: 'red',
        icon: <IconX size={16} />,
        autoClose: 5000,
      });
      logFrontendEvent({
        level: 'ERROR',
        action: 'switch_topology.save_failed',
        component: 'TopologyEditor',
        error: typeof detail === 'string' ? detail : JSON.stringify(detail),
      });
    } finally {
      setSaving(false);
      savingRef.current = false;
      release();
    }
  }, [topology, draft, numericDeclarations, onTopologyUpdated, labProfileId, beginWork]);

  const activeModeObj = draft.operating_modes.find(m => m.id === activeMode);
  const addNode = () => {
    if (savingRef.current || collectionBusyRef.current) return;
    const calibrationOnly = ['reference_antenna','signal_analyzer','air_path','receive_cable'].includes(newNodeType);
    const mode = calibrationOnly ? CALIBRATION_MODE : activeMode || 'mimo_ota';
    let current = draft;
    if (!current.operating_modes.some(m=>m.id===mode)) current = {...current,operating_modes:[...current.operating_modes,{id:mode,name:mode===CALIBRATION_MODE?'校准接线':'MIMO OTA 测试',active_connections:[]}]};
    const node: TopologyNode = {id:crypto.randomUUID(),type:newNodeType,label:nodeTypeOptions.find(o=>o.value===newNodeType)?.label || '器件',
      position:screenToFlowPosition({x:window.innerWidth/2,y:window.innerHeight/2}),
      params:{ports:[],...(calibrationOnly?{connection_scope:'calibration'}:{})}};
    const next = addDraftNode(current,node,mode);
    if (!changeDraft(()=>next)) return;
    setActiveMode(mode);
    setSelectedNode(next.nodes[next.nodes.length-1]);
    setNodeNominalValid(true);
    setPortText(suggestedPassivePorts(newNodeType).join(', '));
    setNodeDrawerOpen(true);
    void setCenter(node.position.x+90,node.position.y+40,{zoom:1,duration:200});
  };
  const applyNodeEdit = () => {
    if (!selectedNode || !nodeNominalValid || savingRef.current || collectionBusyRef.current) return;
    const ports = portText.split(/[,，\n]/).map(p=>p.trim()).filter(Boolean);
    if (!selectedNode.label.trim() || !ports.length || new Set(ports).size!==ports.length) {
      notifications.show({color:'red',message:'请填写器件名称，以及不重复的端口名称'}); return;
    }
    try {
      let editedNode=selectedNode;
      if(selectedNode.type==='probe'){
        const previous=draft.nodes.find(node=>node.id===selectedNode.id);
        if(previous?.params.rf_path_selection && !selectedNode.params.rf_path_selection &&
          !window.confirm('取消显式RF路径声明后，将恢复服务器唯一链解析；这可能改变所选通路')) return;
        if(selectedNode.params.rf_path_selection){
          const declaration=selectedNode.params.rf_path_selection;
          editedNode={...selectedNode,params:{...selectedNode.params,
            rf_path_selection:probePathDeclaration(draft,selectedNode.id,declaration.connection_ids,declaration.switch_mappings)}};
        }
      }
      const next=updateDraftNode(draft,editedNode,ports);
      if (changeDraft(()=>next)) setNodeDrawerOpen(false);
    } catch(error) { notifications.show({color:'red',message:String(error)}); }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <Paper p="sm" withBorder style={{ borderBottom: 'none', borderBottomLeftRadius: 0, borderBottomRightRadius: 0 }}>
        <Text size="sm" data-testid="topology-save-stage">
          {saving ? '正在校验并保存拓扑' : saveResult === 'failed' ? '拓扑保存失败；草稿未保存'
            : dirty ? '拓扑草稿未保存' : saveResult === 'saved' ? '拓扑已保存到服务器；不自动同步仪器绑定'
            : '拓扑编辑器无未保存改动'}
        </Text>
        <Text size="xs" c="dimmed">
          插入线缆：添加并核对A/B → 拖两条新边 → 探头属性按CE→探头重声明完整路径 → 删除旧边 → 保存后重新选择服务器路径。
          旧边校准值不自动复制；改端口名请先加新端口、建替代边、重声明、删旧边，再删旧端口。
        </Text>
        <Select aria-label="含旧PA标称的连线" placeholder="含旧PA标称的连线（含隐藏及非当前模式）" searchable value={null}
          disabled={editingBlocked} onChange={id=>id&&openConnection(id)}
          data={draft.connections.filter(c=>c.pa_gain_db!==null&&c.pa_gain_db!==undefined).map(c=>({value:c.id,
            label:`${c.id} · ${draft.nodes.find(n=>n.id===c.source)?.label??c.source}:${c.source_pin??'?'} → ${draft.nodes.find(n=>n.id===c.target)?.label??c.target}:${c.target_pin??'?'} · 模式：${draft.operating_modes.filter(m=>getDraftModeConnectionIds(draft,m.id).includes(c.id)).map(m=>m.name).join('、')||'未纳入模式'}`}))}/>
        <Group justify="space-between">
          <Group>
            <Text fw={600}>{topology.name}</Text>
            <Badge color="blue" variant="light">{topology.total_channels ?? 0} Channels</Badge>
            <Badge color={topology.is_active ? 'green' : 'gray'} variant="light">
              {topology.is_active ? '已激活' : '草稿'}
            </Badge>
            {dirty && (
              <Badge color="yellow" variant="filled" size="sm">● 未保存</Badge>
            )}
          </Group>
          <Group>
            <Select aria-label="器件列表" placeholder="搜索全部器件（含隐藏）" searchable value={null} w={260}
              data={draft.nodes.map(node=>{
                const activeConnections=new Set(routeCanvasConnections(draft,activeMode,highlightedRoute));
                const connected=draft.connections.some(c=>activeConnections.has(c.id)&&(c.source===node.id||c.target===node.id));
                const visible=highlightedRoute?.calibration_node_ids.includes(node.id)&&connected ||
                  (Array.isArray(node.params.visible_modes)?node.params.visible_modes.includes(activeMode):connected);
                return {value:node.id,label:`${node.label} · ${node.id} · ${visible?'当前模式可见':'当前模式隐藏'}`};
              })}
              disabled={editingBlocked} onChange={id=>id&&openNode(id)} />
            <Select aria-label="新增器件类型" value={newNodeType} onChange={v=>v&&setNewNodeType(v)} data={nodeTypeOptions} disabled={editingBlocked} w={150} />
            <Button onClick={addNode} disabled={editingBlocked}>添加器件</Button>
            <Button variant="light" disabled={editingBlocked} onClick={()=>{
              if (!draft.operating_modes.some(m=>m.id===CALIBRATION_MODE)) changeDraft(current=>({...current,operating_modes:[...current.operating_modes,{id:CALIBRATION_MODE,name:'校准接线',active_connections:[]}]}));
              setActiveMode(CALIBRATION_MODE);
            }}>校准接线</Button>
            <Select 
              aria-label="操作模式"
              value={activeMode} 
              onChange={(v) => v && setActiveMode(v)}
              data={draft.operating_modes.map(m => ({ value: m.id, label: m.name }))}
              disabled={editingBlocked}
              placeholder="操作模式"
              w={200}
            />
            <Button 
              leftSection={<IconDeviceFloppy size={16} />} 
              onClick={handleSave}
              loading={saving}
              disabled={collectionBusy}
              color={dirty ? 'yellow' : 'blue'}
            >
              保存拓扑
            </Button>
          </Group>
        </Group>
      </Paper>

      <div style={{display:'flex',flex:1,minHeight:0}}>
      {/* 原可编辑画布保留；侧栏只高亮同一节点/边，不生成替代只读图。 */}
      <div style={{ flex: 1, border: '1px solid var(--mantine-color-default-border)' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={onConnect}
          onEdgeClick={handleEdgeClick}
          onNodeDoubleClick={(_,node)=>openNode(node.id)}
          nodesDraggable={!editingBlocked}
          nodesConnectable={!editingBlocked}
          deleteKeyCode={null}
          nodeTypes={customNodeTypes}
          edgeTypes={customEdgeTypes}
          fitView
          attributionPosition="bottom-right"
        >
          <Background color="#ccc" gap={16} />
          <Controls showInteractive={!editingBlocked} />
          <MiniMap nodeStrokeWidth={3} zoomable pannable />
        </ReactFlow>
      </div>
      <aside style={{width:410,maxWidth:'45%',minWidth:300,minHeight:0}}>
        {topology.id?<RouteCalibrationPanel key={`${labProfileId}:${topology.id}`} labId={labProfileId} topologyId={topology.id}
          mode={activeMode} dirty={dirty} saving={saving} revision={JSON.stringify([topology.nodes,topology.connections,topology.operating_modes])}
          graph={topology}
          onSelectRoute={setHighlightedRoute} onRunningRoute={handleRunningRoute} onBusyChange={handleCollectionBusy}/>:<Alert>请先保存拓扑再读取完整路径。</Alert>}
      </aside>
      </div>
      
      {/* Status bar */}
      <Paper p="xs" withBorder style={{ borderTop: 'none', borderTopLeftRadius: 0, borderTopRightRadius: 0, backgroundColor: 'var(--mantine-color-gray-0)' }}>
        <Group justify="space-between">
          <Text size="sm" c="dimmed">{activeModeObj?.description || '—'}</Text>
          <Group gap="md">
            <Text size="xs" c="dimmed">
              节点: {draft.nodes.length} · 连接: {draft.connections.length}
            </Text>
            <Text size="xs" c="dimmed">双击器件编辑属性；点击连线编辑或删除。声明接线不代表硬件已连接或支持自动控制。</Text>
          </Group>
        </Group>
      </Paper>

      <Drawer opened={nodeDrawerOpen} onClose={()=>!saving&&setNodeDrawerOpen(false)} title="器件属性" position="right">
        {nodeDrawerOpen && selectedNode && <Stack>
          <Text size="xs" c="dimmed">{selectedNode.id}</Text>
          <TextInput label="器件名称" value={selectedNode.label} disabled={editingBlocked} onChange={event=>setSelectedNode({...selectedNode,label:event.currentTarget.value})} />
          <TextInput label="声明端口" description="用逗号分隔，须按实际接线核对；不是设备能力证明。端口仍有连线时不能移除。" value={portText} disabled={editingBlocked} onChange={event=>setPortText(event.currentTarget.value)} />
          {['cable','receive_cable'].includes(selectedNode.type)&&<Text size="xs">A/B是同一物理线缆两端，可按实际名称修改；须点击应用才成为端口声明。损耗仅在相邻连线编辑，不在器件重复计入。</Text>}
          <NominalPropertyFields key={selectedNode.id} fields={nominalFieldsForNode(selectedNode.type)} values={selectedNode.params}
            metadata={selectedNode.params.nominal_metadata} disabled={editingBlocked} onValidityChange={setNodeNominalValid}
            onChange={(key,value,metadata)=>{if(!savingRef.current&&!collectionBusyRef.current)setSelectedNode(current=>current?setNodeNominal(current,key,value,metadata):null)}}/>
          <Text size="xs" c="dimmed">数值修改可能触发原通路一致性复核；保存标称不等于采用校准。</Text>
          <Text size="xs">画布左为连入、右为连出，同名左右接点是同一个物理端口，不是两根线。</Text>
          <MultiSelect label="显示模式" data={draft.operating_modes.map(m=>({value:m.id,label:m.name}))} value={selectedNode.params.visible_modes || draft.operating_modes.map(m=>m.id)} disabled={editingBlocked || selectedNode.params.connection_scope==='calibration'} onChange={value=>setSelectedNode({...selectedNode,params:{...selectedNode.params,visible_modes:value}})} />
          {selectedNode.params.connection_scope==='calibration'&&
            (draft.operating_modes.some(mode=>mode.id===CALIBRATION_MODE)?
              <Button variant="light" disabled={editingBlocked} onClick={()=>setSelectedNode({...selectedNode,params:{...selectedNode.params,visible_modes:[CALIBRATION_MODE]}})}>恢复到校准接线模式</Button>:
              <Alert color="yellow">请先关闭抽屉，点击“校准接线”创建模式，再从器件列表重新打开；不会自动加入正常模式。</Alert>)}
          {['channel_emulator','communication_tester','emcenter','signal_analyzer','vna','ce_port','bse_port','switch_slot'].includes(selectedNode.type) && <Select label="仪器目录关联" description="仅引用已有目录；不修改地址或驱动，也不代表已经绑定或连接。" data={catalog} value={selectedNode.params.instrument_category_id || null} disabled={editingBlocked} clearable onChange={value=>setSelectedNode({...selectedNode,params:{...selectedNode.params,instrument_category_id:value}})} />}
          {selectedNode.type==='switch_slot'&&<Text size="xs">须关联本图开关类别{draft.switch_category_id}。物理port_maps在原仪器管理→射频开关→端口映射配置中保存；每映射须明确switch_id、relay_type、input_port、output_port及topology_input_pin/output_pin，不能按显示名称猜端口。</Text>}
          {selectedNode.type==='probe'&&<Stack gap="xs">
            <NumberInput label="探头编号（从0开始）" min={0} allowDecimal={false} value={selectedNode.params.probe_id??''} disabled={editingBlocked} onChange={value=>setSelectedNode({...selectedNode,params:{...selectedNode.params,probe_id:value}})}/>
            <Select label="探头极化" data={['V','H']} value={selectedNode.params.polarization??null} disabled={editingBlocked} onChange={value=>setSelectedNode({...selectedNode,params:{...selectedNode.params,polarization:value}})}/>
            <MultiSelect label="显式RF路径：按CE→探头顺序选择连线" description="选择顺序就是保存顺序；需调整顺序时先移除再选。空选保留旧式唯一链解析。" disabled={editingBlocked}
              value={selectedNode.params.rf_path_selection?.connection_ids??[]}
              data={draft.connections.filter(c=>getDraftModeConnectionIds(draft,activeMode).includes(c.id)).map(c=>({value:c.id,label:`${c.id} · ${c.source}:${c.source_pin??'?'} → ${c.target}:${c.target_pin??'?'}`}))}
              onChange={value=>{const params={...selectedNode.params};if(!value.length)delete params.rf_path_selection;else params.rf_path_selection={connection_ids:value,
                switch_mappings:(params.rf_path_selection?.switch_mappings??[]).filter((m:{node_id:string})=>draft.connections.some(c=>value.includes(c.id)&&(c.source===m.node_id||c.target===m.node_id)))};setSelectedNode({...selectedNode,params})}}/>
            <Text size="xs">保存顺序：{selectedNode.params.rf_path_selection?.connection_ids.join(' → ')||'未声明，仅服务器唯一链解析'}</Text>
            {draft.nodes.filter(n=>n.type==='switch_slot'&&draft.connections.some(c=>selectedNode.params.rf_path_selection?.connection_ids.includes(c.id)&&(c.source===n.id||c.target===n.id))).map(node=><TextInput key={node.id}
              label={`开关映射名 ${node.id}`} description="对应port_maps中的精确键，不是端口显示名。" disabled={editingBlocked}
              value={selectedNode.params.rf_path_selection.switch_mappings.find((m:{node_id:string})=>m.node_id===node.id)?.path_name??''}
              onChange={e=>{const declaration=selectedNode.params.rf_path_selection;setSelectedNode({...selectedNode,params:{...selectedNode.params,rf_path_selection:{...declaration,
                switch_mappings:[...declaration.switch_mappings.filter((m:{node_id:string})=>m.node_id!==node.id),{node_id:node.id,path_name:e.currentTarget.value}]}}})}}/>)}
          </Stack>}
          <Alert color="blue">此处只声明拓扑接线。自动控制和正式校准资格由采集入口另行核验。</Alert>
          <Group><Button onClick={applyNodeEdit} disabled={editingBlocked||!nodeNominalValid}>应用器件修改</Button><Button color="red" variant="outline" disabled={editingBlocked} onClick={()=>deleteNodes([selectedNode.id])}>删除器件</Button></Group>
        </Stack>}
      </Drawer>

      {/* ── Edge Parameter Drawer ── */}
      <Drawer
        opened={drawerOpen}
        onClose={() => {setDrawerOpen(false);setEdgeNumericDeclarations([]);}}
        title="连线参数编辑"
        position="right"
        size="sm"
        padding="lg"
      >
        {drawerOpen && selectedEdge && (() => {
          const sourceNode = draft.nodes.find((n) => n.id === selectedEdge.source);
          const targetNode = draft.nodes.find((n) => n.id === selectedEdge.target);
          const sourcePinOpts = nodePortsToSelectOptions(sourceNode);
          const targetPinOpts = nodePortsToSelectOptions(targetNode);
          return (
          <Stack gap="md">
            <Paper withBorder p="sm" radius="md" bg="gray.0">
              <Group gap="xs" mb="xs">
                <IconCircleDot size={14} />
                <Text size="sm" fw={600}>连线标识</Text>
              </Group>
              <Text size="xs" c="dimmed" style={{ wordBreak: 'break-all' }}>{selectedEdge.id}</Text>
              <Text size="xs">所属模式：{draft.operating_modes.filter(m=>getDraftModeConnectionIds(draft,m.id).includes(selectedEdge.id)).map(m=>m.name).join('、')||'未纳入模式'}；{getDraftModeConnectionIds(draft,activeMode).includes(selectedEdge.id)?'当前模式连线':'当前模式隐藏连线（未切换模式）'}</Text>
              <Group gap="lg" mt="xs">
                <Text size="xs"><b>源:</b> {sourceNode?.label || selectedEdge.source}</Text>
                <Text size="xs"><b>目标:</b> {targetNode?.label || selectedEdge.target}</Text>
              </Group>
            </Paper>

            <Divider label="端口绑定 (可编辑)" labelPosition="center" />

            {/* P1: pin Selects driven by node-port helper. Operators picked
                arbitrary strings before, which silently broke downstream SCPI
                routing. Restricting to the node's known port set catches
                typos at edit time. */}
            <Select
              label="源端口"
              description={sourceNode ? `节点 ${sourceNode.type}` : '未知节点'}
              data={sourcePinOpts}
              value={selectedEdge.source_pin || null}
              onChange={(v) => updateConnectionParam('source_pin', v || '')}
              searchable
              allowDeselect={false}
              disabled={editingBlocked}
            />
            <Select
              label="目标端口"
              description={targetNode ? `节点 ${targetNode.type}` : '未知节点'}
              data={targetPinOpts}
              value={selectedEdge.target_pin || null}
              onChange={(v) => updateConnectionParam('target_pin', v || '')}
              searchable
              allowDeselect={false}
              disabled={editingBlocked}
            />

            <Divider label="电缆参数 (可编辑)" labelPosition="center" />
            <Text size="xs">线缆节点不另计损耗；同一物理线缆的损耗只填一条相邻连线，另一条保持0。整条实测校准在校准面板采用，不填此处。</Text>

            <TextInput
              label="电缆类型"
              value={selectedEdge.cable_type || ''}
              disabled={editingBlocked}
              onChange={(e) => updateConnectionParam('cable_type', e.currentTarget.value)}
            />
            <NumberInput
              label="标称电缆损耗 (dB)"
              value={selectedEdge.cable_loss_db ?? 0}
              disabled={editingBlocked}
              onChange={(val) => updateConnectionParam('cable_loss_db', val)}
              decimalScale={2}
              step={0.1}
              min={0}
              max={30}
            />
            <NumberInput
              label="电缆长度 (m)"
              value={selectedEdge.cable_length_m ?? 0}
              disabled={editingBlocked}
              onChange={(val) => updateConnectionParam('cable_length_m', val)}
              decimalScale={1}
              step={0.5}
              min={0}
              max={50}
            />

            <NominalPropertyFields key={`cable-${selectedEdge.id}`} fields={cableNominalFields} values={selectedEdge as unknown as Record<string,unknown>}
              metadata={selectedEdge.nominal_metadata} disabled={editingBlocked} metadataOnly onValidityChange={setCableNominalValid}
              onChange={(key,value,metadata)=>{if(!savingRef.current&&!collectionBusyRef.current)setSelectedEdge(current=>{
                if(!current)return null;const updated=setEdgeNominal(current,key,value,metadata);
                // 来源编辑不声明新电缆数值，特别是存量参考边的缺键。
                if(Object.hasOwn(current,key))return {...updated,[key]:current[key as keyof TopologyConnection]};
                delete (updated as any)[key];return updated;
              })}}/>
            <NominalPropertyFields key={`pa-${selectedEdge.id}`} fields={edgeNominalFields} values={selectedEdge as unknown as Record<string,unknown>}
              metadata={selectedEdge.nominal_metadata} disabled={editingBlocked} onValidityChange={setEdgeNominalValid}
              onChange={(key,value,metadata)=>{if(!savingRef.current&&!collectionBusyRef.current)setSelectedEdge(current=>current?setEdgeNominal(current,key,value,metadata):null)}}/>
            <Text size="xs" c="dimmed">旧PA按精确边ID定位，不自动创建PA器件或切换模式。标称净值仅供显示，非实测；保存标称不等于采用校准，数值修改可能触发原通路一致性复核。</Text>
            <Divider label="校准数据 (只读)" labelPosition="center" />

            <TextInput
              label="校准损耗 (dB)"
              value={selectedEdge.calibrated_loss_db != null ? String(selectedEdge.calibrated_loss_db) : '未校准'}
              readOnly
              disabled={editingBlocked}
              styles={{ input: { backgroundColor: 'var(--mantine-color-gray-1)', cursor: 'not-allowed' } }}
            />
            <TextInput
              label="校准相位 (°)"
              value={selectedEdge.calibrated_phase_deg != null ? String(selectedEdge.calibrated_phase_deg) : '未校准'}
              readOnly
              disabled={editingBlocked}
              styles={{ input: { backgroundColor: 'var(--mantine-color-gray-1)', cursor: 'not-allowed' } }}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="outline" onClick={() => {setDrawerOpen(false);setEdgeNumericDeclarations([]);}}>取消</Button>
              <Button color="red" variant="outline" disabled={editingBlocked} onClick={()=>{if(changeDraft(current=>removeDraftConnections(current,[selectedEdge.id])))setDrawerOpen(false);}}>删除连线</Button>
              <Button onClick={applyConnectionEdit} disabled={editingBlocked||!edgeNominalValid||!cableNominalValid}>应用修改</Button>
            </Group>
          </Stack>
          );
        })()}
      </Drawer>
    </div>
  );
};


// ── Outer: self-contained page component ────────────────────────

export const TopologyEditor = ({ switchCategoryId: initialId }: TopologyEditorProps) => {
  const [availableSwitches, setAvailableSwitches] = useState<SwitchOption[]>([]);
  const [selectedSwitchId, setSelectedSwitchId] = useState<string>(initialId || '');
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  // P1-57：暗室不再由本页选择 —— 唯一真值 = 全局 LabProfile → 派生暗室。
  // 想编辑另一个暗室的拓扑，先在顶部切到绑定它的 LabProfile。
  const { selectedLabProfileId: labProfileId, chamberId, chamberName } = useOperationalLab();

  // dirty 时阻断 LabProfile 切换（未保存的接线不能静默丢，也绝不自动改绑）
  const [flowDirty, setFlowDirty] = useState(false);
  const [flowBusy,setFlowBusy]=useState(false);
  useOperationalLabSwitchGuard(
    'topology-editor',
    flowBusy?'拓扑通路采集尚未确认结束；请先查看或取消采集':flowDirty ? '拓扑编辑器有未保存的改动 —— 请先保存或放弃再切换 LabProfile' : null,
  );

  const [topology, setTopology] = useState<SwitchTopology | null>(null);
  const [topoLoading, setTopoLoading] = useState(false);
  const [topoError, setTopoError] = useState<string | null>(null);
  const [reimporting, setReimporting] = useState(false);

  // List of topology templates available on this deployment. `null` while
  // we're still asking the backend; `[]` on a commercial image where
  // .dockerignore excluded scripts/dev-fixtures/. Loaded once per mount —
  // the registry is filesystem-backed and doesn't change at runtime.
  const [availableTemplates, setAvailableTemplates] = useState<string[] | null>(null);

  useEffect(() => {
    switchTopologyService.listTemplates()
      .then(setAvailableTemplates)
      .catch(() => setAvailableTemplates([]));  // treat fetch failure as "none"
  }, []);

  // Pick the default template to auto-import: prefer 'caict_v4' if it ships;
  // otherwise the first one. Returns null when no templates available — the
  // editor then falls through to the build-from-scratch empty state instead
  // of crashing on a 404.
  const pickDefaultTemplate = useCallback((): string | null => {
    if (!availableTemplates || availableTemplates.length === 0) return null;
    if (availableTemplates.includes('caict_v4')) return 'caict_v4';
    return availableTemplates[0];
  }, [availableTemplates]);

  // P1-57 重导入：单次调用，replace_existing 由服务端处理 ——
  // lab/暗室/模板完整解析成功之后才删同 (switch, 派生暗室) 的旧行。
  // （原先是客户端先删后导：解析失败时行已经白白没了。）
  const handleReimport = useCallback(async () => {
    if (!selectedSwitchId || !labProfileId) return;
    const templateId = pickDefaultTemplate();
    if (!templateId) {
      notifications.show({
        title: '本部署没有可用拓扑模板',
        message: '当前镜像不带 dev-fixture 模板。直接在编辑器里搭拓扑然后保存。',
        color: 'blue',
        icon: <IconAlertTriangle size={16} />,
      });
      return;
    }
    setReimporting(true);
    try {
      const imported = await switchTopologyService.importFromTemplate(
        selectedSwitchId,
        labProfileId,
        templateId,
        true,
      );
      setTopology(imported);
      notifications.show({
        title: '拓扑已更新',
        message: `已导入 V4.0 拓扑: ${imported.name}`,
        color: 'green',
        icon: <IconCheck size={16} />,
        autoClose: 3000,
      });
      logFrontendEvent({
        action: 'switch_topology.reimported',
        component: 'TopologyEditor',
        message: `switch=${selectedSwitchId} lab=${labProfileId} topology=${imported.id}`,
      });
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message;
      notifications.show({
        title: '重导入失败',
        message: typeof detail === 'string' ? detail : JSON.stringify(detail),
        color: 'red',
        icon: <IconX size={16} />,
        autoClose: 5000,
      });
    } finally {
      setReimporting(false);
    }
  }, [selectedSwitchId, labProfileId, pickDefaultTemplate]);


  // Fetch instrument catalog
  useEffect(() => {
    setCatalogLoading(true);
    setCatalogError(null);
    apiClient.get('/instruments/catalog')
      .then(res => {
        const categories = res.data?.categories || [];
        const switches: SwitchOption[] = categories
          .filter((c: any) =>
            c.key?.toLowerCase().includes('switch') ||
            c.key?.toLowerCase().includes('matrix') ||
            c.label?.includes('开关') ||
            c.label?.includes('矩阵')
          )
          .map((c: any) => ({
            value: c.categoryId || c.key,
            label: c.label,
            key: c.key,
          }));

        setAvailableSwitches(switches);
        if (switches.length > 0 && !initialId) {
          setSelectedSwitchId(switches[0].value);
        }
      })
      .catch(err => {
        console.error('Failed to fetch instrument catalog:', err);
        setCatalogError(`无法加载仪器目录: ${err.message}`);
      })
      .finally(() => setCatalogLoading(false));
  }, []);

  // Fetch chamber list (P1 — required for binding any topology).
  // P1-57：按 (switch, 全局 lab) 拉取该 lab 派生暗室的拓扑行。
  // 不再从最新 topology 行反向播种暗室 —— 那正是"编辑器自成一套暗室真值"的来源。
  // lab 切换时本 effect 重跑：先清掉旧暗室的 topology，再加载新作用域。
  useEffect(() => {
    if (!selectedSwitchId || !labProfileId) return;

    setTopoLoading(true);
    setTopoError(null);
    setTopology(null);

    switchTopologyService.getTopologies(labProfileId, selectedSwitchId)
      .then(resp => {
        const items = resp.items || (Array.isArray(resp) ? resp : []);
        if (items.length > 0) {
          setTopology(items[0]);
          return;
        }
        // The template list resolves once per mount via a separate effect.
        // If it hasn't arrived yet, defer — this effect will re-fire when
        // `availableTemplates` flips from null to a value.
        if (availableTemplates === null) return;

        const templateId = pickDefaultTemplate();
        if (!templateId) {
          // Commercial deploy: .dockerignore excluded scripts/dev-fixtures/
          // so the backend reports an empty template registry. Leave
          // topology=null; the canvas falls through to the "尚无拓扑配置"
          // empty state, and the operator builds wiring from scratch +
          // saves via POST /switch-topologies. No error to surface.
          return;
        }
        return switchTopologyService.importFromTemplate(
          selectedSwitchId,
          labProfileId,
          templateId,
        )
          .then(imported => setTopology(imported))
          .catch(err => {
            // Race: template list said the file was there, the import
            // says it isn't (operator deleted it, file moved, container
            // hot-reload, etc.). Fall through to scratch mode rather than
            // breaking the page with a hard error.
            if (err?.response?.status === 404) {
              console.warn('Template auto-import 404; falling through to scratch mode', err);
              return;
            }
            throw err;
          });
      })
      .catch(err => {
        console.error('Topology fetch failed:', err);
        setTopoError(`加载拓扑失败: ${err.response?.data?.detail || err.message}`);
      })
      .finally(() => setTopoLoading(false));
  }, [selectedSwitchId, labProfileId, availableTemplates, pickDefaultTemplate]);

  return (
    <Stack gap="lg" h="100%">
      {/* Switch Selector Card */}
      <Card withBorder radius="md" padding="lg">
        <Group justify="space-between" align="center">
          <Group gap="sm" align="center">
            <IconTopologyRing size={22} color="var(--mantine-color-brand-6)" />
            <Title order={4}>射频开关矩阵拓扑</Title>
          </Group>

          <Group gap="md" align="center">
            {/* P1-57：暗室不再由本页选择 —— 只读展示全局上下文派生的暗室。
                想编辑别的暗室，去顶部切 LabProfile。 */}
            {chamberName ? (
              <Badge color="brand" variant="light" size="lg">
                当前暗室：{chamberName}
              </Badge>
            ) : (
              <Badge color="orange" variant="light" size="lg">
                当前 LabProfile 未绑定暗室
              </Badge>
            )}
            {catalogLoading ? (
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="sm" c="dimmed">加载仪器目录…</Text>
              </Group>
            ) : availableSwitches.length > 0 ? (
              <Select
                label="射频开关设备"
                disabled={flowBusy}
                value={selectedSwitchId}
                onChange={(val) => val && setSelectedSwitchId(val)}
                data={availableSwitches}
                placeholder="选择射频开关设备…"
                w={260}
                required
                allowDeselect={false}
              />
            ) : (
              <Badge color="orange" variant="light" size="lg">
                未检测到射频开关设备
              </Badge>
            )}
            {topology && availableTemplates && availableTemplates.length > 0 && (
              <Button
                variant="light"
                color="orange"
                size="xs"
                leftSection={<IconRefresh size={14} />}
                loading={reimporting}
                onClick={handleReimport}
                disabled={!chamberId||flowBusy}
                title={!chamberId ? '当前 LabProfile 未绑定暗室' : undefined}
              >
                重导入默认拓扑
              </Button>
            )}
          </Group>
        </Group>

        {/* Version mismatch warning */}
        {topology && topology.version && !topology.version.includes('4.0') && (
          <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={16} />} mt="sm">
            当前拓扑版本为 {topology.version}，建议重导入以获取最新 V4.0 拓扑（修正 F64 直连 + 垂直环探头）。
          </Alert>
        )}



        {catalogError && (
          <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />} mt="sm">
            {catalogError}
          </Alert>
        )}

      </Card>

      {/* Topology Canvas Area */}
      <div style={{ height: 'calc(100vh - 250px)', minHeight: 500 }}>
        {!labProfileId ? (
          <Center h="100%">
            <Stack align="center" gap="sm">
              <IconTopologyRing size={48} color="var(--mantine-color-gray-4)" />
              <Text c="dimmed" ta="center">
                请选择当前 LabProfile。<br />
                拓扑属于 LabProfile 绑定的暗室 —— 在顶部选择后这里会加载对应接线。
              </Text>
            </Stack>
          </Center>
        ) : !chamberId ? (
          <Center h="100%">
            <Stack align="center" gap="sm">
              <IconTopologyRing size={48} color="var(--mantine-color-gray-4)" />
              <Text c="dimmed" ta="center">
                当前 LabProfile 未绑定暗室。<br />
                请到 LabProfile 管理里为它绑定暗室后再编辑拓扑。
              </Text>
            </Stack>
          </Center>
        ) : !selectedSwitchId ? (
          <Center h="100%">
            <Stack align="center" gap="sm">
              <IconTopologyRing size={48} color="var(--mantine-color-gray-4)" />
              <Text c="dimmed" ta="center">
                请先在上方选择一个射频开关设备，<br />
                或在「实验室配置 → 仪器资源」中添加 RF Switch 类别。
              </Text>
            </Stack>
          </Center>
        ) : topoLoading ? (
          <Center h="100%">
            <Stack align="center" gap="sm">
              <Loader size="lg" color="brand" />
              <Text size="sm" c="dimmed">正在加载拓扑数据…</Text>
            </Stack>
          </Center>
        ) : topoError ? (
          <Center h="100%">
            <Alert 
              color="red" 
              variant="light" 
              icon={<IconAlertCircle size={16} />}
              title="拓扑加载失败"
              maw={500}
            >
              {topoError}
            </Alert>
          </Center>
        ) : topology ? (
          <ReactFlowProvider>
            <TopologyFlow
              topology={topology}
              labProfileId={labProfileId}
              onTopologyUpdated={(updated) => setTopology(updated)}
              onDirtyChange={setFlowDirty}
              onBusyChange={setFlowBusy}
            />
          </ReactFlowProvider>
        ) : (
          <Center h="100%">
            <Text c="dimmed">此开关尚无拓扑配置。</Text>
          </Center>
        )}
      </div>
    </Stack>
  );
};
