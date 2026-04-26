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
import { switchTopologyService } from '../../api/switchTopologyService';
import type { SwitchTopology, TopologyConnection } from '../../api/switchTopologyService';
import apiClient from '../../api/client';


// ── Types ──────────────────────────────────────────────────────
interface SwitchOption {
  value: string;
  label: string;
  key: string;
}

interface TopologyEditorProps {
  switchCategoryId?: string;
}

// ── Inner: ReactFlow canvas with editing ────────────────────────

interface TopologyFlowProps {
  topology: SwitchTopology;
  onTopologyUpdated: (t: SwitchTopology) => void;
}

const TopologyFlow = ({ topology, onTopologyUpdated }: TopologyFlowProps) => {
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
    return topology.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      position: n.position || { x: 0, y: 0 },
      data: { label: n.label, params: n.params },
    }));
  }, [topology.nodes]);

  const initialEdges: Edge[] = React.useMemo(() => {
    const currentMode = topology.operating_modes.find(m => m.id === activeMode);
    const activeConnectionIds = new Set(currentMode?.active_connections || []);

    return connectionsRef.current.map((c) => {
      const isActive = activeConnectionIds.has(c.id);
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
          inactive: !isActive 
        },
        animated: isActive,
        markerEnd: isActive ? { type: MarkerType.ArrowClosed, color: c.calibrated_loss_db ? '#10B981' : '#3B82F6' } : undefined,
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

      // 2. Build update payload with current positions + edited connections
      const updatedNodes = nodesDataRef.current.map(n => {
        // merge ReactFlow's current position
        const rfNode = nodes.find(rn => rn.id === n.id);
        return {
          ...n,
          position: rfNode?.position || n.position,
        };
      });

      const payload = {
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
    } catch (err: any) {
      notifications.show({
        title: '保存失败',
        message: err.response?.data?.detail || err.message,
        color: 'red',
        icon: <IconX size={16} />,
        autoClose: 5000,
      });
    } finally {
      setSaving(false);
    }
  }, [topology, nodes, onTopologyUpdated]);

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
        {selectedEdge && (
          <Stack gap="md">
            <Paper withBorder p="sm" radius="md" bg="gray.0">
              <Group gap="xs" mb="xs">
                <IconCircleDot size={14} />
                <Text size="sm" fw={600}>连线标识</Text>
              </Group>
              <Text size="xs" c="dimmed" style={{ wordBreak: 'break-all' }}>{selectedEdge.id}</Text>
              <Group gap="lg" mt="xs">
                <Text size="xs"><b>源:</b> {selectedEdge.source}</Text>
                <Text size="xs"><b>目标:</b> {selectedEdge.target}</Text>
              </Group>
            </Paper>

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
        )}
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

  const [topology, setTopology] = useState<SwitchTopology | null>(null);
  const [topoLoading, setTopoLoading] = useState(false);
  const [topoError, setTopoError] = useState<string | null>(null);
  const [reimporting, setReimporting] = useState(false);

  // Reimport: delete old topology and import fresh V4.0
  const handleReimport = useCallback(async () => {
    if (!selectedSwitchId) return;
    setReimporting(true);
    try {
      // Delete existing topologies for this category
      const resp = await switchTopologyService.getTopologies(selectedSwitchId);
      const items = resp.items || (Array.isArray(resp) ? resp : []);
      for (const item of items) {
        if (item.id) {
          try {
            await apiClient.delete(`/switch-topologies/${item.id}`);
          } catch { /* ignore deletion errors */ }
        }
      }

      // Import fresh default
      const imported = await switchTopologyService.importCaictDefault(selectedSwitchId);
      setTopology(imported);
      notifications.show({
        title: '拓扑已更新',
        message: `已导入 V4.0 拓扑: ${imported.name}`,
        color: 'green',
        icon: <IconCheck size={16} />,
        autoClose: 3000,
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
  }, [selectedSwitchId]);

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

  // Fetch topology when switch is selected
  useEffect(() => {
    if (!selectedSwitchId) return;

    setTopoLoading(true);
    setTopoError(null);
    setTopology(null);

    switchTopologyService.getTopologies(selectedSwitchId)
      .then(resp => {
        const items = resp.items || (Array.isArray(resp) ? resp : []);
        if (items.length > 0) {
          setTopology(items[0]);
        } else {
          return switchTopologyService.importCaictDefault(selectedSwitchId)
            .then(imported => setTopology(imported));
        }
      })
      .catch(err => {
        console.error('Topology fetch failed:', err);
        setTopoError(`加载拓扑失败: ${err.response?.data?.detail || err.message}`);
      })
      .finally(() => setTopoLoading(false));
  }, [selectedSwitchId]);

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
            {catalogLoading ? (
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="sm" c="dimmed">加载仪器目录…</Text>
              </Group>
            ) : availableSwitches.length > 0 ? (
              <Select
                value={selectedSwitchId}
                onChange={(val) => val && setSelectedSwitchId(val)}
                data={availableSwitches}
                placeholder="选择射频开关设备…"
                w={260}
                allowDeselect={false}
              />
            ) : (
              <Badge color="orange" variant="light" size="lg">
                未检测到射频开关设备
              </Badge>
            )}
            {topology && (
              <Button
                variant="light"
                color="orange"
                size="xs"
                leftSection={<IconRefresh size={14} />}
                loading={reimporting}
                onClick={handleReimport}
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
        {!selectedSwitchId ? (
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
