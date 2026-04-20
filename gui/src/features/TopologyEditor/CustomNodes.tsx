import { Handle, Position } from '@xyflow/react';
import { ThemeIcon, Group, Text, Stack, Badge, Box } from '@mantine/core';
import { 
  IconServer, 
  IconRouter, 
  IconAntenna, 
  IconRadio
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
// CE Port Node
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
// Base Station Port Node
// ==========================================
export const BSEPortNode = ({ data }: any) => {
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-indigo-6)' }}>
      <Group gap="xs" mb={8}>
        <ThemeIcon color="indigo" variant="light" size="sm">
          <IconRadio size={14} />
        </ThemeIcon>
        <Text size="sm" fw={500}>{data.label || 'BSE Port'}</Text>
      </Group>
      <Handle type="source" position={Position.Right} id="out" style={{ background: 'var(--mantine-color-indigo-6)' }} />
    </Box>
  );
};

// ==========================================
// Switch Slot Node
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
// Probe Node
// ==========================================
export const ProbeNode = ({ data }: any) => {
  const pol = data.params?.polarization;
  const isV = pol === 'V' || pol === 'Slant +45';
  
  return (
    <Box style={{ ...baseNodeStyle, borderLeft: '4px solid var(--mantine-color-green-6)' }}>
      <Handle type="target" position={Position.Left} id="in" style={{ background: 'var(--mantine-color-green-6)' }} />
      <Group gap="xs" mb={4}>
        <ThemeIcon color="green" variant="light" size="sm">
          <IconAntenna size={14} />
        </ThemeIcon>
        <Text size="sm" fw={500}>{data.label || 'Probe'}</Text>
      </Group>
      <Group gap={4}>
        <Badge size="xs" variant="outline" color={isV ? 'blue' : 'orange'}>
          {pol || '?'}
        </Badge>
        {data.params?.ring && (
          <Badge size="xs" variant="dot" color="gray">
            {data.params.ring}
          </Badge>
        )}
      </Group>
    </Box>
  );
};

// ==========================================
// Node Types Registry
// ==========================================
export const customNodeTypes = {
  ce_port: CEPortNode,
  bse_port: BSEPortNode,
  switch_slot: SwitchSlotNode,
  probe: ProbeNode,
};
