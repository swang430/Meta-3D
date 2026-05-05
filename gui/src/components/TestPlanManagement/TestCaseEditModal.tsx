/**
 * Phase 3b: TestCaseLibrary "edit" 入口
 *
 * 用户从 TestCaseLibrary 卡片直接打开此 Modal 修改 TestCase 元数据(name /
 * description / tags) + configuration JSON, 不需要先把 case 加到 TestPlan
 * 再走 StepsTab 间接编辑。
 *
 * v1: configuration 是 raw JSON 文本编辑(对所有 test_type 通用)。
 * 将来可针对 MIMO_OTA 类复用 MIMOOTAConfigForm, 其它类继续 raw JSON。
 */
import { useEffect, useState } from 'react'
import {
  Modal,
  Stack,
  TextInput,
  Textarea,
  Button,
  Group,
  Loader,
  Center,
  Alert,
  Code,
  TagsInput,
} from '@mantine/core'
import { IconAlertCircle, IconDeviceFloppy, IconX } from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import {
  getTestCase,
  updateTestCase,
  type TestCase,
} from '../../api/testPlanService'
import { logFrontendEvent } from '../../observability/frontendLogger'

interface TestCaseEditModalProps {
  opened: boolean
  testCaseId: string | null
  onClose: () => void
  onSaved?: (updated: TestCase) => void
}

export function TestCaseEditModal({
  opened,
  testCaseId,
  onClose,
  onSaved,
}: TestCaseEditModalProps) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [tc, setTc] = useState<TestCase | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [configText, setConfigText] = useState('{}')
  const [jsonError, setJsonError] = useState<string | null>(null)

  useEffect(() => {
    if (!opened || !testCaseId) return
    setLoading(true)
    setJsonError(null)
    getTestCase(testCaseId)
      .then((data) => {
        setTc(data)
        setName(data.name || '')
        setDescription(data.description || '')
        setTags((data as unknown as { tags?: string[] }).tags || [])
        setConfigText(JSON.stringify(data.configuration ?? {}, null, 2))
      })
      .catch((e) => {
        notifications.show({
          title: '加载失败',
          message: (e as Error)?.message || '无法获取 TestCase',
          color: 'red',
        })
        onClose()
      })
      .finally(() => setLoading(false))
  }, [opened, testCaseId, onClose])

  const handleConfigChange = (text: string) => {
    setConfigText(text)
    if (!text.trim()) {
      setJsonError('configuration 不能为空')
      return
    }
    try {
      JSON.parse(text)
      setJsonError(null)
    } catch (e) {
      setJsonError(`JSON 解析错误: ${(e as Error).message}`)
    }
  }

  const handleSave = async () => {
    if (!testCaseId || jsonError) return
    setSaving(true)
    try {
      const config = JSON.parse(configText)
      const updated = await updateTestCase(testCaseId, {
        name,
        description: description || null,
        tags,
        configuration: config,
      })
      notifications.show({
        title: 'TestCase 已更新',
        message: name,
        color: 'green',
        icon: <IconDeviceFloppy size={18} />,
      })
      logFrontendEvent({
        action: 'test_case.edit.saved',
        component: 'TestCaseEditModal',
        message: `id=${testCaseId} type=${tc?.test_type} name="${name}"`,
      })
      onSaved?.(updated)
      onClose()
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e as Error)?.message ||
        '保存失败'
      notifications.show({
        title: '保存失败',
        message: detail,
        color: 'red',
        icon: <IconAlertCircle size={18} />,
      })
      logFrontendEvent({
        level: 'ERROR',
        action: 'test_case.edit.save_failed',
        component: 'TestCaseEditModal',
        error: detail,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      size="xl"
      title={
        tc ? (
          <Group gap="xs">
            <span>编辑 TestCase</span>
            <Code>{tc.test_type}</Code>
          </Group>
        ) : (
          '编辑 TestCase'
        )
      }
    >
      {loading ? (
        <Center py="xl">
          <Loader size="md" />
        </Center>
      ) : !tc ? null : (
        <Stack gap="md">
          <TextInput
            label="名称"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            required
          />
          <Textarea
            label="描述"
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
            minRows={2}
            autosize
          />
          <TagsInput
            label="标签"
            value={tags}
            onChange={setTags}
            placeholder="按回车添加..."
          />

          <Textarea
            label="Configuration (JSON)"
            description={`原始 JSON 编辑; 字段含义见 ${tc.test_type} schema 文档`}
            value={configText}
            onChange={(e) => handleConfigChange(e.currentTarget.value)}
            minRows={12}
            autosize
            styles={{ input: { fontFamily: 'monospace', fontSize: 12 } }}
            error={jsonError || undefined}
          />

          {jsonError && (
            <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />}>
              {jsonError}
            </Alert>
          )}

          <Group justify="flex-end">
            <Button
              variant="default"
              leftSection={<IconX size={16} />}
              onClick={onClose}
              disabled={saving}
            >
              取消
            </Button>
            <Button
              leftSection={<IconDeviceFloppy size={16} />}
              onClick={handleSave}
              disabled={saving || !!jsonError || !name}
              loading={saving}
            >
              保存
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  )
}
