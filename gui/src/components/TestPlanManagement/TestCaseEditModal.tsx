/**
 * Phase 3b: TestCaseLibrary "edit" 入口
 *
 * 用户从 TestCaseLibrary 卡片直接打开此 Modal 修改 TestCase 元数据(name /
 * description / tags) + configuration JSON, 不需要先把 case 加到 TestPlan
 * 再走 StepsTab 间接编辑。
 *
 * v1: configuration 是 raw JSON 文本编辑(对所有 test_type 通用)。
 * v2 (ARCH-1 S4a): MIMO_OTA 类改用 MIMOOTAConfigForm 类型化表单, 其它类继续
 * raw JSON —— 兑现 v1 注释里写的"将来"。
 *
 * ⚠️ 这不是新功能, 是**换挂载点**: 该表单原先只能从「步骤编排」Tab 进去
 * (StepsTab → StepEditor), 而那条路要先选一个 TestPlan。计划链拆掉后
 * 若不搬家, 操作员配 MIMO_OTA 仪表参数就只剩裸 JSON 文本框 —— 那是实打实的
 * 能力倒退。搬完这里, StepsTab 才可以删。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
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
  Select,
} from '@mantine/core'
import {
  IconAlertCircle,
  IconDeviceFloppy,
  IconRefresh,
  IconX,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import {
  getTestCase,
  updateTestCase,
  updateTestCaseExecutionPolicy,
  type TestCase,
} from '../../api/testPlanService'
import {
  MIMOOTAConfigForm,
  type MIMOOTAConfiguration,
} from '../TestCaseConfig/MIMOOTAConfigForm'
import { logFrontendEvent } from '../../observability/frontendLogger'
import {
  fetchAllLabProfiles,
  type LabProfileSummary,
} from '../../api/labProfileService'
import {
  buildLabProfileBindingPatch,
  labProfileSelectionDisabled,
} from '../../features/TestManagement/testCaseLabProfileBinding'
import { validateMacProfileDraftForSave } from '../../types/macTestProfile'

/** 有类型化配置表单的用例类型。其余走 raw JSON。 */
const TYPED_CONFIG_CASE_TYPE = 'MIMO_OTA'
const UNBOUND_LAB = '__unbound__'

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
  const [mimoConfig, setMimoConfig] = useState<MIMOOTAConfiguration>({})
  const [labs, setLabs] = useState<LabProfileSummary[]>([])
  const [labsLoading, setLabsLoading] = useState(false)
  const [labsError, setLabsError] = useState<string | null>(null)
  const [labsReady, setLabsReady] = useState(false)
  const [originalLabProfileId, setOriginalLabProfileId] = useState<string | null>(null)
  const [selectedLabId, setSelectedLabId] = useState(UNBOUND_LAB)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [policyMode, setPolicyMode] = useState<'formal' | 'diagnostic'>('formal')
  const [originalPolicyMode, setOriginalPolicyMode] = useState<'formal' | 'diagnostic'>('formal')
  const [policyReason, setPolicyReason] = useState('')
  const [policyUpdatedBy, setPolicyUpdatedBy] = useState('')
  const labRequestId = useRef(0)

  // 类型化表单只对 MIMO_OTA 生效; 其余 test_type 仍是 raw JSON。
  const useTypedForm = tc?.test_type === TYPED_CONFIG_CASE_TYPE
  const labSelectionIsDisabled = labProfileSelectionDisabled({
    labsLoading,
    labsError,
  })
  const selectedLabMissing =
    selectedLabId !== UNBOUND_LAB
    && !labs.some((lab) => lab.id === selectedLabId)
  const compatibilityContextSaved = Boolean(
    tc
    && JSON.stringify(mimoConfig) === JSON.stringify(tc.configuration ?? {})
    && selectedLabId === (originalLabProfileId ?? UNBOUND_LAB),
  )
  const labOptions = [
    { value: UNBOUND_LAB, label: '不绑定（执行时自动解析）' },
    ...(selectedLabMissing
      ? [{
          value: selectedLabId,
          label: labsReady
            ? `当前绑定 ${selectedLabId}（已不可用）`
            : `当前绑定 ${selectedLabId}（列表未加载）`,
          disabled: true,
        }]
      : []),
    ...labs.map((lab) => ({
      value: lab.id,
      label: `${lab.name}${lab.is_active ? '' : '（已停用）'}`,
      disabled: !lab.is_active,
    })),
  ]

  const loadLabProfiles = useCallback(async () => {
    const requestId = ++labRequestId.current
    setLabsLoading(true)
    setLabsError(null)
    setLabsReady(false)
    try {
      const items = await fetchAllLabProfiles()
      if (requestId !== labRequestId.current) return
      setLabs(items)
      setLabsReady(true)
    } catch (error: unknown) {
      if (requestId !== labRequestId.current) return
      const detail = (
        error as { response?: { data?: { detail?: unknown } } }
      )?.response?.data?.detail
      setLabs([])
      setLabsError(
        typeof detail === 'string' && detail.trim()
          ? detail
          : (error as Error)?.message || '无法加载 LabProfile 列表',
      )
    } finally {
      if (requestId === labRequestId.current) setLabsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!opened || !testCaseId) return
    let cancelled = false
    setLoading(true)
    setJsonError(null)
    setTc(null)
    setLabs([])
    setLabsError(null)
    setLabsReady(false)
    void loadLabProfiles()
    getTestCase(testCaseId)
      .then((data) => {
        if (cancelled) return
        setTc(data)
        const binding = data.lab_profile_id ?? null
        setOriginalLabProfileId(binding)
        setSelectedLabId(binding ?? UNBOUND_LAB)
        setName(data.name || '')
        setDescription(data.description || '')
        setTags((data as unknown as { tags?: string[] }).tags || [])
        setConfigText(JSON.stringify(data.configuration ?? {}, null, 2))
        // 两路都填: test_type 决定保存时取哪一路 (见 handleSave)。
        // configuration 可能是 null / 非对象 (旧数据), 表单要的是对象。
        const cfg = data.configuration
        setMimoConfig(
          cfg && typeof cfg === 'object' && !Array.isArray(cfg)
            ? (cfg as MIMOOTAConfiguration)
            : {},
        )
        const mode = data.execution_policy?.mode === 'diagnostic' ? 'diagnostic' : 'formal'
        setPolicyMode(mode)
        setOriginalPolicyMode(mode)
        setPolicyReason('')
        setPolicyUpdatedBy('')
      })
      .catch((e) => {
        if (cancelled) return
        notifications.show({
          title: '加载失败',
          message: (e as Error)?.message || '无法获取 TestCase',
          color: 'red',
        })
        onClose()
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      labRequestId.current += 1
    }
    // ⚠️ deps 只放"开了 + 换用例"。onClose 只在 catch 分支用, 而调用点
    // (TestCaseLibrary) 传的是内联箭头 —— 每次父组件重渲染都换引用。
    // 父组件有 2 秒执行轮询, 把 onClose 放进 deps 会让本 effect 每 2 秒重跑一次,
    // 用服务端旧值覆盖用户正在编辑的 60+ 项仪表参数 (内审 F3)。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, testCaseId, loadLabProfiles])

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
    // 类型化表单没有 JSON 解析这一步, jsonError 只约束 raw JSON 那一路。
    if (!testCaseId || (!useTypedForm && jsonError)) return
    const policyChanged = policyMode !== originalPolicyMode
    if (policyChanged && (!policyReason.trim() || !policyUpdatedBy.trim())) {
      setJsonError('切换 Diagnostic / Formal 必须填写操作人和原因')
      return
    }
    if (useTypedForm) {
      const macProfileError = validateMacProfileDraftForSave(mimoConfig)
      if (macProfileError) {
        setJsonError(macProfileError)
        return
      }
      setJsonError(null)
    }
    setSaving(true)
    try {
      const config = useTypedForm ? mimoConfig : JSON.parse(configText)
      const selectedLabProfileId =
        selectedLabId === UNBOUND_LAB ? null : selectedLabId
      const updated = await updateTestCase(testCaseId, {
        name,
        description: description || null,
        tags,
        configuration: config,
        ...buildLabProfileBindingPatch({
          labsReady,
          originalLabProfileId,
          selectedLabProfileId,
        }),
      })
      if (policyChanged) {
        updated.execution_policy = await updateTestCaseExecutionPolicy(testCaseId, {
          mode: policyMode,
          reason: policyReason.trim(),
          updated_by: policyUpdatedBy.trim(),
        })
      }
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
          <Select
            label="执行资格"
            description="Formal 仍须由当前现场认证与本次冻结证据共同放行；Diagnostic 只生成黄色审计结果，不进入正式 KPI。"
            value={policyMode}
            onChange={(value) => setPolicyMode(value === 'diagnostic' ? 'diagnostic' : 'formal')}
            data={[
              { value: 'formal', label: 'Formal（正式）' },
              { value: 'diagnostic', label: 'Diagnostic（仅可诊断）' },
            ]}
            allowDeselect={false}
          />
          {policyMode !== originalPolicyMode && (
            <Group grow align="flex-start">
              <TextInput
                required
                label="操作人"
                value={policyUpdatedBy}
                onChange={(event) => setPolicyUpdatedBy(event.currentTarget.value)}
              />
              <Textarea
                required
                label="切换原因"
                value={policyReason}
                onChange={(event) => setPolicyReason(event.currentTarget.value)}
                minRows={2}
              />
            </Group>
          )}
          <Select
            label="LabProfile"
            description="绑定后执行使用该实验室的暗室与仪表；不绑定时要求系统只有一个活动 LabProfile"
            value={selectedLabId}
            onChange={(value) => setSelectedLabId(value ?? UNBOUND_LAB)}
            data={labOptions}
            allowDeselect={false}
            disabled={labSelectionIsDisabled}
            rightSection={labsLoading ? <Loader size="xs" /> : undefined}
          />

          {labsError && (
            <Alert
              color="red"
              variant="light"
              icon={<IconAlertCircle size={18} />}
              title="LabProfile 列表不可用"
            >
              <Stack gap="xs">
                <span>
                  {labsError}。当前绑定保持不变；仍可保存其它 TestCase 字段。
                </span>
                <Group>
                  <Button
                    size="xs"
                    variant="light"
                    leftSection={<IconRefresh size={14} />}
                    onClick={() => void loadLabProfiles()}
                  >
                    重试加载
                  </Button>
                </Group>
              </Stack>
            </Alert>
          )}

          {useTypedForm ? (
            <>
              {jsonError ? (
                <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />}>
                  {jsonError}
                </Alert>
              ) : null}
              <MIMOOTAConfigForm
                value={mimoConfig}
                onChange={setMimoConfig}
                testCaseId={testCaseId}
                labProfileId={selectedLabId === UNBOUND_LAB ? null : selectedLabId}
                compatibilityContextSaved={compatibilityContextSaved}
              />
            </>
          ) : (
            <>
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
            </>
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
