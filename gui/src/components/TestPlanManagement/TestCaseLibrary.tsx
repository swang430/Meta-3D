/**
 * Test Case Library Component
 *
 * Displays test cases grouped by template_category as card-based layout.
 * This is the foundation of the test management system — users pick test cases
 * from here to compose test plans.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Stack,
  Group,
  Text,
  Title,
  TextInput,
  Badge,
  Paper,
  Button,
  SimpleGrid,
  Accordion,
  ActionIcon,
  Tooltip,
  Checkbox,
  Loader,
  Center,
  Divider,
  ThemeIcon,
  Select,
} from '@mantine/core';
import {
  IconSearch,
  IconPlus,
  IconFlask,
  IconAntenna,
  IconWifi,
  IconRoute,
  IconChartLine,
  IconRadar,
  IconArrowsShuffle,
  IconChecklist,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import {
  listTestCases,
  type TestCaseSummary,
  type TestCaseType,
  getTestTypeLabel,
} from '../../api/testPlanService';

// Category icon mapping
const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  'TRP 全向辐射功率': <IconAntenna size={20} />,
  'TIS 全向灵敏度': <IconWifi size={20} />,
  'MIMO OTA 吞吐量': <IconRadar size={20} />,
  '信道模型验证': <IconChartLine size={20} />,
  '波束管理': <IconFlask size={20} />,
  '虚拟路测': <IconRoute size={20} />,
  '切换测试': <IconArrowsShuffle size={20} />,
};

const CATEGORY_COLORS: Record<string, string> = {
  'TRP 全向辐射功率': 'blue',
  'TIS 全向灵敏度': 'cyan',
  'MIMO OTA 吞吐量': 'violet',
  '信道模型验证': 'orange',
  '波束管理': 'teal',
  '虚拟路测': 'green',
  '切换测试': 'pink',
};

interface TestCaseLibraryProps {
  /** When set, shows checkboxes for multi-select mode (used by CreateTestPlanWizard) */
  selectionMode?: boolean;
  /** Currently selected test case IDs */
  selectedIds?: string[];
  /** Callback when selection changes */
  onSelectionChange?: (ids: string[]) => void;
  /** Callback to open create test case dialog */
  onCreateNew?: () => void;
}

export function TestCaseLibrary({
  selectionMode = false,
  selectedIds = [],
  onSelectionChange,
  onCreateNew,
}: TestCaseLibraryProps) {
  const [testCases, setTestCases] = useState<TestCaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<string | null>(null);

  const loadTestCases = useCallback(async () => {
    setLoading(true);
    try {
      const response = await listTestCases(0, 500, filterType as TestCaseType | undefined, true);
      setTestCases(response.items);
    } catch (error) {
      notifications.show({
        title: '加载失败',
        message: '无法加载测试用例库',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  }, [filterType]);

  useEffect(() => {
    loadTestCases();
  }, [loadTestCases]);

  // Group by template_category
  const grouped = testCases.reduce<Record<string, TestCaseSummary[]>>((acc, tc) => {
    const cat = (tc as any).template_category || '未分类';
    if (!acc[cat]) acc[cat] = [];

    // Apply search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchName = tc.name.toLowerCase().includes(q);
      const matchType = tc.test_type.toLowerCase().includes(q);
      const matchDesc = ((tc as any).description || '').toLowerCase().includes(q);
      const matchTags = ((tc as any).tags || []).some((t: string) => t.toLowerCase().includes(q));
      if (!matchName && !matchType && !matchDesc && !matchTags) return acc;
    }

    acc[cat].push(tc);
    return acc;
  }, {});

  // Remove empty groups
  const categories = Object.keys(grouped).filter((k) => grouped[k].length > 0);

  const toggleSelection = (id: string) => {
    if (!onSelectionChange) return;
    const newIds = selectedIds.includes(id)
      ? selectedIds.filter((x) => x !== id)
      : [...selectedIds, id];
    onSelectionChange(newIds);
  };

  const selectAllInCategory = (cat: string) => {
    if (!onSelectionChange) return;
    const catIds = grouped[cat].map((tc) => tc.id);
    const allSelected = catIds.every((id) => selectedIds.includes(id));
    if (allSelected) {
      onSelectionChange(selectedIds.filter((id) => !catIds.includes(id)));
    } else {
      const newIds = [...new Set([...selectedIds, ...catIds])];
      onSelectionChange(newIds);
    }
  };

  const formatDuration = (sec?: number) => {
    if (!sec) return '-';
    const min = Math.round(sec / 60);
    return min >= 60 ? `${Math.floor(min / 60)}h ${min % 60}m` : `${min} min`;
  };

  if (loading) {
    return (
      <Center py="xl">
        <Loader size="lg" />
      </Center>
    );
  }

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between" align="center">
        <Group gap="xs">
          <ThemeIcon size="lg" variant="light" color="brand">
            <IconChecklist size={20} />
          </ThemeIcon>
          <div>
            <Title order={4}>测试用例库</Title>
            <Text size="xs" c="dimmed">
              共 {testCases.length} 个标准测试用例模板，{categories.length} 个类别
            </Text>
          </div>
        </Group>
        {onCreateNew && (
          <Button
            leftSection={<IconPlus size={16} />}
            variant="light"
            size="compact-md"
            onClick={onCreateNew}
          >
            新建用例
          </Button>
        )}
      </Group>

      {/* Search & Filter Bar */}
      <Group gap="sm">
        <TextInput
          placeholder="搜索用例名称、标签..."
          leftSection={<IconSearch size={16} />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ flex: 1 }}
        />
        <Select
          placeholder="按类型筛选"
          clearable
          value={filterType}
          onChange={setFilterType}
          data={[
            { value: 'TRP', label: 'TRP - 辐射功率' },
            { value: 'TIS', label: 'TIS - 灵敏度' },
            { value: 'MIMO', label: 'MIMO 性能' },
            { value: 'Throughput', label: '吞吐量' },
            { value: 'ChannelModel', label: '信道模型' },
            { value: 'Handover', label: '切换测试' },
            { value: 'Custom', label: '自定义' },
          ]}
          w={180}
        />
      </Group>

      {/* Selection Summary */}
      {selectionMode && selectedIds.length > 0 && (
        <Paper p="sm" withBorder radius="md" bg="blue.0">
          <Group justify="space-between">
            <Text size="sm" fw={600} c="blue.8">
              已选择 {selectedIds.length} 个测试用例
            </Text>
            <Button
              size="compact-xs"
              variant="subtle"
              color="red"
              onClick={() => onSelectionChange?.([])}
            >
              清除全部
            </Button>
          </Group>
        </Paper>
      )}

      {/* Empty State */}
      {categories.length === 0 && (
        <Paper p="xl" withBorder radius="md">
          <Center>
            <Stack align="center" gap="sm">
              <IconChecklist size={48} color="gray" />
              <Text c="dimmed" ta="center">
                {searchQuery
                  ? `未找到匹配"${searchQuery}"的测试用例`
                  : '测试用例库为空，请先运行 seed_test_cases.py 初始化标准模板'}
              </Text>
            </Stack>
          </Center>
        </Paper>
      )}

      {/* Grouped Cards */}
      <Accordion variant="separated" radius="md" multiple defaultValue={categories}>
        {categories.map((cat) => {
          const items = grouped[cat];
          const color = CATEGORY_COLORS[cat] || 'gray';
          const icon = CATEGORY_ICONS[cat] || <IconFlask size={20} />;
          const catAllSelected =
            selectionMode && items.every((tc) => selectedIds.includes(tc.id));

          return (
            <Accordion.Item key={cat} value={cat}>
              <Accordion.Control
                icon={
                  <ThemeIcon size="sm" variant="light" color={color}>
                    {icon}
                  </ThemeIcon>
                }
              >
                <Group gap="sm">
                  <Text fw={600}>{cat}</Text>
                  <Badge size="sm" variant="light" color={color}>
                    {items.length}
                  </Badge>
                  {selectionMode && (
                    <Checkbox
                      size="xs"
                      checked={catAllSelected}
                      onChange={() => selectAllInCategory(cat)}
                      onClick={(e) => e.stopPropagation()}
                      label="全选"
                    />
                  )}
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
                  {items.map((tc) => (
                    <Paper
                      key={tc.id}
                      withBorder
                      radius="md"
                      p="md"
                      style={{
                        cursor: selectionMode ? 'pointer' : 'default',
                        borderColor: selectedIds.includes(tc.id)
                          ? `var(--mantine-color-${color}-5)`
                          : undefined,
                        borderWidth: selectedIds.includes(tc.id) ? 2 : 1,
                        backgroundColor: selectedIds.includes(tc.id)
                          ? `var(--mantine-color-${color}-0)`
                          : undefined,
                      }}
                      onClick={() => selectionMode && toggleSelection(tc.id)}
                    >
                      <Stack gap="xs">
                        <Group justify="space-between" align="flex-start" wrap="nowrap">
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <Group gap="xs" wrap="nowrap">
                              {selectionMode && (
                                <Checkbox
                                  size="sm"
                                  checked={selectedIds.includes(tc.id)}
                                  onChange={() => toggleSelection(tc.id)}
                                  onClick={(e) => e.stopPropagation()}
                                />
                              )}
                              <Text fw={600} size="sm" truncate>
                                {tc.name}
                              </Text>
                            </Group>
                          </div>
                          <Badge size="xs" variant="light" color={color}>
                            {getTestTypeLabel(tc.test_type)}
                          </Badge>
                        </Group>

                        {(tc as any).description && (
                          <Text size="xs" c="dimmed" lineClamp={2}>
                            {(tc as any).description}
                          </Text>
                        )}

                        <Divider />

                        <Group gap="lg">
                          {tc.frequency_mhz && (
                            <Tooltip label="中心频率">
                              <Text size="xs" c="dimmed">
                                📡 {tc.frequency_mhz} MHz
                              </Text>
                            </Tooltip>
                          )}
                          {(tc as any).bandwidth_mhz && (
                            <Tooltip label="带宽">
                              <Text size="xs" c="dimmed">
                                📶 {(tc as any).bandwidth_mhz} MHz
                              </Text>
                            </Tooltip>
                          )}
                          {tc.test_duration_sec && (
                            <Tooltip label="预计时长">
                              <Text size="xs" c="dimmed">
                                ⏱ {formatDuration(tc.test_duration_sec)}
                              </Text>
                            </Tooltip>
                          )}
                        </Group>

                        {(tc as any).tags && (tc as any).tags.length > 0 && (
                          <Group gap={4}>
                            {((tc as any).tags as string[]).map((tag) => (
                              <Badge key={tag} size="xs" variant="outline" color="gray">
                                {tag}
                              </Badge>
                            ))}
                          </Group>
                        )}
                      </Stack>
                    </Paper>
                  ))}
                </SimpleGrid>
              </Accordion.Panel>
            </Accordion.Item>
          );
        })}
      </Accordion>
    </Stack>
  );
}
