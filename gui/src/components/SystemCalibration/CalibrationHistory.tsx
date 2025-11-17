/**
 * Calibration History Component
 *
 * Display historical calibration records with filtering and search
 */
import { useState } from 'react';
import {
  Table,
  Badge,
  Group,
  Text,
  ActionIcon,
  TextInput,
  Select,
  Stack,
  Paper,
  ScrollArea,
} from '@mantine/core';
import {
  IconEye,
  IconSearch,
  IconDownload,
} from '@tabler/icons-react';

interface CalibrationRecord {
  id: string;
  type: 'TRP' | 'TIS' | 'Repeatability';
  dutModel: string;
  measuredValue: number;
  errorDb: number;
  validationPass: boolean;
  testedAt: string;
  testedBy: string;
}

const mockData: CalibrationRecord[] = [
  {
    id: '1',
    type: 'TRP',
    dutModel: 'Standard Dipole λ/2',
    measuredValue: 10.48,
    errorDb: -0.02,
    validationPass: true,
    testedAt: '2025-11-16 10:30',
    testedBy: 'Engineer A',
  },
  {
    id: '2',
    type: 'TIS',
    dutModel: 'Reference Smartphone',
    measuredValue: -90.35,
    errorDb: 0.15,
    validationPass: true,
    testedAt: '2025-11-16 11:15',
    testedBy: 'Engineer B',
  },
  {
    id: '3',
    type: 'Repeatability',
    dutModel: 'Standard Dipole λ/2',
    measuredValue: 10.52,
    errorDb: 0.18,
    validationPass: true,
    testedAt: '2025-11-16 12:00',
    testedBy: 'Engineer C',
  },
];

export function CalibrationHistory() {
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  const filteredData = mockData.filter(record => {
    const matchesSearch = record.dutModel.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         record.testedBy.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = !typeFilter || record.type === typeFilter;
    return matchesSearch && matchesType;
  });

  const rows = filteredData.map((record) => (
    <tr key={record.id}>
      <td>
        <Badge
          color={
            record.type === 'TRP' ? 'blue' :
            record.type === 'TIS' ? 'cyan' :
            'violet'
          }
          variant="light"
        >
          {record.type}
        </Badge>
      </td>
      <td>
        <Text size="sm">{record.dutModel}</Text>
      </td>
      <td>
        <Text size="sm" fw={600}>
          {record.measuredValue.toFixed(2)} dBm
        </Text>
      </td>
      <td>
        <Badge color={Math.abs(record.errorDb) < 0.5 ? 'green' : 'yellow'} variant="dot">
          {record.errorDb > 0 ? '+' : ''}{record.errorDb.toFixed(2)} dB
        </Badge>
      </td>
      <td>
        <Badge color={record.validationPass ? 'green' : 'red'}>
          {record.validationPass ? '通过' : '未通过'}
        </Badge>
      </td>
      <td>
        <Text size="sm" color="dimmed">{record.testedAt}</Text>
      </td>
      <td>
        <Text size="sm">{record.testedBy}</Text>
      </td>
      <td>
        <Group gap={4} justify="right">
          <ActionIcon color="blue" variant="subtle">
            <IconEye size={16} />
          </ActionIcon>
          <ActionIcon color="gray" variant="subtle">
            <IconDownload size={16} />
          </ActionIcon>
        </Group>
      </td>
    </tr>
  ));

  return (
    <Stack gap="md">
      {/* Filters */}
      <Group>
        <TextInput
          placeholder="搜索 DUT 或工程师..."
          leftSection={<IconSearch size={16} />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ flex: 1 }}
        />
        <Select
          placeholder="筛选类型"
          clearable
          value={typeFilter}
          onChange={setTypeFilter}
          data={[
            { value: 'TRP', label: 'TRP' },
            { value: 'TIS', label: 'TIS' },
            { value: 'Repeatability', label: '可重复性' },
          ]}
          style={{ width: 200 }}
        />
      </Group>

      {/* Table */}
      <Paper withBorder>
        <ScrollArea>
          <Table striped highlightOnHover>
            <thead>
              <tr>
                <th>类型</th>
                <th>DUT 型号</th>
                <th>测量值</th>
                <th>误差</th>
                <th>状态</th>
                <th>测试时间</th>
                <th>测试工程师</th>
                <th style={{ textAlign: 'right' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.length > 0 ? (
                rows
              ) : (
                <tr>
                  <td colSpan={8}>
                    <Text color="dimmed" ta="center" py="xl">
                      未找到匹配的记录
                    </Text>
                  </td>
                </tr>
              )}
            </tbody>
          </Table>
        </ScrollArea>
      </Paper>

      <Text size="xs" color="dimmed">
        共 {filteredData.length} 条记录
      </Text>
    </Stack>
  );
}
