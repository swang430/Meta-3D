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
  Modal,
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
import { customEdgeTypes, ReadOnlySignalEdge } from './CustomEdges';
import {NominalPropertyFields} from './NominalPropertyFields';
import {PortDeclarationFields} from './PortDeclarationFields';
import {InternalPathFields} from './InternalPathFields';
import {LegacyConversionPanel} from './LegacyConversionPanel';
import {TopologyHistoryPanel} from './TopologyHistoryPanel';
import {canRestore,ownsRevisionRequest,revisionFailure} from './topologyRevisionState';
import type {RevisionContext} from './topologyRevisionState';
import {validateDraftInternalPaths} from './internalPathHelpers';
import {nominalFieldsForNode, edgeNominalFields, cableNominalFields, setNodeNominal, setEdgeNominal} from './nominalProperties';
import { RouteCalibrationPanel } from './RouteCalibrationPanel';
import { routeCanvasConnections, probePathDeclaration } from './routeCalibrationState';
import { routeGraphMatchesSaved } from './routeCalibrationState';
import type { RouteSelection } from '../../types/api';
import { getNodePorts, nodePortsToSelectOptions, suggestedPassivePorts, edgePortPresentation, edgeNeedsReadOnlyGeometry } from './nodePortHelpers';
import { addDraftNode, addDraftConnection, removeDraftNodes, removeDraftConnections, updateDraftNode, updateDraftConnection, getDraftModeConnectionIds, CALIBRATION_MODE } from './topologyDraft';
import { switchTopologyService, topologyUpdatePayload, mergeConnectionDeclarations } from '../../api/switchTopologyService';
import type { SwitchTopology, TopologyConnection, TopologyNode, ConnectionNumericField, ConnectionNumericDeclarations, TopologyConversionPreview } from '../../api/switchTopologyService';
import {chooseTopology, preferenceKey, requestMatches, canLeaveTopology, loadTopologyLibrary} from './topologyLibraryState';
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
  conversionEpoch: number;
  libraryBusy: boolean;
  isLibraryBusy: () => boolean;
  onTopologyUpdated: (t: SwitchTopology) => void;
  /** P1-57：dirty 状态上报给外层，用于注册 LabProfile 切换阻断。 */
  onDirtyChange: (dirty: boolean) => void;
  onBusyChange: (busy:boolean)=>void;
}

const TopologyFlow = ({ topology, labProfileId, conversionEpoch, libraryBusy, isLibraryBusy, onTopologyUpdated, onDirtyChange, onBusyChange }: TopologyFlowProps) => {
  const { screenToFlowPosition, setCenter } = useReactFlow();
  const [activeMode, setActiveMode] = useState<string>(
    topology.operating_modes.length > 0 ? topology.operating_modes[0].id : ''
  );
  const [dirty, setDirty] = useState(false);
  const updateDirty = (value: boolean) => { onDirtyChange(value); setDirty(value); };
  const mounted = useRef(true);
  useEffect(() => { mounted.current=true; return () => {mounted.current=false;} }, []);
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
  const [portsExplicit,setPortsExplicit]=useState(false);
  const [nodeNominalValid,setNodeNominalValid]=useState(true);
  const [edgeNominalValid,setEdgeNominalValid]=useState(true);
  const [cableNominalValid,setCableNominalValid]=useState(true);
  const [selectedConnectionId,setSelectedConnectionId]=useState<string|null>(null);
  const [catalog, setCatalog] = useState<{value:string;label:string}[]>([]);
  const savingRef = useRef(false);
  const unknownWriteRef=useRef(false);
  const [unknownWrite,setUnknownWrite]=useState(false);
  const [revisionError,setRevisionError]=useState('');
  const [historyOpen,setHistoryOpen]=useState(false);
  const [latest,setLatest]=useState<SwitchTopology|null>(null);
  const [latestHistory,setLatestHistory]=useState<unknown>(null);
  const [inspecting,setInspecting]=useState(false);
  const inspectGeneration=useRef(0);
  const scope=JSON.stringify([labProfileId,topology.switch_category_id]);
  const requestGeneration=useRef(0);
  const liveRequest=useRef<RevisionContext>({scope,topologyId:topology.id??'',generation:0});
  if(liveRequest.current.scope!==scope||liveRequest.current.topologyId!==(topology.id??'')){
    liveRequest.current={scope,topologyId:topology.id??'',generation:++requestGeneration.current};
    inspectGeneration.current++;
  }
  const collectionBusyRef=useRef(false);
  const [collectionBusy,setCollectionBusy]=useState(false);
  const [conversionOpen,setConversionOpen]=useState(false);
  useEffect(()=>setConversionOpen(false),[conversionEpoch]);
  const [highlightedRoute,setHighlightedRoute]=useState<RouteSelection|null>(null);
  const editingBlocked=saving||collectionBusy||libraryBusy||unknownWrite;
  const isWriteBlocked=()=>savingRef.current||collectionBusyRef.current||isLibraryBusy()||unknownWriteRef.current;
  const handleCollectionBusy=useCallback((busy:boolean)=>{
    // activeWork包含本次保存。busy始终保留为锁；仅保存期间不因回传而关闭转换丢输入。
    collectionBusyRef.current=busy;setCollectionBusy(busy);onBusyChange(busy||savingRef.current||unknownWriteRef.current);
    if(busy){setDrawerOpen(false);setNodeDrawerOpen(false);setEdgeNumericDeclarations([]);if(!savingRef.current)setConversionOpen(false);}
  },[onBusyChange]);
  const handleRunningRoute=useCallback((route:RouteSelection)=>{
    if(route.lab_profile_id===labProfileId && route.topology_id===topology.id){setActiveMode(route.operating_mode);setHighlightedRoute(routeGraphMatchesSaved(topology,route)?route:null)}
  },[labProfileId,topology]);

  useEffect(() => {
    apiClient.get('/instruments/catalog').then(response => {
      setCatalog((response.data.categories || []).map((item: any) => ({value:item.categoryId || item.key,label:item.label})));
    }).catch(() => setCatalog([]));
  }, []);

  // 只恢复当前图已知保存快照，不读取历史修订，也不发写请求。
  const resetToSaved = () => {
    setDraft(topology);
    updateDirty(false);
    setSaveResult('idle');
    setNumericDeclarations({});
    setEdgeNumericDeclarations([]);
    setDrawerOpen(false);
    setSelectedEdge(null);
    setSelectedConnectionId(null);
    setSelectedNode(null);setNodeDrawerOpen(false);setPortText('');setPortsExplicit(false);
    setHighlightedRoute(null);
    setConversionOpen(false);
    setActiveMode(current=>topology.operating_modes.some(mode=>mode.id===current)?current:topology.operating_modes[0]?.id??'');
  };
  useEffect(resetToSaved, [topology.id,labProfileId]);
  // 库改名/显式采用最新沿同一图ID回传；仅无草稿时同步保存模型，绝不换令牌重放旧草稿。
  useEffect(()=>{if(!dirty&&!saving&&!unknownWrite)setDraft(topology)},[topology,dirty,saving,unknownWrite]);

  // P1-57：dirty 变化上报外层（含卸载复位）—— 外层据此阻断 LabProfile 切换
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

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
      const portView=edgePortPresentation(draft.nodes,c);
      const marker={type:MarkerType.ArrowClosed,color:c.direction==='UL'?'#D946EF':(c.calibrated_loss_db!=null?'#10B981':
        (typeof c.pa_gain_db==='number'&&Number.isFinite(c.pa_gain_db)?'#F59E0B':'#3B82F6'))};
      return {
        id: c.id,
        source: c.source,
        sourceHandle: c.source_pin,
        target: c.target,
        targetHandle: c.target_pin,
        type: 'signal',
        data: { 
          cable_loss_db: c.cable_loss_db,
          loss_owner_connection_id: c.loss_owner_connection_id,
          calibrated_loss_db: c.calibrated_loss_db,
          pa_gain_db: c.pa_gain_db,
          direction: c.direction,
          portWarning:portView.warning,
          readOnlyGeometry:edgeNeedsReadOnlyGeometry(draft.nodes,c),
        },
        animated: true,
        selected:selectedConnectionId===c.id,
        style:selectedConnectionId===c.id?{filter:'drop-shadow(0 0 5px var(--mantine-color-yellow-5))'}:
          highlightedRoute?.connection_ids.includes(c.id)?{filter:'drop-shadow(0 0 5px var(--mantine-color-blue-5))'}:
          highlightedRoute?.calibration_connection_ids.includes(c.id)?{filter:'drop-shadow(0 0 5px var(--mantine-color-orange-5))'}:undefined,
        markerEnd:portView.arrowEnd?marker:undefined,
        markerStart:portView.arrowStart?marker:undefined,
      };
    });
  }, [draft, activeMode, highlightedRoute, selectedConnectionId]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const openNode = (id: string) => {
    if (isWriteBlocked()) return;
    const item=draft.nodes.find(node=>node.id===id);
    if (item) {
      setSelectedNode({...item,params:{...item.params}});
      setNodeNominalValid(true);
      setPortText(getNodePorts(item).join(', '));
      setPortsExplicit(false);
      setNodeDrawerOpen(true);
    }
  };

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const changeDraft = useCallback((change: (current: SwitchTopology) => SwitchTopology): boolean => {
    if (isWriteBlocked()) return false;
    try {
      const next = change(draft);
      validateDraftInternalPaths(next,draft);
      setDraft(next);
      setNumericDeclarations(current=>topologyUpdatePayload(next,current).connection_numeric_declarations??{});
      updateDirty(true);
      setSaveResult('idle');
      return true;
    } catch (error) {
      notifications.show({color:'red',message:String(error)});
      return false;
    }
  }, [draft]);
  const onConnect = useCallback((params: Connection) => {
    if (isWriteBlocked()) return;
    try {
      const next = addDraftConnection(draft, {id:crypto.randomUUID(),source:params.source,target:params.target,
        source_pin:params.sourceHandle || undefined,target_pin:params.targetHandle || undefined}, activeMode);
      changeDraft(() => next);
    } catch (error) {
      notifications.show({color:'red',message:String(error)});
    }
  }, [draft, activeMode, changeDraft]);

  const deleteNodes = useCallback((ids: string[]) => {
    if (isWriteBlocked()) return;
    const count = draft.connections.filter(c=>ids.includes(c.source)||ids.includes(c.target)).length;
    if (window.confirm(`删除 ${ids.length} 个拓扑器件及 ${count} 条关联连线？不会删除仪器资源或历史记录。`)) {
      if (changeDraft(current=>removeDraftNodes(current,ids))) setNodeDrawerOpen(false);
    }
  }, [draft, changeDraft]);

  // ── Node drag → update position in ref, mark dirty ──
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    if (isWriteBlocked()) return;
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
    if (isWriteBlocked()) return;
    const removed = changes.filter(c=>c.type==='remove').map(c=>c.id);
    if (removed.length) changeDraft(current=>removeDraftConnections(current,removed));
    onEdgesChange(changes.filter(c=>c.type!=='remove'));
  }, [onEdgesChange, changeDraft]);

  // ── Edge click → open parameter drawer ──
  const openConnection = useCallback((id: string) => {
    if (isWriteBlocked()) return;
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
    if (!selectedEdge || isWriteBlocked()) return;
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

  const ownsWrite=(ticket:RevisionContext)=>mounted.current&&ownsRevisionRequest(liveRequest.current,ticket);
  const startWrite=()=>{
    const ticket={scope,topologyId:topology.id??'',generation:++requestGeneration.current};
    liveRequest.current=ticket;inspectGeneration.current++;setInspecting(false);
    savingRef.current=true;setSaving(true);setRevisionError('');setLatest(null);onBusyChange(true);
    return ticket;
  };
  const finishWrite=(ticket:RevisionContext)=>{
    if(!ownsWrite(ticket))return;
    savingRef.current=false;setSaving(false);onBusyChange(collectionBusyRef.current||unknownWriteRef.current);
  };
  const writeFailed=(err:any,ticket:RevisionContext,writeConfirmed=false)=>{
    if(!ownsWrite(ticket))return;
    const failure=revisionFailure(writeConfirmed?undefined:err.response?.status);
    setSaveResult('failed');setRevisionError(`${failure.message} ${errorText(err)}`);
    if(failure.kind==='unknown'){
      unknownWriteRef.current=true;setUnknownWrite(true);onBusyChange(true);
    }
  };
  const adoptSaved=(current:SwitchTopology)=>{
    setDraft(current);setNumericDeclarations({});setEdgeNumericDeclarations([]);
    setSelectedNode(null);setSelectedEdge(null);setSelectedConnectionId(null);
    setDrawerOpen(false);setNodeDrawerOpen(false);setHighlightedRoute(null);
    setPortText('');setPortsExplicit(false);setConversionOpen(false);
    setActiveMode(mode=>current.operating_modes.some(item=>item.id===mode)?mode:current.operating_modes[0]?.id??'');
    updateDirty(false);onTopologyUpdated(current);
  };
  // 显式 GET 核查不借用写 ticket，不接纳令牌覆盖仍在编辑的旧草稿。
  const inspectLatest=async()=>{
    if(savingRef.current||collectionBusyRef.current||libraryBusy||!topology.id)return;
    const ticket={...liveRequest.current},read=++inspectGeneration.current;setInspecting(true);setLatest(null);setLatestHistory(null);
    try{
      const current=await switchTopologyService.getTopology(topology.id,labProfileId);
      const history=await switchTopologyService.listRevisions(topology.id,labProfileId,0,50);
      if(ownsWrite(ticket)&&read===inspectGeneration.current){setLatest(current);setLatestHistory(history)}
    }catch(err){if(ownsWrite(ticket)&&read===inspectGeneration.current)setRevisionError(`核查读取失败，原草稿和未知状态保留。 ${errorText(err)}`)}
    finally{if(ownsWrite(ticket)&&read===inspectGeneration.current)setInspecting(false)}
  };
  const adoptLatest=()=>{
    if(!latest||savingRef.current||collectionBusyRef.current||libraryBusy)return;
    adoptSaved(latest);setLatest(null);setLatestHistory(null);setRevisionError('');setSaveResult('idle');
    unknownWriteRef.current=false;setUnknownWrite(false);onBusyChange(collectionBusyRef.current||savingRef.current);
  };

  // ── Save: validate then PATCH ──
  const handleSave = useCallback(async () => {
    if (!topology.id || isWriteBlocked()) return;
    const ticket=startWrite();
    const release = beginWork('topology-save', '拓扑保存尚未结束');

    try {
      // 2. Build update payload with current positions + edited connections.
      // P1-57：不再提交 chamber_id —— 暗室由后端从 lab_profile_id 派生，
      // 客户端提交只会造出"写进错暗室"的口子。
      // 实际拖动已经写入draft，ReactFlow的视图默认位置不得反写。
      const payload = topologyUpdatePayload(draft,numericDeclarations);

      // 3. PATCH to backend
      const updated = await switchTopologyService.updateTopology(topology.id, labProfileId, payload);
      if (!ownsWrite(ticket)) return;
      setDraft(updated);
      setNumericDeclarations({});
      setEdgeNumericDeclarations([]);
      updateDirty(false);
      setHighlightedRoute(null);
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
      if (!ownsWrite(ticket)) return;
      writeFailed(err,ticket);
      const detail = err.response?.data?.detail || err.message;
      notifications.show({
        title: '保存失败',
        message: `${revisionFailure(err.response?.status).message} ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`,
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
      finishWrite(ticket);
      release();
    }
  }, [topology, draft, numericDeclarations, onTopologyUpdated, labProfileId, beginWork, onBusyChange]);

  const saveConversion=async(preview:TopologyConversionPreview)=>{
    if(isWriteBlocked()||dirty||!topology.id)return;
    const ticket=startWrite();
    const release=beginWork('topology-save','拓扑转换保存尚未结束');
    try{
      const updated=await switchTopologyService.updateTopology(topology.id,labProfileId,{expected_revision:preview.revision,conversion:{source_digest:preview.source_digest,changes:preview.changes}});
      if(!ownsWrite(ticket))return;
      // 只用已保存GET模型更新原编辑器，不使用preview.candidate替换草稿。
      setDraft(updated);setNumericDeclarations({});setEdgeNumericDeclarations([]);updateDirty(false);
      setHighlightedRoute(null);setSaveResult('saved');setConversionOpen(false);onTopologyUpdated(updated);
    }catch(err){writeFailed(err,ticket);throw err}
    finally{finishWrite(ticket);release()}
  };

  const restoreRevision=async(targetRevision:number,expectedRevision:number)=>{
    if(!topology.id||!canRestore({dirty,writing:savingRef.current||isLibraryBusy(),collectionBusy:collectionBusyRef.current,unknownWrite:unknownWriteRef.current}))return;
    const ticket=startWrite(),release=beginWork('topology-save','拓扑历史恢复尚未结束');
    let writeConfirmed=false;
    try{
      await switchTopologyService.restoreTopology(topology.id,labProfileId,targetRevision,expectedRevision);
      writeConfirmed=true;
      const current=await switchTopologyService.getTopology(topology.id,labProfileId);
      if(!ownsWrite(ticket))return;
      adoptSaved(current);setSaveResult('saved');setHistoryOpen(false);
      notifications.show({color:'green',message:`已恢复为新的保存修订 r${current.revision}；未恢复校准资格`});
    }catch(err){writeFailed(err,ticket,writeConfirmed);if(writeConfirmed)throw new Error(`恢复写入已确认，但当前详情读取失败；${errorText(err)}`);throw err}
    finally{finishWrite(ticket);release()}
  };

  const activeModeObj = draft.operating_modes.find(m => m.id === activeMode);
  const addNode = () => {
    if (isWriteBlocked()) return;
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
    setPortsExplicit(false);
    setNodeDrawerOpen(true);
    void setCenter(node.position.x+90,node.position.y+40,{zoom:1,duration:200});
  };
  const applyNodeEdit = () => {
    if (!selectedNode || !nodeNominalValid || isWriteBlocked()) return;
    const ports = portText.split(/[,，\n]/).map(p=>p.trim()).filter(Boolean);
    if (!selectedNode.label.trim() || (portsExplicit&&(!ports.length || new Set(ports).size!==ports.length))) {
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
      const next=updateDraftNode(draft,editedNode,portsExplicit?ports:undefined);
      if (changeDraft(()=>next)) setNodeDrawerOpen(false);
    } catch(error) { notifications.show({color:'red',message:String(error)}); }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <Paper p="sm" withBorder style={{ borderBottom: 'none', borderBottomLeftRadius: 0, borderBottomRightRadius: 0 }}>
        <Text size="sm" data-testid="topology-save-stage">
          {saving ? '正在校验并保存拓扑' : unknownWrite ? '保存结果未知；请显式核对服务器修订' : saveResult === 'failed' ? '拓扑保存失败；草稿未保存'
            : dirty ? '拓扑草稿未保存' : saveResult === 'saved' ? '拓扑已保存到服务器；不自动同步仪器绑定'
            : '拓扑编辑器无未保存改动'}
        </Text>
        {revisionError&&<Alert color="red" data-testid="topology-revision-error">{revisionError}</Alert>}
        <Group mt="xs"><Button variant="light" onClick={()=>setHistoryOpen(true)}>保存修订历史</Button>
          <Button variant="light" loading={inspecting} disabled={saving||collectionBusy||libraryBusy} onClick={()=>void inspectLatest()}>刷新查看服务器最新</Button></Group>
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
            <Button disabled={editingBlocked} variant="light" onClick={()=>{
              if(isWriteBlocked())return;
              setDrawerOpen(false);setNodeDrawerOpen(false);setConversionOpen(true);
            }}>转换旧配置</Button>
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
              if(isWriteBlocked())return;
              if (!draft.operating_modes.some(m=>m.id===CALIBRATION_MODE)) changeDraft(current=>({...current,operating_modes:[...current.operating_modes,{id:CALIBRATION_MODE,name:'校准接线',active_connections:[]}]}));
              setActiveMode(CALIBRATION_MODE);
            }}>校准接线</Button>
            <Select 
              aria-label="操作模式"
              value={activeMode} 
              onChange={(v) => {if(!isWriteBlocked()&&v)setActiveMode(v)}}
              data={draft.operating_modes.map(m => ({ value: m.id, label: m.name }))}
              disabled={editingBlocked}
              placeholder="操作模式"
              w={200}
            />
            <Button 
              leftSection={<IconDeviceFloppy size={16} />} 
              onClick={handleSave}
              loading={saving}
              disabled={collectionBusy||libraryBusy}
              color={dirty ? 'yellow' : 'blue'}
            >
              保存拓扑
            </Button>
            <Button variant="default" disabled={!dirty||editingBlocked} onClick={()=>{
              if(isWriteBlocked()||!dirty)return;
              if(window.confirm(`放弃当前图 ${topology.name} · ${topology.id?.slice(0,8)} 的未保存改动？仅恢复已保存快照，不写入或删除服务器图。`))resetToSaved();
            }}>放弃未保存改动</Button>
          </Group>
        </Group>
      </Paper>

      <div style={{display:'flex',flex:1,minHeight:0}}>
      {/* 原可编辑画布保留；侧栏只高亮同一节点/边，不生成替代只读图。 */}
      <div style={{ flex: 1, border: '1px solid var(--mantine-color-default-border)' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges.filter(edge=>!edge.data?.readOnlyGeometry)}
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
          {edges.filter(edge=>edge.data?.readOnlyGeometry).map(edge=><ReadOnlySignalEdge key={edge.id} edge={edge} onClick={()=>openConnection(edge.id)}/>)}
          <Background color="#ccc" gap={16} />
          <Controls showInteractive={!editingBlocked} />
          <MiniMap nodeStrokeWidth={3} zoomable pannable />
        </ReactFlow>
      </div>
      <aside style={{width:410,maxWidth:'45%',minWidth:300,minHeight:0}}>
        {topology.id?<RouteCalibrationPanel key={`${labProfileId}:${topology.id}`} labId={labProfileId} topologyId={topology.id}
          mode={activeMode} dirty={dirty} saving={saving||libraryBusy||unknownWrite} revision={JSON.stringify([topology.nodes,topology.connections,topology.operating_modes])}
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
          <PortDeclarationFields node={selectedNode} text={portText} disabled={editingBlocked}
            onTextChange={value=>{if(!isWriteBlocked())setPortText(value)}}
            onChange={delta=>{if(isWriteBlocked())return;setPortsExplicit(true);setSelectedNode(current=>current?{...current,params:{...current.params,...delta}}:null)}}
            onRestore={()=>{if(isWriteBlocked())return;const original=draft.nodes.find(n=>n.id===selectedNode.id);if(!original)return;
              const params={...selectedNode.params};for(const key of ['ports','port_directions',...(['communication_tester','bse_port'].includes(selectedNode.type)?['port_roles']:[])]){
                if(Object.hasOwn(original.params,key))params[key]=original.params[key];else delete params[key];
              }setSelectedNode({...selectedNode,params});setPortText(getNodePorts(original).join(', '));setPortsExplicit(false)}}/>
          <InternalPathFields node={selectedNode} disabled={editingBlocked}
            onChange={paths=>{if(isWriteBlocked())return;setSelectedNode(current=>current?{...current,params:{...current.params,internal_paths:paths}}:null)}}
            onRestore={()=>{if(isWriteBlocked())return;const original=draft.nodes.find(n=>n.id===selectedNode.id);if(!original)return;
              const params={...selectedNode.params};if(Object.hasOwn(original.params,'internal_paths'))params.internal_paths=original.params.internal_paths;else delete params.internal_paths;
              setSelectedNode({...selectedNode,params})}}/>
          {['cable','receive_cable'].includes(selectedNode.type)&&<Text size="xs">A/B是同一物理线缆两端，可按实际名称修改；须点击应用才成为端口声明。损耗仅在相邻连线编辑，不在器件重复计入。</Text>}
          <NominalPropertyFields key={selectedNode.id} fields={nominalFieldsForNode(selectedNode.type)} values={selectedNode.params}
            metadata={selectedNode.params.nominal_metadata} disabled={editingBlocked} onValidityChange={setNodeNominalValid}
            onChange={(key,value,metadata)=>{if(!isWriteBlocked())setSelectedNode(current=>current?setNodeNominal(current,key,value,metadata):null)}}/>
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

      <LegacyConversionPanel key={conversionEpoch} opened={conversionOpen} topology={topology} labId={labProfileId} dirty={dirty}
        blocked={editingBlocked} isBlocked={isWriteBlocked}
        onClose={()=>{if(!isWriteBlocked())setConversionOpen(false)}} onSave={saveConversion} onInspectLatest={inspectLatest}/>
      <TopologyHistoryPanel opened={historyOpen} topology={topology} labId={labProfileId} dirty={dirty}
        blocked={editingBlocked} isBlocked={isWriteBlocked} onClose={()=>setHistoryOpen(false)}
        onRestore={restoreRevision} onInspectLatest={inspectLatest}/>
      <Modal opened={latest!==null} onClose={()=>setLatest(null)} title="核对服务器最新保存修订" size="xl" closeOnClickOutside={false}>
        <Stack>
          <Alert color="orange">读取不改变草稿或解除未知状态。请核对修订、操作与内容；只有显式采用才放弃旧草稿和转换输入，不会自动重试写请求。</Alert>
          <Text>本地保存令牌 r{topology.revision} · 服务器 r{latest?.revision}</Text>
          <Text fw={600}>服务器当前详情（GET）</Text><pre style={{whiteSpace:'pre-wrap',maxHeight:240,overflow:'auto'}}>{JSON.stringify(latest,null,2)}</pre>
          <Text fw={600}>服务器历史操作</Text><pre style={{whiteSpace:'pre-wrap',maxHeight:180,overflow:'auto'}}>{JSON.stringify(latestHistory,null,2)}</pre>
          <Text fw={600}>保留中的本地草稿</Text><pre style={{whiteSpace:'pre-wrap',maxHeight:180,overflow:'auto'}}>{JSON.stringify(draft,null,2)}</pre>
          <Group><Button variant="default" onClick={()=>setLatest(null)}>保留草稿，取消核对</Button>
            <Button color="orange" disabled={saving||collectionBusy||libraryBusy} onClick={adoptLatest}>确认放弃旧草稿并采用服务器最新</Button></Group>
        </Stack>
      </Modal>

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
          const sourcePinOpts = nodePortsToSelectOptions(sourceNode,'source');
          const targetPinOpts = nodePortsToSelectOptions(targetNode,'target');
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
            {edgePortPresentation(draft.nodes,selectedEdge).warning&&<Alert color="orange">{edgePortPresentation(draft.nodes,selectedEdge).warning}；现有pins保持原值，修改端点时重新核对。</Alert>}

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
            <Text size="xs">线缆节点不另计损耗；未知请留空，不用0代替。只有明确声明同一物理线缆归属的两侧才共用owner原值；未声明仍逐边参与。整条实测校准在校准面板采用，不填此处。</Text>
            {selectedEdge.loss_owner_connection_id && <Group><Text size="xs">旧值保留、不参与本组计算；量值归属：{selectedEdge.loss_owner_connection_id}</Text>
              <Button size="xs" variant="subtle" onClick={()=>openConnection(selectedEdge.loss_owner_connection_id!)}>定位owner</Button></Group>}

            <TextInput
              label="电缆类型"
              value={selectedEdge.cable_type || ''}
              disabled={editingBlocked}
              onChange={(e) => updateConnectionParam('cable_type', e.currentTarget.value)}
            />
            <NumberInput
              label="标称电缆损耗 (dB)"
              value={selectedEdge.cable_loss_db ?? ''}
              placeholder="未知"
              disabled={editingBlocked || !!selectedEdge.loss_owner_connection_id}
              onChange={(val) => updateConnectionParam('cable_loss_db', val === '' ? null : val)}
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
              onChange={(key,value,metadata)=>{if(!isWriteBlocked())setSelectedEdge(current=>{
                if(!current)return null;const updated=setEdgeNominal(current,key,value,metadata);
                // 来源编辑不声明新电缆数值，特别是存量参考边的缺键。
                if(Object.hasOwn(current,key))return {...updated,[key]:current[key as keyof TopologyConnection]};
                delete (updated as any)[key];return updated;
              })}}/>
            <NominalPropertyFields key={`pa-${selectedEdge.id}`} fields={edgeNominalFields} values={selectedEdge as unknown as Record<string,unknown>}
              metadata={selectedEdge.nominal_metadata} disabled={editingBlocked} onValidityChange={setEdgeNominalValid}
              onChange={(key,value,metadata)=>{if(!isWriteBlocked())setSelectedEdge(current=>current?setEdgeNominal(current,key,value,metadata):null)}}/>
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
  const editorMounted=useRef(true);
  useEffect(()=>{editorMounted.current=true;return()=>{editorMounted.current=false}},[]);
  const [availableSwitches, setAvailableSwitches] = useState<SwitchOption[]>([]);
  const [selectedSwitchId, setSelectedSwitchId] = useState(initialId || '');
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const {selectedLabProfileId: labProfileId, chamberId, chamberName, beginWork, registerSwitchGuard} = useOperationalLab();
  const [flowDirty,setFlowDirty] = useState(false);
  const [flowBusy,setFlowBusy] = useState(false);
  const [libraryBusy,setLibraryBusy] = useState(false);
  const [libraryUnknown,setLibraryUnknown]=useState(false);
  const [libraryRevisionError,setLibraryRevisionError]=useState('');
  const [libraryInspection,setLibraryInspection]=useState<{items:SwitchTopology[];saved:SwitchTopology|null;history:unknown;
    token:{scope:string;generation:number};sourceId:string|null}|null>(null);
  const [libraryInspecting,setLibraryInspecting]=useState(false);
  const libraryInspectSerial=useRef(0);
  const lock = useRef({dirty:false,flow:false,library:false,unknown:false});
  const syncGuard = useCallback(() => {
    const value=lock.current;
    registerSwitchGuard('topology-editor',value.flow||value.library||value.unknown
      ? '拓扑操作尚未结束或采集尚未确认结束，请先查看当前操作'
      : value.dirty ? '拓扑编辑器有未保存的改动 —— 请先保存或放弃再切换 LabProfile' : null);
  },[registerSwitchGuard]);
  const handleFlowDirty=useCallback((dirty:boolean)=>{if(!editorMounted.current)return;lock.current.dirty=dirty;setFlowDirty(dirty);syncGuard()},[syncGuard]);
  const handleFlowBusy=useCallback((busy:boolean)=>{if(!editorMounted.current)return;lock.current.flow=busy;setFlowBusy(busy);syncGuard()},[syncGuard]);
  const isLibraryBusy=useCallback(()=>lock.current.library||lock.current.unknown,[]);
  useOperationalLabSwitchGuard('topology-editor',flowBusy||libraryBusy||libraryUnknown ? '拓扑操作尚未结束或采集尚未确认结束'
    : flowDirty ? '拓扑编辑器有未保存的改动 —— 请先保存或放弃再切换 LabProfile' : null);
  const canLeave=()=>canLeaveTopology(lock.current.dirty,lock.current.flow||lock.current.library||lock.current.unknown);
  const blocked=flowDirty||flowBusy||libraryBusy||libraryUnknown;

  const scope=JSON.stringify([labProfileId,selectedSwitchId]);
  const request=useRef({scope,generation:0});
  // render即失效旧Lab；effect尚未运行的间隙也不能展示/回写旧图。
  if(request.current.scope!==scope) request.current={scope,generation:request.current.generation+1};
  const [loadedScope,setLoadedScope]=useState('');
  const [library,setLibrary]=useState<SwitchTopology[]>([]);
  const [selectedId,setSelectedId]=useState<string|null>(null);
  const [topology,setTopology]=useState<SwitchTopology|null>(null);
  const [topoLoading,setTopoLoading]=useState(false);
  const [topoError,setTopoError]=useState<string|null>(null);
  const [conversionEpoch,setConversionEpoch]=useState(0);
  const [reload,setReload]=useState(0);
  const [modal,setModal]=useState<'name'|'copy'|null>(null);
  const [name,setName]=useState('');
  const [modalError,setModalError]=useState<string|null>(null);
  const currentId=useRef<string|null>(null);
  currentId.current=loadedScope===scope?selectedId:null;
  const currentTopology=loadedScope===scope?topology:null;
  const currentLibrary=loadedScope===scope?library:[];
  const owns=(token:{scope:string;generation:number},id?:string|null)=>
    requestMatches(request.current,token)&&(id===undefined||currentId.current===id);

  const [availableTemplates,setAvailableTemplates]=useState<string[]|null>(null);
  const [templateError,setTemplateError]=useState(false);
  const [templateReload,setTemplateReload]=useState(0);
  useEffect(()=>{
    let alive=true;setTemplateError(false);setAvailableTemplates(null);
    switchTopologyService.listTemplates().then(value=>{if(alive)setAvailableTemplates(value)})
      .catch(()=>{if(alive)setTemplateError(true)});
    return()=>{alive=false};
  },[templateReload]);

  useEffect(()=>{
    let alive=true;
    apiClient.get('/instruments/catalog').then(res=>{
      if(!alive)return;
      const switches:SwitchOption[]=(res.data?.categories||[]).filter((c:any)=>
        c.key?.toLowerCase().includes('switch')||c.key?.toLowerCase().includes('matrix')||
        c.label?.includes('开关')||c.label?.includes('矩阵'))
        .map((c:any)=>({value:c.categoryId||c.key,label:c.label,key:c.key}));
      setAvailableSwitches(switches);
      if(switches.length&&!initialId)setSelectedSwitchId(switches[0].value);
    }).catch(err=>{if(alive)setCatalogError(`无法加载仪器目录: ${err.message}`)})
      .finally(()=>{if(alive)setCatalogLoading(false)});
    return()=>{alive=false};
  },[]);

  const fetchLibrary=(lab:string,category:string)=>loadTopologyLibrary(
    (skip,limit)=>switchTopologyService.getTopologies(lab,category,skip,limit));
  const selectLoaded=(items:SwitchTopology[],id:string|null)=>{
    setLibrary(items);setSelectedId(id);currentId.current=id;
    setTopology(items.find(item=>item.id===id)??null);setLoadedScope(scope);
    setConversionEpoch(value=>value+1);
  };
  useEffect(()=>{
    const token={scope,generation:request.current.generation+1};request.current=token;
    setTopology(null);setSelectedId(null);currentId.current=null;setLibrary([]);setLoadedScope('');
    setModal(null);setTopoError(null);setLibraryInspection(null);setLibraryInspecting(false);libraryInspectSerial.current++;
    if(!labProfileId||!selectedSwitchId||!chamberId){setTopoLoading(false);return}
    setTopoLoading(true);
    fetchLibrary(labProfileId,selectedSwitchId).then(items=>{
      if(!owns(token))return;
      let preferred:string|null=null;
      const key=preferenceKey(labProfileId,selectedSwitchId);
      try{preferred=localStorage.getItem(key)}catch{
        notifications.show({color:'yellow',message:'本浏览器偏好不可读取；本次仍可选择编辑图'});
      }
      if(preferred&&!items.some(item=>item.id===preferred)){
        try{localStorage.removeItem(key)}catch{}
        notifications.show({color:'yellow',message:'本浏览器默认编辑图已失效，已回退到当前库中的图'});
      }
      selectLoaded(items,chooseTopology(items,preferred));
    }).catch(err=>{
      if(owns(token))setTopoError(`加载拓扑失败: ${errorText(err)}`);
    }).finally(()=>{if(owns(token))setTopoLoading(false)});
    return()=>{if(requestMatches(request.current,token))request.current={scope,generation:token.generation+1}};
  },[scope,chamberId,reload]);

  // 同一操作持有独立token；迟到finally只释放自己的锁，不能解锁新操作。
  const operation=useRef<object|null>(null);
  const runWrite=async(kind:'name'|'copy'|'import')=>{
    if(!canLeave()||!labProfileId||!selectedSwitchId||!chamberId)return;
    const id=currentId.current;
    const template=availableTemplates?.includes('caict_v4')?'caict_v4':availableTemplates?.[0];
    if(kind!=='import'&&!id)return;
    if(kind==='import'&&!template)return;
    const token={...request.current};
    libraryInspectSerial.current++;setLibraryInspection(null);setLibraryInspecting(false);
    const owner={};operation.current=owner;
    lock.current.library=true;setLibraryBusy(true);syncGuard();setModalError(null);setLibraryRevisionError('');
    const release=beginWork('topology-library','拓扑库写操作尚未结束');
    let writeConfirmed=false;
    try{
      let result:SwitchTopology;
      if(kind==='import') result=await switchTopologyService.importFromTemplate(selectedSwitchId,labProfileId,template!);
      else if(kind==='copy') result=await switchTopologyService.copyTopology(id!,labProfileId,name);
      else result=await switchTopologyService.updateTopology(id!,labProfileId,{name,expected_revision:topology!.revision});
      writeConfirmed=true;
      if(!owns(token,id))return;
      // 写成功后从服务器重读全集，不把客户端草稿或POST载荷当当前图。
      const items=await fetchLibrary(labProfileId,selectedSwitchId);
      if(!owns(token,id))return;
      if(!items.some(item=>item.id===result.id))throw new Error('写入已返回，但刷新列表中没有该图；请刷新核查，不要自动重试写入');
      const saved=await switchTopologyService.getTopology(result.id!,labProfileId);
      if(!owns(token,id))return;
      selectLoaded(items.map(item=>item.id===saved.id?saved:item),saved.id!);
      setModal(null);
      notifications.show({color:'green',message:kind==='name'?'名称已保存；执行选择未改变':'已新增非活跃副本；未修改本浏览器默认或正式执行选择'});
    }catch(err){
      if(!owns(token,id))return;
      const failure=revisionFailure(writeConfirmed?undefined:(err as any).response?.status);
      const message=`${failure.message} ${errorText(err)}`;
      setLibraryRevisionError(message);
      if(failure.kind==='unknown'){lock.current.unknown=true;setLibraryUnknown(true);syncGuard()}
      if(kind==='import')notifications.show({color:'red',title:'模板导入失败',message});
      else setModalError(message);
    }finally{
      release();
      if(editorMounted.current&&operation.current===owner){
        operation.current=null;lock.current.library=false;setLibraryBusy(false);syncGuard();
      }
    }
  };
  const inspectLibrary=async()=>{
    if(lock.current.library||lock.current.flow||!labProfileId)return;
    const token={...request.current},id=currentId.current,serial=++libraryInspectSerial.current;
    setLibraryInspecting(true);setLibraryInspection(null);
    try{
      const items=await fetchLibrary(labProfileId,selectedSwitchId);
      const selected=id??chooseTopology(items,null);
      const saved=selected?await switchTopologyService.getTopology(selected,labProfileId):null;
      const history=selected?await switchTopologyService.listRevisions(selected,labProfileId,0,50):null;
      if(owns(token,id)&&serial===libraryInspectSerial.current)setLibraryInspection({items,saved,history,token,sourceId:id});
    }catch(err){if(owns(token,id)&&serial===libraryInspectSerial.current)setLibraryRevisionError(`核查失败；未知锁和输入保留。 ${errorText(err)}`)}
    finally{if(owns(token,id)&&serial===libraryInspectSerial.current)setLibraryInspecting(false)}
  };
  const adoptLibraryLatest=()=>{
    if(!libraryInspection||!owns(libraryInspection.token,libraryInspection.sourceId)||lock.current.library||lock.current.flow)return;
    const {items,saved}=libraryInspection;
    selectLoaded(saved?items.map(item=>item.id===saved.id?saved:item):items,saved?.id??null);
    lock.current.unknown=false;setLibraryUnknown(false);setLibraryRevisionError('');setLibraryInspection(null);setModal(null);syncGuard();
  };
  const handleSelection=(id:string|null)=>{
    if(!id||id===currentId.current||!canLeave())return;
    selectLoaded(currentLibrary,id);
  };
  const openModal=(kind:'name'|'copy')=>{
    if(!canLeave()||!currentTopology)return;
    setName(kind==='copy'?`${currentTopology.name} 副本`:currentTopology.name);
    setModalError(null);setModal(kind);
  };
  const savePreference=()=>{
    if(!canLeave()||!labProfileId||!currentId.current)return;
    try{
      localStorage.setItem(preferenceKey(labProfileId,selectedSwitchId),currentId.current);
      notifications.show({color:'green',message:'已保存本浏览器默认编辑图；不改变正式执行拓扑'});
    }catch{
      notifications.show({color:'yellow',message:'本浏览器偏好未保存；仅保留本次选择'});
    }
  };
  const flowIdentity=`${scope}/${currentTopology?.id??''}`;
  const liveFlow=useRef(flowIdentity);liveFlow.current=flowIdentity;
  // 稳定回调避免普通重渲染触发子组件cleanup而误清dirty。
  const dirtyCallback=React.useMemo(()=>((value:boolean)=>{if(liveFlow.current===flowIdentity)handleFlowDirty(value)}),[flowIdentity,handleFlowDirty]);
  const busyCallback=React.useMemo(()=>((value:boolean)=>{if(liveFlow.current===flowIdentity)handleFlowBusy(value)}),[flowIdentity,handleFlowBusy]);

  return <Stack gap="lg" h="100%">
    <Card withBorder radius="md" padding="lg">
      <Group justify="space-between">
        <Group><IconTopologyRing size={22}/><Title order={4}>射频开关矩阵拓扑</Title></Group>
        <Badge color={chamberName?'brand':'orange'}>{chamberName?`当前暗室：${chamberName}`:'当前 LabProfile 未绑定暗室'}</Badge>
      </Group>
      <Group mt="sm" align="end">
        {catalogLoading?<Loader size="xs"/>:<Select label="射频开关设备" value={selectedSwitchId}
          data={availableSwitches} disabled={blocked} allowDeselect={false} w={240}
          onChange={value=>{if(value&&canLeave())setSelectedSwitchId(value)}}/>}
        <Select label="拓扑库（仅编辑选择）" value={currentTopology?.id??null} searchable
          data={currentLibrary.filter(item=>!!item.id).map(item=>({value:item.id!,label:topologyLabel(item)}))}
          disabled={blocked||topoLoading} onChange={handleSelection} w={420} allowDeselect={false}
          placeholder="当前范围尚无拓扑"/>
        <Button variant="light" disabled={blocked||topoLoading||!labProfileId} onClick={()=>{if(canLeave())setReload(value=>value+1)}}>刷新拓扑库</Button>
      </Group>
      <Group mt="sm">
        <Button disabled={blocked||!currentTopology} onClick={()=>openModal('name')}>重命名</Button>
        <Button disabled={blocked||!currentTopology} onClick={()=>openModal('copy')}>复制已保存版本为…</Button>
        <Button variant="light" disabled={blocked||!currentTopology} onClick={savePreference}>设为本浏览器默认编辑图</Button>
        {!!availableTemplates?.length&&<Button color="orange" variant="light" leftSection={<IconRefresh size={14}/>}
          loading={libraryBusy&&modal===null} disabled={blocked||topoLoading||!!topoError||!chamberId}
          onClick={()=>void runWrite('import')}>从模板新增副本</Button>}
      </Group>
      <Text size="xs" c="dimmed" mt="xs">库选择和本浏览器默认不改变正式执行绑定。复制/模板新增均为非活跃图，不自动用于正式测试。</Text>
      <Text size="xs" c="dimmed">进入页面从服务器读取保存基线；如曾离开结果未知的写操作，请核查服务器最新修订，页面不会自动重发。</Text>
      {blocked&&<Alert mt="sm" color="yellow">{flowDirty?'请先保存或放弃未保存草稿，再切换范围、复制、命名或导入。':'操作尚未结束；保存、转换或采集结束未确认时禁止切换和另存。'}</Alert>}
      {libraryRevisionError&&<Alert mt="sm" color="red">{libraryRevisionError}</Alert>}
      {!!libraryRevisionError&&<Button mt="xs" variant="light" loading={libraryInspecting} disabled={libraryBusy||flowBusy} onClick={()=>void inspectLibrary()}>核查服务器最新拓扑库（只读）</Button>}
      {templateError&&<Alert mt="sm" color="red" title="模板加载失败"><Button size="xs" variant="light" onClick={()=>setTemplateReload(value=>value+1)}>重试模板加载</Button></Alert>}
      {catalogError&&<Alert mt="sm" color="red">{catalogError}</Alert>}
    </Card>
    <Modal opened={modal!==null} onClose={()=>{if(!lock.current.library)setModal(null)}}
      closeOnClickOutside={!libraryBusy} closeOnEscape={!libraryBusy} withCloseButton={!libraryBusy}
      title={modal==='copy'?'复制已保存版本为…':'重命名拓扑'}>
      <Stack>
        <Text size="sm">源图：{currentTopology?topologyLabel(currentTopology):'无'}</Text>
        {modal==='copy'&&<Alert color="yellow">只复制已保存版本。副本非活跃、非默认；不复制旧采用记录、证书或历史执行。已有 calibrated_loss_db 和 calibrated_phase_deg 将置空，标称值不等于实测校准。</Alert>}
        <TextInput label="拓扑名称" value={name} disabled={libraryBusy} onChange={event=>setName(event.currentTarget.value)} required/>
        {modalError&&<Alert color="red">{modalError}</Alert>}
        {modalError&&<Button variant="light" loading={libraryInspecting} disabled={libraryBusy||flowBusy} onClick={()=>void inspectLibrary()}>核查服务器最新拓扑库（只读）</Button>}
        <Group justify="end"><Button variant="default" disabled={libraryBusy} onClick={()=>setModal(null)}>取消</Button>
          <Button loading={libraryBusy} disabled={!name.trim()||flowDirty||flowBusy||libraryUnknown} onClick={()=>void runWrite(modal==='copy'?'copy':'name')}>确认{modal==='copy'?'复制':'命名'}</Button></Group>
      </Stack>
    </Modal>
    <Modal opened={libraryInspection!==null} onClose={()=>setLibraryInspection(null)} title="核对服务器拓扑库" size="xl" closeOnClickOutside={false}>
      <Stack><Alert color="orange">请核对修订、历史操作与图内容。读取不会解除未知写锁，也不会自动重发命名、复制或导入。</Alert>
        <pre style={{whiteSpace:'pre-wrap',maxHeight:380,overflow:'auto'}}>{JSON.stringify(libraryInspection,null,2)}</pre>
        <Group><Button variant="default" onClick={()=>setLibraryInspection(null)}>保留输入，取消</Button>
          <Button color="orange" onClick={adoptLibraryLatest}>确认采用服务器最新并结束核查</Button></Group></Stack>
    </Modal>
    <div style={{height:'calc(100vh - 350px)',minHeight:500}}>
      {!labProfileId?<Center h="100%"><Text>请选择当前 LabProfile。</Text></Center>
        :!chamberId?<Center h="100%"><Text>当前 LabProfile 未绑定暗室。</Text></Center>
        :!selectedSwitchId?<Center h="100%"><Text>请先选择射频开关设备。</Text></Center>
        :topoLoading||loadedScope!==scope&&!topoError?<Center h="100%"><Loader/></Center>
        :topoError?<Center h="100%"><Alert color="red" title="拓扑加载失败">{topoError}</Alert></Center>
        :currentTopology?<ReactFlowProvider key={`${labProfileId}/${selectedSwitchId}/${currentTopology.id}`}>
          <TopologyFlow topology={currentTopology} labProfileId={labProfileId} conversionEpoch={conversionEpoch}
            libraryBusy={libraryBusy||libraryUnknown} isLibraryBusy={isLibraryBusy}
            onDirtyChange={dirtyCallback} onBusyChange={busyCallback}
            onTopologyUpdated={updated=>{if(liveFlow.current===flowIdentity&&updated.id===currentId.current){setTopology(updated);setLibrary(items=>items.map(item=>item.id===updated.id?updated:item))}}}/>
        </ReactFlowProvider>
        :<Center h="100%"><Text c="dimmed">此范围尚无拓扑配置；可显式从模板新增非活跃副本，不会自动导入。</Text></Center>}
    </div>
  </Stack>;
};

function errorText(error: any): string {
  const detail=error.response?.data?.detail??error.message??String(error);
  return typeof detail==='string'?detail:JSON.stringify(detail);
}
function topologyLabel(item:SwitchTopology):string {
  return `${item.name} · ${item.id?.slice(0,8)} · ${item.is_active?'活跃':'非活跃'}`;
}
