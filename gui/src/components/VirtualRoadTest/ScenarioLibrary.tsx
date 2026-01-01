/**
 * 场景库组件
 * 浏览和管理路测场景
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Group,
  TextInput,
  Select,
  Button,
  SimpleGrid,
  Text,
  Loader,
  Alert,
  Stack,
  Center,
} from '@mantine/core'
import { IconSearch, IconPlus, IconAlertCircle, IconBooks } from '@tabler/icons-react'
import { fetchScenarios } from '../../api/roadTestService'
import type { ScenarioCategory, TestMode } from '../../types/roadTest'
import ScenarioCard from './ScenarioCard'
import { CreateScenarioDialog } from './CreateScenarioDialog'

// 场景分类
const CATEGORIES: { value: ScenarioCategory; label: string }[] = [
  { value: 'standard', label: '标准认证 (3GPP/CTIA)' },
  { value: 'functional', label: '功能测试' },
  { value: 'performance', label: '性能测试' },
  { value: 'environment', label: '环境测试' },
  { value: 'extreme', label: '极端场景' },
  { value: 'custom', label: '自定义' },
]

interface ScenarioLibraryProps {
  testMode?: TestMode
}

export default function ScenarioLibrary({ testMode }: ScenarioLibraryProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<ScenarioCategory | null>(null)
  const [selectedSource, setSelectedSource] = useState<'standard' | 'custom' | null>(null)
  const [createDialogOpened, setCreateDialogOpened] = useState(false)

  // 获取场景列表
  const {
    data: scenarios,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['scenarios', selectedCategory, selectedSource],
    queryFn: () =>
      fetchScenarios({
        category: selectedCategory || undefined,
        source: selectedSource || undefined,
      }),
  })

  // 按搜索词过滤场景
  const filteredScenarios = scenarios?.filter((s) => {
    const query = searchQuery.toLowerCase()
    return (
      s.name.toLowerCase().includes(query) ||
      s.description?.toLowerCase().includes(query) ||
      s.tags.some((tag) => tag.toLowerCase().includes(query))
    )
  })

  return (
    <Stack gap="md">
      {/* 筛选栏 */}
      <Group>
        <TextInput
          placeholder="搜索场景名称、描述或标签..."
          leftSection={<IconSearch size={16} />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.currentTarget.value)}
          style={{ flex: 1 }}
        />

        <Select
          placeholder="场景分类"
          value={selectedCategory}
          onChange={(value) => setSelectedCategory(value as ScenarioCategory | null)}
          data={[{ value: '', label: '全部分类' }, ...CATEGORIES]}
          clearable
          style={{ width: 180 }}
        />

        <Select
          placeholder="来源"
          value={selectedSource}
          onChange={(value) => setSelectedSource(value as 'standard' | 'custom' | null)}
          data={[
            { value: '', label: '全部来源' },
            { value: 'standard', label: '标准场景' },
            { value: 'custom', label: '自定义场景' },
          ]}
          clearable
          style={{ width: 140 }}
        />

        <Button
          leftSection={<IconPlus size={16} />}
          variant="light"
          onClick={() => setCreateDialogOpened(true)}
        >
          创建场景
        </Button>
      </Group>

      {/* 加载状态 */}
      {isLoading && (
        <Center py="xl">
          <Loader size="md" />
          <Text c="dimmed" ml="md">
            加载场景中...
          </Text>
        </Center>
      )}

      {/* 错误状态 */}
      {error && (
        <Alert icon={<IconAlertCircle size={16} />} title="加载失败" color="red">
          无法加载场景列表: {(error as Error).message}
        </Alert>
      )}

      {/* 空状态 */}
      {filteredScenarios && filteredScenarios.length === 0 && (
        <Center py="xl">
          <Stack align="center" gap="sm">
            <IconBooks size={48} stroke={1.5} color="gray" />
            <Text c="dimmed" ta="center">
              未找到匹配的场景
            </Text>
            <Text size="sm" c="dimmed" ta="center">
              尝试调整筛选条件或创建新场景
            </Text>
          </Stack>
        </Center>
      )}

      {/* 场景列表 */}
      {filteredScenarios && filteredScenarios.length > 0 && (
        <>
          <Text size="sm" c="dimmed">
            共找到 {filteredScenarios.length} 个场景
          </Text>

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md" verticalSpacing="md">
            {filteredScenarios.map((scenario) => (
              <ScenarioCard
                key={scenario.id}
                scenario={scenario}
                testMode={testMode}
                onRefresh={refetch}
              />
            ))}
          </SimpleGrid>
        </>
      )}

      {/* 创建场景对话框 */}
      <CreateScenarioDialog
        opened={createDialogOpened}
        onClose={() => {
          setCreateDialogOpened(false)
          refetch()
        }}
        testMode={testMode}
      />
    </Stack>
  )
}
