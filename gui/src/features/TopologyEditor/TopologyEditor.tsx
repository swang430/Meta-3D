import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  ReactFlow, 
  Background, 
  Controls, 
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  ReactFlowProvider,
  MarkerType,
} from '@xyflow/react';
import type { Connection, Edge, Node, NodeChange } from '@xyflow/react';
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

import { customNodeTypes } from './CustomNodes';
import { customEdgeTypes } from './CustomEdges';
import { nodePortsToSelectOptions } from './nodePortHelpers';
import { switchTopologyService } from '../../api/switchTopologyService';
import type { SwitchTopology, TopologyConnection } from '../../api/switchTopologyService';
import { fetchChamberConfigurations } from '../../api/service';
import apiClient from '../../api/client';
import { logFrontendEvent } from '../../observability/frontendLogger';


// ── Types ──────────────────────────────────────────────────────
interface SwitchOption {
  value: string;
  label: string;
  key: string;
}

interface ChamberOption {
  value: string;
  label: string;
}

interface TopologyEditorProps {
  switchCategoryId?: string;
}

// ── Inner: ReactFlow canvas with editing ────────────────────────

interface TopologyFlowProps {
  topology: SwitchTopology;
  selectedChamberId: string;
  onTopologyUpdated: (t: SwitchTopology) => void;
}

const TopologyFlow = ({ topology, selectedChamberId, onTopologyUpdated }: TopologyFlowProps) => {
  const [activeMode, setActiveMode] = useState<string>(
    topology.operating_modes.length > 0 ? topology.operating_modes[0].id : ''
  );
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState<TopologyConnection | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Track local edits to connections
  const connectionsRef = useRef<TopologyConnection[]>([...topology.connections]);
  const nodesDataRef = useRef(topology.nodes.map(n => ({ ...n })));

  // Reset refs when topology prop changes (e.g. after save refresh)
  useEffect(() => {
    connectionsRef.current = [...topology.connections];
    nodesDataRef.current = topology.nodes.map(n => ({ ...n }));
    setDirty(false);
  }, [topology.id]);

  const initialNodes: Node[] = React.useMemo(() => {
    const currentMode = topology.operating_modes.find(m => m.id === activeMode);
    const activeConnectionIds = new Set(currentMode?.active_connections || []);

    // Collect node IDs that have at least one active connection
    const activeNodeIds = new Set<string>();
    for (const c of connectionsRef.current) {
      if (activeConnectionIds.has(c.id)) {
        activeNodeIds.add(c.source);
        activeNodeIds.add(c.target);
      }
    }

    return topology.nodes
      .filter((n) => {
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
      }));
  }, [topology.nodes, topology.operating_modes, activeMode]);

  const initialEdges: Edge[] = React.useMemo(() => {
    const currentMode = topology.operating_modes.find(m => m.id === activeMode);
    const activeConnectionIds = new Set(currentMode?.active_connections || []);

    return connectionsRef.current
      .filter((c) => activeConnectionIds.has(c.id))
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
          pa_gain_db: (c as any).pa_gain_db,
          direction: c.direction,
        },
        animated: true,
        markerEnd: { 
          type: MarkerType.ArrowClosed, 
          color: c.direction === 'UL' ? '#D946EF' : (c.calibrated_loss_db ? '#10B981' : ((c as any).pa_gain_db ? '#F59E0B' : '#3B82F6')) 
        },
      };
    });
  }, [topology.connections, topology.operating_modes, activeMode]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const onConnect = useCallback(
    (params: Connection | Edge) => setEdges((eds) => addEdge({ ...params, type: 'signal' }, eds)),
    [setEdges],
  );

  // ── Node drag → update position in ref, mark dirty ──
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    onNodesChange(changes);
    // Track position changes
    for (const change of changes) {
      if (change.type === 'position' && change.position && !change.dragging) {
        const nodeData = nodesDataRef.current.find(n => n.id === change.id);
        if (nodeData) {
          nodeData.position = { x: change.position.x, y: change.position.y };
          setDirty(true);
        }
      }
    }
  }, [onNodesChange]);

  // ── Edge click → open parameter drawer ──
  const handleEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    const conn = connectionsRef.current.find(c => c.id === edge.id);
    if (conn) {
      setSelectedEdge({ ...conn });
      setDrawerOpen(true);
    }
  }, []);

  // ── Update connection parameter ──
  const updateConnectionParam = useCallback((field: keyof TopologyConnection, value: any) => {
    if (!selectedEdge) return;
    setSelectedEdge(prev => prev ? { ...prev, [field]: value } : null);
  }, [selectedEdge]);

  const applyConnectionEdit = useCallback(() => {
    if (!selectedEdge) return;
    const idx = connectionsRef.current.findIndex(c => c.id === selectedEdge.id);
    if (idx >= 0) {
      connectionsRef.current[idx] = { ...selectedEdge };
      setDirty(true);
      // Update edge data in ReactFlow
      setEdges(eds => eds.map(e => {
        if (e.id === selectedEdge.id) {
          return {
            ...e,
            data: {
              ...e.data,
              cable_loss_db: selectedEdge.cable_loss_db,
              calibrated_loss_db: selectedEdge.calibrated_loss_db,
            },
          };
        }
        return e;
      }));
      setDrawerOpen(false);
      notifications.show({
        message: `连线 ${selectedEdge.id} 参数已更新`,
        color: 'blue',
        autoClose: 2000,
      });
    }
  }, [selectedEdge, setEdges]);

  // ── Save: validate then PATCH ──
  const handleSave = useCallback(async () => {
    if (!topology.id) return;
    // P1: block save when chamber binding is missing — backend returns 422
    // for active topologies anyway, but failing in the UI gives a clearer
    // message and avoids a doomed network round-trip.
    if (!selectedChamberId) {
      notifications.show({
        title: '需要先选择目标暗室',
        message: '保存前必须为该拓扑绑定一个暗室。请使用顶部的暗室下拉。',
        color: 'orange',
        icon: <IconAlertTriangle size={16} />,
        autoClose: 5000,
      });
      return;
    }
    setSaving(true);

    try {
      // 1. Validate first
      const validation = await switchTopologyService.validateTopology(topology.id);
      const errors = (validation.issues || []).filter((i: any) => i.severity === 'error');
      const warnings = (validation.issues || []).filter((i: any) => i.severity === 'warning');

      if (errors.length > 0) {
        notifications.show({
          title: '拓扑验证失败',
          message: `${errors.length} 个错误需要修复`,
          color: 'red',
          icon: <IconX size={16} />,
          autoClose: 5000,
        });
        setSaving(false);
        return;
      }

      if (warnings.length > 0) {
        notifications.show({
          title: '拓扑验证警告',
          message: `${warnings.length} 个警告（不影响保存）`,
          color: 'yellow',
          icon: <IconAlertTriangle size={16} />,
          autoClose: 3000,
        });
      }

      // 2. Build update payload with current positions + edited connections.
      // P1: chamber_id is always included so a re-save fixes any legacy row
      // that was orphaned before this constraint existed.
      const updatedNodes = nodesDataRef.current.map(n => {
        const rfNode = nodes.find(rn => rn.id === n.id);
        return {
          ...n,
          position: rfNode?.position || n.position,
        };
      });

      const payload = {
        chamber_id: selectedChamberId,
        nodes: updatedNodes,
        connections: connectionsRef.current,
      };

      // 3. PATCH to backend
      const updated = await switchTopologyService.updateTopology(topology.id, payload);

      setDirty(false);
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
        message: `topology=${topology.id} chamber=${selectedChamberId} nodes=${updatedNodes.length} conns=${connectionsRef.current.length}`,
      });
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message;
      notifications.show({
        title: '保存失败',
        message: detail,
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
    }
  }, [topology, nodes, onTopologyUpdated, selectedChamberId]);

  const activeModeObj = topology.operating_modes.find(m => m.id === activeMode);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <Paper p="sm" withBorder style={{ borderBottom: 'none', borderBottomLeftRadius: 0, borderBottomRightRadius: 0 }}>
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
            <Select 
              value={activeMode} 
              onChange={(v) => v && setActiveMode(v)}
              data={topology.operating_modes.map(m => ({ value: m.id, label: m.name }))}
              placeholder="操作模式"
              w={200}
            />
            <Button 
              leftSection={<IconDeviceFloppy size={16} />} 
              onClick={handleSave}
              loading={saving}
              color={dirty ? 'yellow' : 'blue'}
            >
              保存拓扑
            </Button>
          </Group>
        </Group>
      </Paper>

      {/* Canvas */}
      <div style={{ flex: 1, border: '1px solid var(--mantine-color-default-border)' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={handleNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onEdgeClick={handleEdgeClick}
          nodeTypes={customNodeTypes}
          edgeTypes={customEdgeTypes}
          fitView
          attributionPosition="bottom-right"
        >
          <Background color="#ccc" gap={16} />
          <Controls />
          <MiniMap nodeStrokeWidth={3} zoomable pannable />
        </ReactFlow>
      </div>
      
      {/* Status bar */}
      <Paper p="xs" withBorder style={{ borderTop: 'none', borderTopLeftRadius: 0, borderTopRightRadius: 0, backgroundColor: 'var(--mantine-color-gray-0)' }}>
        <Group justify="space-between">
          <Text size="sm" c="dimmed">{activeModeObj?.description || '—'}</Text>
          <Group gap="md">
            <Text size="xs" c="dimmed">
              节点: {topology.total_nodes ?? topology.nodes.length} · 连接: {topology.total_connections ?? topology.connections.length}
            </Text>
            <Text size="xs" c="dimmed">点击连线可编辑参数</Text>
          </Group>
        </Group>
      </Paper>

      {/* ── Edge Parameter Drawer ── */}
      <Drawer
        opened={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="连线参数编辑"
        position="right"
        size="sm"
        padding="lg"
      >
        {selectedEdge && (() => {
          const sourceNode = topology.nodes.find((n) => n.id === selectedEdge.source);
          const targetNode = topology.nodes.find((n) => n.id === selectedEdge.target);
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
            />
            <Select
              label="目标端口"
              description={targetNode ? `节点 ${targetNode.type}` : '未知节点'}
              data={targetPinOpts}
              value={selectedEdge.target_pin || null}
              onChange={(v) => updateConnectionParam('target_pin', v || '')}
              searchable
              allowDeselect={false}
            />

            <Divider label="电缆参数 (可编辑)" labelPosition="center" />

            <TextInput
              label="电缆类型"
              value={selectedEdge.cable_type || ''}
              onChange={(e) => updateConnectionParam('cable_type', e.currentTarget.value)}
            />
            <NumberInput
              label="标称电缆损耗 (dB)"
              value={selectedEdge.cable_loss_db ?? 0}
              onChange={(val) => updateConnectionParam('cable_loss_db', val)}
              decimalScale={2}
              step={0.1}
              min={0}
              max={30}
            />
            <NumberInput
              label="电缆长度 (m)"
              value={selectedEdge.cable_length_m ?? 0}
              onChange={(val) => updateConnectionParam('cable_length_m', val)}
              decimalScale={1}
              step={0.5}
              min={0}
              max={50}
            />

            <Divider label="校准数据 (只读)" labelPosition="center" />

            <TextInput
              label="校准损耗 (dB)"
              value={selectedEdge.calibrated_loss_db != null ? String(selectedEdge.calibrated_loss_db) : '未校准'}
              readOnly
              styles={{ input: { backgroundColor: 'var(--mantine-color-gray-1)', cursor: 'not-allowed' } }}
            />
            <TextInput
              label="校准相位 (°)"
              value={selectedEdge.calibrated_phase_deg != null ? String(selectedEdge.calibrated_phase_deg) : '未校准'}
              readOnly
              styles={{ input: { backgroundColor: 'var(--mantine-color-gray-1)', cursor: 'not-allowed' } }}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="outline" onClick={() => setDrawerOpen(false)}>取消</Button>
              <Button onClick={applyConnectionEdit}>应用修改</Button>
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

  // P1: chamber binding is mandatory — the topology models cabling inside a
  // specific chamber, so importing without one leaves calibration / measure
  // unable to resolve a chamber. Selector lives next to the switch selector.
  const [availableChambers, setAvailableChambers] = useState<ChamberOption[]>([]);
  const [selectedChamberId, setSelectedChamberId] = useState<string>('');
  const [chambersLoading, setChambersLoading] = useState(true);
  const [chambersError, setChambersError] = useState<string | null>(null);

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

  // Reimport: delete old topology and import fresh V4.0
  const handleReimport = useCallback(async () => {
    if (!selectedSwitchId) return;
    if (!selectedChamberId) {
      notifications.show({
        title: '需要先选择目标暗室',
        message: '导入拓扑前必须绑定一个暗室,以便后续校准/测量能够解析。',
        color: 'orange',
        icon: <IconAlertTriangle size={16} />,
      });
      return;
    }
    // Resolve the template *before* deleting the existing topology, so a
    // commercial-deploy 404 doesn't leave the chamber with no wiring at all.
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
      // Delete only the topology for THIS (switch, chamber) pair — leave
      // other chambers' topologies alone. Each chamber owns its own row.
      const resp = await switchTopologyService.getTopologies(
        selectedSwitchId,
        selectedChamberId,
      );
      const items = resp.items || (Array.isArray(resp) ? resp : []);
      for (const item of items) {
        if (item.id) {
          try {
            await apiClient.delete(`/switch-topologies/${item.id}`);
          } catch { /* ignore deletion errors */ }
        }
      }

      // Import fresh default for this chamber. template_id is whichever
      // template the deployment ships; pickDefaultTemplate() prefers
      // 'caict_v4' when present.
      const imported = await switchTopologyService.importFromTemplate(
        selectedSwitchId,
        selectedChamberId,
        templateId,
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
        message: `switch=${selectedSwitchId} chamber=${selectedChamberId} topology=${imported.id}`,
      });
    } catch (err: any) {
      notifications.show({
        title: '重导入失败',
        message: err.response?.data?.detail || err.message,
        color: 'red',
        icon: <IconX size={16} />,
        autoClose: 5000,
      });
    } finally {
      setReimporting(false);
    }
  }, [selectedSwitchId, selectedChamberId, pickDefaultTemplate]);

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
  useEffect(() => {
    setChambersLoading(true);
    setChambersError(null);
    fetchChamberConfigurations()
      .then((res) => {
        const items = res?.items || [];
        const opts: ChamberOption[] = items.map((c) => ({
          value: c.id,
          label: c.name || `Chamber ${c.id?.slice(0, 8)}`,
        }));
        setAvailableChambers(opts);
      })
      .catch((err) => {
        console.error('Failed to fetch chambers:', err);
        setChambersError(`无法加载暗室列表: ${err.message}`);
      })
      .finally(() => setChambersLoading(false));
  }, []);

  // Fetch topology for the (switch, chamber) pair. Each chamber holds its own
  // topology row — the model design (switch_topology.py) is explicit:
  //   "每条记录代表一个 Switch 实例在特定暗室中的完整接线配置".
  // First mount (no chamber yet) fetches by switch alone and seeds the chamber
  // dropdown from whichever topology sorts first. After that, any chamber pick
  // fetches the chamber-specific row; if none exists, auto-import default for
  // that chamber WITHOUT touching other chambers' topologies.
  useEffect(() => {
    if (!selectedSwitchId) return;

    setTopoLoading(true);
    setTopoError(null);
    setTopology(null);

    switchTopologyService.getTopologies(selectedSwitchId, selectedChamberId || undefined)
      .then(resp => {
        const items = resp.items || (Array.isArray(resp) ? resp : []);
        if (items.length > 0) {
          const t = items[0];
          setTopology(t);
          // Seed chamber dropdown from topology on first mount. After the user
          // has picked a chamber, the query is already chamber-filtered so
          // chamber_id matches selectedChamberId by construction.
          if (t.chamber_id && !selectedChamberId) {
            setSelectedChamberId(t.chamber_id);
          }
          return;
        }
        if (!selectedChamberId) {
          // No topology AND no chamber chosen — defer auto-import.
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
          selectedChamberId,
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
  }, [selectedSwitchId, selectedChamberId, availableTemplates, pickDefaultTemplate]);

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
            {/* P1: chamber binding (required). Without it, save / import are
                blocked because the topology has no chamber to attach cabling
                to — calibration / measure can't resolve a topology that
                isn't bound to a specific chamber row. */}
            {chambersLoading ? (
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="sm" c="dimmed">加载暗室…</Text>
              </Group>
            ) : availableChambers.length > 0 ? (
              <Select
                label="目标暗室"
                value={selectedChamberId || null}
                onChange={(val) => val && setSelectedChamberId(val)}
                data={availableChambers}
                placeholder="选择目标暗室..."
                w={220}
                required
                allowDeselect={false}
                error={!selectedChamberId ? '保存前必填' : undefined}
              />
            ) : (
              <Badge color="orange" variant="light" size="lg">
                未配置任何暗室
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
                disabled={!selectedChamberId}
                title={!selectedChamberId ? '请先选择目标暗室' : undefined}
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

        {/* P1: chamber-binding status hint when topology already exists but
            had no chamber attached (legacy row from before this constraint). */}
        {topology && !topology.chamber_id && selectedChamberId && (
          <Alert color="orange" variant="light" icon={<IconAlertTriangle size={16} />} mt="sm">
            当前拓扑未绑定暗室。点击"保存拓扑"会将其绑定到所选暗室。
          </Alert>
        )}


        {catalogError && (
          <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />} mt="sm">
            {catalogError}
          </Alert>
        )}

        {chambersError && (
          <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />} mt="sm">
            {chambersError}
          </Alert>
        )}
      </Card>

      {/* Topology Canvas Area */}
      <div style={{ height: 'calc(100vh - 250px)', minHeight: 500 }}>
        {!selectedChamberId ? (
          <Center h="100%">
            <Stack align="center" gap="sm">
              <IconTopologyRing size={48} color="var(--mantine-color-gray-4)" />
              <Text c="dimmed" ta="center">
                请先在上方选择目标暗室。<br />
                拓扑必须绑定到一个具体暗室,以便后续校准/测量解析。
              </Text>
            </Stack>
          </Center>
        ) : !selectedSwitchId ? (
          <Center h="100%">
            <Stack align="center" gap="sm">
              <IconTopologyRing size={48} color="var(--mantine-color-gray-4)" />
              <Text c="dimmed" ta="center">
                请先在上方选择一个射频开关设备，<br />
                或在「仪器资源配置」中添加 RF Switch 类别。
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
              selectedChamberId={selectedChamberId}
              onTopologyUpdated={(updated) => setTopology(updated)}
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
