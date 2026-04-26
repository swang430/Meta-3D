import { Handle, Position } from '@xyflow/react';
import { ThemeIcon, Group, Text, Stack, Badge, Box, Tooltip } from '@mantine/core';
import { 
  IconServer, 
  IconRouter, 
  IconAntenna, 
  IconRadio,
  IconWaveSine,
  IconDeviceAnalytics,
  IconTarget,
  IconChartLine,
  IconAntennaBars5,
} from '@tabler/icons-react';

// ==========================================
// Base Node Style
// ==========================================
const baseNodeStyle = {
  background: 'var(--mantine-color-body)',
  border: '1px solid var(--mantine-color-default-border)',
  borderRadius: '8px',
  padding: '10px 14px',
  minWidth: '150px',
  boxShadow: 'var(--mantine-shadow-sm)',
};

// ==========================================
// Channel Emulator Node (F64)
// ==========================================
export const ChannelEmulatorNode = ({ data }: any) => {
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-blue-6)', minWidth: '180px' }}>
      <Handle type="target" position={Position.Left} id="in1" style={{ top: '20%', background: 'var(--mantine-color-blue-6)' }} />
      <Handle type="target" position={Position.Left} id="in2" style={{ top: '40%', background: 'var(--mantine-color-blue-6)' }} />
      <Handle type="target" position={Position.Left} id="in3" style={{ top: '60%', background: 'var(--mantine-color-blue-6)' }} />
      <Handle type="target" position={Position.Left} id="in4" style={{ top: '80%', background: 'var(--mantine-color-blue-6)' }} />

      <Group gap="xs" mb={6}>
        <ThemeIcon color="blue" variant="light" size="sm">
          <IconWaveSine size={14} />
        </ThemeIcon>
        <Text size="sm" fw={600}>{data.label || 'Channel Emulator'}</Text>
      </Group>
      <Stack gap={2}>
        <Text size="xs" c="dimmed">{data.params?.vendor} {data.params?.model}</Text>
        <Group gap={4}>
          <Badge size="xs" variant="light" color="blue">{data.params?.inputs || 4} in</Badge>
          <Badge size="xs" variant="light" color="cyan">{data.params?.outputs || 32} out</Badge>
        </Group>
      </Stack>

      {/* CE outputs: use generic right handle */}
      <Handle type="source" position={Position.Right} id="out" style={{ background: 'var(--mantine-color-blue-6)' }} />
    </Box>
  );
};

// ==========================================
// Communication Tester Node (UXM)
// ==========================================
export const CommunicationTesterNode = ({ data }: any) => {
  const roles = data.params?.roles || {};
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-indigo-6)', minWidth: '190px' }}>
      <Group gap="xs" mb={6}>
        <ThemeIcon color="indigo" variant="light" size="sm">
          <IconRadio size={14} />
        </ThemeIcon>
        <Text size="sm" fw={600}>{data.label || 'UXM'}</Text>
      </Group>

      <Stack gap={2}>
        {Object.entries(roles).map(([port, desc]: [string, any]) => (
          <Text key={port} size="xs" c="dimmed">{port}: {desc}</Text>
        ))}
      </Stack>

      {/* Port handles on right */}
      {(data.params?.ports || ['RF1','RF2','RF3','RF4','RF5']).map((port: string, i: number) => (
        <Handle
          key={port}
          type="source"
          position={Position.Right}
          id={port}
          style={{
            top: `${15 + i * 18}%`,
            background: port === 'RF5' ? 'var(--mantine-color-orange-6)' : 'var(--mantine-color-indigo-6)',
          }}
        />
      ))}
    </Box>
  );
};

// ==========================================
// EMCenter Node (dual-mode: PA + Switch)
// ==========================================
export const EMCenterNode = ({ data }: any) => {
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-grape-6)', minWidth: '200px' }}>
      <Handle type="target" position={Position.Left} id="switch_in" style={{ top: '80%', background: 'var(--mantine-color-orange-6)' }} />

      <Group gap="xs" mb={6}>
        <ThemeIcon color="grape" variant="light" size="sm">
          <IconRouter size={14} />
        </ThemeIcon>
        <Text size="sm" fw={600}>{data.label || 'EMCenter'}</Text>
      </Group>

      <Stack gap={2}>
        <Group gap={4}>
          <Badge size="xs" variant="light" color="green">集成PA ×32</Badge>
          <Badge size="xs" variant="light" color="orange">Switch</Badge>
        </Group>
        <Text size="xs" c="dimmed">{data.params?.description || ''}</Text>
      </Stack>

      {/* PA output handle (right) */}
      <Handle type="source" position={Position.Right} id="pa_out" style={{ top: '30%', background: 'var(--mantine-color-green-6)' }} />
      {/* Switch output handle (right-bottom) */}
      <Handle type="source" position={Position.Right} id="sw_out" style={{ top: '70%', background: 'var(--mantine-color-orange-6)' }} />
      {/* PA input from CE (left) */}
      <Handle type="target" position={Position.Left} id="pa_in" style={{ top: '30%', background: 'var(--mantine-color-green-6)' }} />
    </Box>
  );
};

// ==========================================
// Probe Node (shared for horizontal & vertical)
// ==========================================
export const ProbeNode = ({ data }: any) => {
  const pol = data.params?.polarization;
  const isV = pol === 'V' || pol === 'Slant +45';
  const ring = data.params?.ring;
  const isHorizontal = ring === 'horizontal';

  return (
    <Box style={{
      ...baseNodeStyle,
      borderLeft: `4px solid var(--mantine-color-${isHorizontal ? 'green' : 'teal'}-6)`,
      minWidth: '100px',
      padding: '6px 10px',
    }}>
      <Handle type="target" position={Position.Left} id="in" style={{ background: `var(--mantine-color-${isHorizontal ? 'green' : 'teal'}-6)` }} />
      <Group gap={4} mb={2}>
        <ThemeIcon color={isHorizontal ? 'green' : 'teal'} variant="light" size="xs">
          <IconAntenna size={12} />
        </ThemeIcon>
        <Text size="xs" fw={500}>{data.label || 'Probe'}</Text>
      </Group>
      <Group gap={4}>
        <Badge size="xs" variant="outline" color={isV ? 'blue' : 'orange'}>
          {pol || '?'}
        </Badge>
        <Badge size="xs" variant="dot" color={isHorizontal ? 'green' : 'teal'}>
          {isHorizontal ? '水平' : '垂直'}
        </Badge>
      </Group>
    </Box>
  );
};

// ==========================================
// Reference Antenna Node (SGH)
// ==========================================
export const ReferenceAntennaNode = ({ data }: any) => {
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-yellow-6)' }}>
      <Handle type="target" position={Position.Left} id="rf" style={{ background: 'var(--mantine-color-yellow-6)' }} />
      <Group gap="xs" mb={4}>
        <ThemeIcon color="yellow" variant="light" size="sm">
          <IconTarget size={14} />
        </ThemeIcon>
        <Text size="sm" fw={600}>{data.label || 'SGH'}</Text>
      </Group>
      <Text size="xs" c="dimmed">{data.params?.description || '标准增益喇叭'}</Text>
      <Handle type="source" position={Position.Right} id="rf" style={{ background: 'var(--mantine-color-yellow-6)' }} />
    </Box>
  );
};

// ==========================================
// Signal Analyzer Node (FSVA3000)
// ==========================================
export const SignalAnalyzerNode = ({ data }: any) => {
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-pink-6)' }}>
      <Handle type="target" position={Position.Left} id="rf_in" style={{ background: 'var(--mantine-color-pink-6)' }} />
      <Group gap="xs" mb={4}>
        <ThemeIcon color="pink" variant="light" size="sm">
          <IconChartLine size={14} />
        </ThemeIcon>
        <Text size="sm" fw={600}>{data.label || 'Signal Analyzer'}</Text>
      </Group>
      <Text size="xs" c="dimmed">{data.params?.vendor} {data.params?.model}</Text>
    </Box>
  );
};

// ==========================================
// VNA Node
// ==========================================
export const VNANode = ({ data }: any) => {
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-violet-6)' }}>
      <Group gap="xs" mb={4}>
        <ThemeIcon color="violet" variant="light" size="sm">
          <IconDeviceAnalytics size={14} />
        </ThemeIcon>
        <Text size="sm" fw={600}>{data.label || 'VNA'}</Text>
      </Group>
      <Text size="xs" c="dimmed">{data.params?.description || '矢量网络分析仪'}</Text>
      <Handle type="source" position={Position.Right} id="Port1" style={{ top: '40%', background: 'var(--mantine-color-violet-6)' }} />
      <Handle type="source" position={Position.Right} id="Port2" style={{ top: '75%', background: 'var(--mantine-color-violet-6)' }} />
    </Box>
  );
};

// ==========================================
// Legacy CE Port Node (backward compat)
// ==========================================
export const CEPortNode = ({ data }: any) => {
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-blue-6)' }}>
      <Group gap="xs" mb={8}>
        <ThemeIcon color="blue" variant="light" size="sm">
          <IconServer size={14} />
        </ThemeIcon>
        <Text size="sm" fw={500}>{data.label || 'CE Port'}</Text>
      </Group>
      <Stack gap={2}>
        <Text size="xs" c="dimmed">Unit: {data.params?.ce_unit || '-'}</Text>
        <Text size="xs" c="dimmed">Port: {data.params?.port || '-'}</Text>
      </Stack>
      <Handle type="source" position={Position.Right} id="out" style={{ background: 'var(--mantine-color-blue-6)' }} />
    </Box>
  );
};

// ==========================================
// Legacy Switch Slot Node (backward compat)
// ==========================================
export const SwitchSlotNode = ({ data }: any) => {
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-grape-6)', minWidth: '120px' }}>
      <Group gap="xs" mb={8} justify="center">
        <ThemeIcon color="grape" variant="light" size="sm">
          <IconRouter size={14} />
        </ThemeIcon>
        <Text size="sm" fw={500}>{data.label || 'Switch Slot'}</Text>
      </Group>
      
      {/* Target (Input) Pins on Left */}
      <Handle type="target" position={Position.Left} id="P1" style={{ top: '30%', background: '#555' }} />
      <Text size="xs" style={{ position: 'absolute', left: 4, top: '22%' }} c="dimmed">P1</Text>
      
      <Handle type="target" position={Position.Left} id="P3" style={{ top: '70%', background: '#555' }} />
      <Text size="xs" style={{ position: 'absolute', left: 4, top: '62%' }} c="dimmed">P3</Text>
      
      {/* Source (Output) Pins on Right */}
      <Handle type="source" position={Position.Right} id="P2" style={{ top: '30%', background: '#555' }} />
      <Text size="xs" style={{ position: 'absolute', right: 4, top: '22%' }} c="dimmed">P2</Text>

      <Handle type="source" position={Position.Right} id="P4" style={{ top: '70%', background: '#555' }} />
      <Text size="xs" style={{ position: 'absolute', right: 4, top: '62%' }} c="dimmed">P4</Text>
    </Box>
  );
};

// ==========================================
// Node Types Registry
// ==========================================
export const customNodeTypes = {
  // V4.0 新节点类型
  channel_emulator: ChannelEmulatorNode,
  communication_tester: CommunicationTesterNode,
  emcenter: EMCenterNode,
  reference_antenna: ReferenceAntennaNode,
  signal_analyzer: SignalAnalyzerNode,
  vna: VNANode,

  // 通用 + 向后兼容
  probe: ProbeNode,
  ce_port: CEPortNode,
  bse_port: CommunicationTesterNode,
  switch_slot: SwitchSlotNode,
};
