/**
 * GUI「新建测试用例」入口 — 轻量创建弹窗
 *
 * 设计稿: docs/design/gui-create-test-case-entry.md (2026-07-31 拍板, 全甲案)。
 * 原入口挂在 StepsTab 的 SaveAsTestCaseModal 上, 随 ARCH-1 S4a 计划链一并删除;
 * 本组件是那次显式申报的能力缺口的补齐。
 *
 * 两步流(建壳 → 编辑)的前半: 只收名称/起点/类别, 建完由父组件
 * (TestManagement) 直接打开 TestCaseEditModal 让用户在 MIMOOTAConfigForm
 * 里填仪表参数 —— 不在这里再造一份参数表单, 避免创建/编辑两套表单漂移。
 *
 * 关键语义(设计稿 §0.3 的洞):
 * - is_template 固定 true —— 库的可见性判据是 is_template=true
 *   (TestCaseLibrary 显式传参), 而后端 TestCaseCreate.is_template 默认 false,
 *   照默认建出来的用例会"建完即隐形"。此处必须显式置 true。
 * - test_type 固定 MIMO_OTA 不给选 —— 执行正门 (test_case_runner) 对其它
 *   类型 422, 给选 = 给用户造一个建完跑不了的坑。
 * - configuration 允许为空 {} —— 空配置合法(54 字段全有默认), 执行时工厂
 *   fail-loud 校验。"先建壳再填参"是有意的捷径, 不是静默兜底(拍板③)。
 * - created_by 固定 "gui" —— GUI 今天无认证上下文(拍板④), 接上后换真实用户。
 */
import { useEffect, useRef, useState } from 'react'
import {
  Modal,
  Stack,
  TextInput,
  Select,
  Button,
  Group,
  Text,
} from '@mantine/core'
import { IconPlus, IconX } from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import {
  createTestCase,
  getTestCase,
  listTestCases,
  type TestCaseSummary,
} from '../../api/testPlanService'
import {
  fetchAllLabProfiles,
  type LabProfileSummary,
} from '../../api/labProfileService'
import { logFrontendEvent } from '../../observability/frontendLogger'

/** 空白起点的哨兵值 (Select 的 value 只能是 string) */
const BLANK_START = '__blank__'
const UNBOUND_LAB = '__unbound__'
const DEFAULT_CATEGORY = '我的用例'

interface TestCaseCreateModalProps {
  opened: boolean
  onClose: () => void
  /** 创建成功后回调新用例 id — 父组件接着打开编辑弹窗填参数 */
  onCreated: (id: string) => void
}

export function TestCaseCreateModal({
  opened,
  onClose,
  onCreated,
}: TestCaseCreateModalProps) {
  const [name, setName] = useState('')
  const [startFrom, setStartFrom] = useState<string>(BLANK_START)
  const [category, setCategory] = useState(DEFAULT_CATEGORY)
  const [templates, setTemplates] = useState<TestCaseSummary[]>([])
  const [labs, setLabs] = useState<LabProfileSummary[]>([])
  const [labsLoading, setLabsLoading] = useState(false)
  const [labsError, setLabsError] = useState<string | null>(null)
  const [selectedLabId, setSelectedLabId] = useState(UNBOUND_LAB)
  const [loadingTemplate, setLoadingTemplate] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const templateRequestId = useRef(0)
  const activeLabs = labs.filter((item) => item.is_active)
  const selectedLab = labs.find((item) => item.id === selectedLabId)
  const labSelectionInvalid =
    labsLoading || labsError !== null
    || (activeLabs.length > 1 && selectedLabId === UNBOUND_LAB)
    || (selectedLabId !== UNBOUND_LAB && selectedLab?.is_active !== true)

  useEffect(() => {
    if (!opened) return
    // 每次打开重置表单 + 拉可选起点(现有 MIMO_OTA 模板)。
    // 拉取失败不阻塞 — 起点是可选项, 空白照样能建。
    setName('')
    setStartFrom(BLANK_START)
    setCategory(DEFAULT_CATEGORY)
    setLabs([])
    setLabsLoading(true)
    setLabsError(null)
    setSelectedLabId(UNBOUND_LAB)
    setLoadingTemplate(false)
    templateRequestId.current += 1
    let cancelled = false
    listTestCases(0, 500, 'MIMO_OTA', true)
      .then((res) => {
        if (!cancelled) setTemplates(res.items)
      })
      .catch(() => {
        if (!cancelled) setTemplates([])
      })
    fetchAllLabProfiles()
      .then((items) => {
        if (cancelled) return
        setLabs(items)
        const active = items.filter((item) => item.is_active)
        if (active.length === 1) setSelectedLabId(active[0].id)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setLabs([])
        setLabsError((error as Error)?.message || '无法加载 LabProfile 列表')
      })
      .finally(() => {
        if (!cancelled) setLabsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [opened])

  const handleStartChange = async (value: string | null) => {
    const next = value ?? BLANK_START
    const requestId = ++templateRequestId.current
    setStartFrom(next)
    if (next === BLANK_START) {
      setLoadingTemplate(false)
      const active = labs.filter((item) => item.is_active)
      setSelectedLabId(active.length === 1 ? active[0].id : UNBOUND_LAB)
      return
    }
    setLoadingTemplate(true)
    try {
      const tpl = await getTestCase(next)
      if (requestId === templateRequestId.current) {
        setSelectedLabId(tpl.lab_profile_id ?? UNBOUND_LAB)
      }
    } catch (error) {
      if (requestId !== templateRequestId.current) return
      setSelectedLabId(UNBOUND_LAB)
      notifications.show({
        title: '模板加载失败',
        message: (error as Error)?.message || '无法复制模板的 LabProfile 绑定',
        color: 'red',
      })
    } finally {
      if (requestId === templateRequestId.current) {
        setLoadingTemplate(false)
      }
    }
  }

  const handleCreate = async () => {
    const trimmed = name.trim()
    if (!trimmed) return
    setSubmitting(true)
    try {
      // 起点选了模板 → 复制它的 configuration 当初值; 空白 → {}
      let configuration: Record<string, unknown> = {}
      if (startFrom !== BLANK_START) {
        const tpl = await getTestCase(startFrom)
        const cfg = tpl.configuration
        if (cfg && typeof cfg === 'object' && !Array.isArray(cfg)) {
          configuration = cfg
        }
      }
      const created = await createTestCase({
        name: trimmed,
        test_type: 'MIMO_OTA',
        configuration,
        is_template: true,
        template_category: category.trim() || DEFAULT_CATEGORY,
        created_by: 'gui',
        lab_profile_id:
          selectedLabId === UNBOUND_LAB ? null : selectedLabId,
      })
      notifications.show({
        title: '用例已创建',
        message: `${trimmed} — 接下来在编辑页填仪表参数`,
        color: 'green',
        icon: <IconPlus size={18} />,
      })
      logFrontendEvent({
        action: 'test_case.create.saved',
        component: 'TestCaseCreateModal',
        message: `id=${created.id} name="${trimmed}" start=${
          startFrom === BLANK_START ? 'blank' : startFrom
        }`,
      })
      onCreated(created.id)
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail
      notifications.show({
        title: '创建失败',
        message:
          typeof detail === 'string'
            ? detail
            : (e as Error)?.message || '无法创建测试用例',
        color: 'red',
        icon: <IconX size={18} />,
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="新建测试用例 (MIMO_OTA)"
      size="md"
      centered
      closeOnEscape={!submitting}
      closeOnClickOutside={!submitting}
      closeButtonProps={{ disabled: submitting }}
    >
      <Stack gap="md">
        <TextInput
          label="名称"
          placeholder="例如: 3.5GHz 4方位吞吐验证"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={255}
          data-autofocus
        />
        <Select
          label="起点"
          description="选一个现有模板把它的参数复制过来当起点, 或从空白开始"
          value={startFrom}
          onChange={handleStartChange}
          data={[
            { value: BLANK_START, label: '空白 (全默认参数)' },
            ...templates.map((t) => ({ value: t.id, label: t.name })),
          ]}
          allowDeselect={false}
          disabled={labsLoading || labsError !== null}
        />
        <Select
          label="LabProfile"
          description="绑定后执行使用该实验室的暗室与仪表；从模板开始时会复制其绑定"
          value={selectedLabId}
          onChange={(value) => setSelectedLabId(value ?? UNBOUND_LAB)}
          data={[
            { value: UNBOUND_LAB, label: '不绑定（执行时要求唯一活动 LabProfile）' },
            ...labs.map((lab) => ({
              value: lab.id,
              label: `${lab.name}${lab.is_active ? '' : '（已停用）'}`,
              disabled: !lab.is_active,
            })),
          ]}
          allowDeselect={false}
          disabled={labsLoading || labsError !== null}
          error={
            labsError
              ?? (labSelectionInvalid
              ? '多个活动 LabProfile 时必须选择一个可用实验室'
              : undefined)
          }
        />
        <TextInput
          label="类别"
          description="决定用例在库里归到哪一组"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          maxLength={100}
        />
        <Text size="xs" c="dimmed">
          仪表参数在创建后的编辑页里填, 执行时会做严格校验 —— 未配置的项
          走系统默认值。
        </Text>
        <Group justify="flex-end" gap="sm">
          <Button variant="default" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={handleCreate}
            loading={submitting || loadingTemplate || labsLoading}
            disabled={
              !name.trim()
              || loadingTemplate
              || labsLoading
              || labsError !== null
              || labSelectionInvalid
            }
          >
            创建并配置参数
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
