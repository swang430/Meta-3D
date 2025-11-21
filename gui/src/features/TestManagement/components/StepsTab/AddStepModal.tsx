/**
 * Add Step Modal Component
 *
 * Modal for adding new steps from the sequence library.
 */

import { useState } from 'react'
import {
  Modal,
  Stack,
  TextInput,
  Select,
  Table,
  Button,
  Group,
  Text,
  Badge,
  Paper,
  ActionIcon,
  Loader,
  Center,
} from '@mantine/core'
import { IconSearch, IconPlus, IconStar } from '@tabler/icons-react'
import { useSequenceLibrary, useSequenceCategories, useAddTestStep } from '../../hooks'

interface AddStepModalProps {
  opened: boolean
  onClose: () => void
  planId: string
}

export function AddStepModal({ opened, onClose, planId }: AddStepModalProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)

  // Query hooks
  const { data: sequenceItems, isLoading } = useSequenceLibrary({
    category: categoryFilter || undefined,
    search: searchQuery || undefined,
  })
  const { data: categories } = useSequenceCategories()
  const { mutate: addStep, isPending } = useAddTestStep()

  const handleAddStep = (sequenceLibraryId: string) => {
    addStep(
      {
        planId,
        payload: {
          sequence_library_id: sequenceLibraryId,
          order: 999, // Will be appended to end
        },
      },
      {
        onSuccess: () => {
          onClose()
          // Reset filters
          setSearchQuery('')
          setCategoryFilter(null)
        },
      },
    )
  }

  const categoryOptions = categories?.map((cat) => ({ value: cat, label: cat })) || []

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="从序列库添加步骤"
      size="xl"
    >
      <Stack gap="md">
        {/* Filters */}
        <Group>
          <TextInput
            placeholder="搜索步骤..."
            leftSection={<IconSearch size={16} />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <Select
            placeholder="分类筛选"
            clearable
            value={categoryFilter}
            onChange={setCategoryFilter}
            data={categoryOptions}
            style={{ width: 200 }}
          />
        </Group>

        {/* Sequence Library Table */}
        <Paper withBorder style={{ maxHeight: 500, overflow: 'auto' }}>
          {isLoading ? (
            <Center p="xl">
              <Loader size="sm" />
            </Center>
          ) : (
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>名称</Table.Th>
                  <Table.Th>分类</Table.Th>
                  <Table.Th>使用次数</Table.Th>
                  <Table.Th style={{ width: 80 }}>操作</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sequenceItems?.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={4}>
                      <Text ta="center" c="dimmed" py="md">
                        未找到匹配的序列
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ) : (
                  sequenceItems?.map((item) => (
                    <Table.Tr key={item.id}>
                      <Table.Td>
                        <Stack gap={2}>
                          <Group gap="xs">
                            <Text size="sm" fw={500}>
                              {item.title}
                            </Text>
                            {item.popularity_score > 80 && (
                              <Badge
                                size="xs"
                                variant="light"
                                color="yellow"
                                leftSection={<IconStar size={10} />}
                              >
                                热门
                              </Badge>
                            )}
                          </Group>
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            {item.description}
                          </Text>
                        </Stack>
                      </Table.Td>
                      <Table.Td>
                        <Badge size="sm" variant="dot">
                          {item.category}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" c="dimmed">
                          {item.usage_count}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <ActionIcon
                          variant="light"
                          color="blue"
                          onClick={() => handleAddStep(item.id)}
                          loading={isPending}
                        >
                          <IconPlus size={16} />
                        </ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  ))
                )}
              </Table.Tbody>
            </Table>
          )}
        </Paper>

        {/* Actions */}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            关闭
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export default AddStepModal
