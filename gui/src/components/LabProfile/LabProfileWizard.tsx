/**
 * Lab Profile init wizard — P0-2 (first-call roadmap).
 *
 * Why this exists
 * ---------------
 * Even with the DB auto-bootstrap (P0-1) seeding chamber presets and an
 * instrument-model catalog, a fresh deploy still has zero LabProfile rows,
 * so the calibration / measurement UI has nothing to operate against.
 * Operators don't know that they need to clone a preset → bind instruments
 * → create a profile. This 3-step wizard makes that the first thing they
 * see on first launch.
 *
 * 3 steps (scope-decided 2026-05-14; the 4th "edit chamber dimensions"
 * step was deferred to the existing chamber-config tab to keep the
 * wizard small):
 *   1. Pick chamber template + name lab
 *   2. Bind instruments (model + endpoint per category)
 *   3. Confirm + create LabProfile
 *
 * Resumability
 * ------------
 * Wizard state is persisted to localStorage on every change, so a browser
 * refresh mid-wizard puts the operator back on the step they were on with
 * their entries intact. Cleared on successful create or explicit cancel.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Badge,
  Button,
  Card,
  Container,
  Group,
  Loader,
  SegmentedControl,
  Select,
  Stack,
  Stepper,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconAlertCircle,
  IconArrowLeft,
  IconArrowRight,
  IconCheck,
  IconInfoCircle,
} from '@tabler/icons-react'

import {
  createChamberFromTemplate,
  fetchChamberPresets,
  fetchInstrumentCatalog,
  updateInstrumentCategory,
} from '../../api/service'
import {
  createLabProfile,
  type InstrumentBindingPayload,
} from '../../api/labProfileService'
import type { ChamberType } from '../../types/api'

const WIZARD_STORAGE_KEY = 'mimo-first-lab-wizard-state-v1'

type DriverMode = 'auto' | 'mock' | 'real'

// Per-category form state the operator fills in step 2. Stored alongside
// `categoryKey` so a refresh restores each row even if the catalog
// reorders between fetches.
interface BindingDraft {
  categoryKey: string
  categoryLabel: string
  modelId: string | null
  endpoint: string
  driverMode: DriverMode
}

interface WizardState {
  active: number
  labName: string
  selectedPresetType: ChamberType | null
  /** Set after step-1 → step-2 transition; the chamber row exists in DB. */
  duplicatedChamberId: string | null
  duplicatedChamberName: string | null
  bindings: BindingDraft[]
}

const EMPTY_STATE: WizardState = {
  active: 0,
  labName: '',
  selectedPresetType: null,
  duplicatedChamberId: null,
  duplicatedChamberName: null,
  bindings: [],
}

function loadPersisted(): WizardState {
  try {
    const raw = localStorage.getItem(WIZARD_STORAGE_KEY)
    if (!raw) return EMPTY_STATE
    const parsed = JSON.parse(raw) as Partial<WizardState>
    return { ...EMPTY_STATE, ...parsed }
  } catch {
    // Corrupt JSON in a previous session shouldn't wedge the wizard.
    return EMPTY_STATE
  }
}

interface LabProfileWizardProps {
  /** Called after the operator successfully creates a profile or
   *  cancels — parent re-fetches `/lab-profiles` and re-evaluates the
   *  no-lab-profile gate. */
  onComplete: () => void
}

export function LabProfileWizard({ onComplete }: LabProfileWizardProps) {
  const queryClient = useQueryClient()
  const [state, setState] = useState<WizardState>(loadPersisted)

  // Persist on every state change. Cheap; ~1KB JSON.
  useEffect(() => {
    try {
      localStorage.setItem(WIZARD_STORAGE_KEY, JSON.stringify(state))
    } catch {
      // localStorage full / disabled — wizard still works in-session.
    }
  }, [state])

  const presetsQuery = useQuery({
    queryKey: ['chamber-presets'],
    queryFn: fetchChamberPresets,
  })

  const catalogQuery = useQuery({
    queryKey: ['instruments-catalog'],
    queryFn: fetchInstrumentCatalog,
  })

  // Seed bindings from the catalog the first time it loads. Each
  // category gets one editable row, prefilled from any existing
  // backend-side selection so the operator can review-and-confirm
  // rather than re-enter what's already configured.
  useEffect(() => {
    if (!catalogQuery.data) return
    if (state.bindings.length > 0) return
    const seeded: BindingDraft[] = catalogQuery.data.categories.map((cat) => ({
      categoryKey: cat.key,
      categoryLabel: cat.label,
      modelId: cat.selectedModelId,
      endpoint: cat.connection.endpoint ?? '',
      driverMode: 'auto',
    }))
    setState((s) => ({ ...s, bindings: seeded }))
  }, [catalogQuery.data, state.bindings.length])

  const fromPresetMutation = useMutation({
    mutationFn: createChamberFromTemplate,
  })

  const updateCategoryMutation = useMutation({
    mutationFn: ({ key, payload }: {
      key: string
      payload: { modelId?: string; connection?: { endpoint?: string } }
    }) => updateInstrumentCategory(key, payload),
  })

  const createMutation = useMutation({
    mutationFn: createLabProfile,
  })

  // ---- Step 1 actions -----------------------------------------------------

  const onStep1Next = async () => {
    if (!state.selectedPresetType) return
    if (!state.labName.trim()) return
    try {
      const chamber = await fromPresetMutation.mutateAsync({
        preset_type: state.selectedPresetType,
        name: `${state.labName.trim()} 暗室`,
      })
      setState((s) => ({
        ...s,
        duplicatedChamberId: chamber.id,
        duplicatedChamberName: chamber.name,
        active: 1,
      }))
    } catch (err: unknown) {
      notifications.show({
        color: 'red',
        title: '复制模板失败',
        message: err instanceof Error ? err.message : String(err),
      })
    }
  }

  // ---- Step 2 actions -----------------------------------------------------

  /** A binding row counts as "configured" when it has both a model
   *  picked and a non-empty endpoint. Empty rows are skipped on
   *  submit, which is fine: only the categories the operator
   *  actually has wired up belong in `instrument_bindings`. */
  const configuredBindings = useMemo(
    () =>
      state.bindings.filter(
        (b) => b.modelId !== null && b.endpoint.trim().length > 0,
      ),
    [state.bindings],
  )

  const onStep2Next = async () => {
    // Save each configured binding back to the backend so the
    // /instruments/{key} resources reflect what the operator chose
    // — keeps the existing instrument-management UI in sync.
    for (const b of configuredBindings) {
      await updateCategoryMutation.mutateAsync({
        key: b.categoryKey,
        payload: {
          modelId: b.modelId ?? undefined,
          connection: { endpoint: b.endpoint },
        },
      })
    }
    setState((s) => ({ ...s, active: 2 }))
  }

  // ---- Step 3 actions -----------------------------------------------------

  const onStep3Create = async () => {
    if (!state.duplicatedChamberId) return
    if (configuredBindings.length < 1) return

    // Convert configured bindings → backend payload. Pass the
    // category UUID we resolve from the catalog (NOT the category
    // key string); the backend expects UUIDs in instrument_bindings.
    const catalog = catalogQuery.data
    if (!catalog) return
    const catByKey = new Map(
      catalog.categories.map((c) => [c.key, c]),
    )

    // Send the catalog category's DB UUID (categoryId), NOT its
    // string key. Downstream resolvers (services/diagnostic_context
    // `_parse_instrument_bindings`) parse this field as UUID to join
    // back to InstrumentCategory.id; a non-UUID silently collapses
    // to category_key=None, and the *IDN? diagnostic sweep then
    // reports "no HAL driver" for every binding the wizard created.
    // (Codex P1 review on PR #18.)
    const bindingsPayload: InstrumentBindingPayload[] = configuredBindings.flatMap(
      (b) => {
        const cat = catByKey.get(b.categoryKey)
        if (!cat || !cat.categoryId) return []
        return [{
          category_id: cat.categoryId,
          instrument_model_id: b.modelId ?? undefined,
          connection_endpoint: b.endpoint,
          driver_mode: b.driverMode,
          role: b.categoryKey,
        }]
      },
    )

    try {
      await createMutation.mutateAsync({
        name: state.labName.trim(),
        chamber_config_id: state.duplicatedChamberId,
        instrument_bindings: bindingsPayload,
        is_active: true,
      })
      // Drop persisted state so a future re-open isn't haunted by a
      // half-filled draft, and re-fetch the gate query so App.tsx
      // hides the wizard.
      localStorage.removeItem(WIZARD_STORAGE_KEY)
      queryClient.invalidateQueries({ queryKey: ['lab-profiles'] })
      notifications.show({
        color: 'green',
        title: 'Lab Profile 已创建',
        message: `${state.labName.trim()} 已就绪,可以开始校准。`,
        icon: <IconCheck size={16} />,
      })
      onComplete()
    } catch (err: unknown) {
      // Backend returns 409 for duplicate name, 422 for invalid FK;
      // surface the actionable detail rather than the generic
      // "Request failed" axios string.
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response
          ?.data?.detail ?? (err instanceof Error ? err.message : String(err))
      notifications.show({
        color: 'red',
        title: '创建失败',
        message: detail,
        icon: <IconAlertCircle size={16} />,
      })
    }
  }

  const onCancel = () => {
    localStorage.removeItem(WIZARD_STORAGE_KEY)
    setState(EMPTY_STATE)
    onComplete()
  }

  // ---- Render -------------------------------------------------------------

  const canAdvanceStep1 =
    state.selectedPresetType !== null && state.labName.trim().length > 0
  const canAdvanceStep2 = configuredBindings.length >= 1
  const canCreate = canAdvanceStep2 && state.duplicatedChamberId !== null

  return (
    <Container size="md" py="xl">
      <Stack gap="lg">
        <div>
          <Title order={2}>欢迎使用 MIMO-First — 首次配置 Lab</Title>
          <Text c="dimmed" mt={4}>
            还没有 Lab Profile。下面 3 步将创建第一个 Lab,完成后即可进入主界面。
          </Text>
        </div>

        <Stepper active={state.active} onStepClick={() => { /* read-only */ }}>
          {/* ---------------------------- Step 1 ---------------------------- */}
          <Stepper.Step label="选择模板" description="暗室类型 + Lab 名">
            <Stack mt="lg">
              <Alert icon={<IconInfoCircle size={16} />} variant="light">
                选一个 chamber 模板作为起点。后续可以在"暗室配置"中调整尺寸 / 探头布局。
              </Alert>
              {presetsQuery.isLoading && <Loader />}
              {presetsQuery.data && (
                <Group gap="md" align="stretch" wrap="wrap">
                  {presetsQuery.data.presets.map((p) => {
                    const selected = state.selectedPresetType === p.type
                    return (
                      <Card
                        key={p.type}
                        withBorder
                        shadow={selected ? 'md' : 'xs'}
                        radius="md"
                        style={{
                          cursor: 'pointer',
                          flex: '1 1 220px',
                          minWidth: 220,
                          maxWidth: 280,
                          borderColor: selected ? 'var(--mantine-color-blue-6)' : undefined,
                          borderWidth: selected ? 2 : 1,
                        }}
                        onClick={() =>
                          setState((s) => ({
                            ...s,
                            selectedPresetType: p.type as ChamberType,
                          }))
                        }
                      >
                        <Group justify="space-between">
                          <Text fw={600}>{p.name}</Text>
                          {selected && <Badge color="blue">已选</Badge>}
                        </Group>
                        <Text size="sm" c="dimmed" mt={4}>
                          {p.description}
                        </Text>
                        <Text size="xs" c="dimmed" mt="sm">
                          {p.num_probes} 探头 · 半径 {p.chamber_radius_m} m
                          {p.supports_mimo_ota && ' · MIMO-OTA ✓'}
                        </Text>
                      </Card>
                    )
                  })}
                </Group>
              )}
              <TextInput
                label="Lab 名称"
                placeholder="例如 CAICT-Lab-1"
                value={state.labName}
                onChange={(e) => {
                  // e.currentTarget 在事件 handler 返回后被 React 置 null; 若在 setState
                  // 函数式 updater 内部读 .value, updater 异步/批处理执行时会崩 null.value
                  // (自动化快速交互序列触发)。先把值读到 updater 外 const。
                  const value = e.currentTarget.value
                  setState((s) => ({ ...s, labName: value }))
                }}
                description="后续在测试报告与校准证书上展示"
                required
              />
            </Stack>
          </Stepper.Step>

          {/* ---------------------------- Step 2 ---------------------------- */}
          <Stepper.Step label="绑定仪表" description="model + 连接地址">
            <Stack mt="lg">
              <Alert icon={<IconInfoCircle size={16} />} variant="light">
                给每个仪表类别选 model 和填连接地址。至少配置一个类别才能继续 (无仪表的 Lab 没法校准)。
              </Alert>
              {catalogQuery.isLoading && <Loader />}
              {state.bindings.map((b) => {
                const cat = catalogQuery.data?.categories.find(
                  (c) => c.key === b.categoryKey,
                )
                const modelOptions =
                  cat?.models.map((m) => ({
                    value: m.id,
                    label: `${m.vendor} · ${m.model}`,
                  })) ?? []
                return (
                  <Card key={b.categoryKey} withBorder radius="md">
                    <Group justify="space-between" mb="xs">
                      <Text fw={600}>{b.categoryLabel}</Text>
                      <SegmentedControl
                        size="xs"
                        value={b.driverMode}
                        onChange={(v) =>
                          setState((s) => ({
                            ...s,
                            bindings: s.bindings.map((row) =>
                              row.categoryKey === b.categoryKey
                                ? { ...row, driverMode: v as DriverMode }
                                : row,
                            ),
                          }))
                        }
                        data={[
                          { label: 'Auto', value: 'auto' },
                          { label: 'Mock', value: 'mock' },
                          { label: 'Real', value: 'real' },
                        ]}
                      />
                    </Group>
                    <Group grow>
                      <Select
                        label="Model"
                        placeholder="选择型号 (可空)"
                        value={b.modelId}
                        onChange={(v) =>
                          setState((s) => ({
                            ...s,
                            bindings: s.bindings.map((row) =>
                              row.categoryKey === b.categoryKey
                                ? { ...row, modelId: v }
                                : row,
                            ),
                          }))
                        }
                        data={modelOptions}
                        clearable
                      />
                      <TextInput
                        label="连接地址"
                        placeholder="192.168.1.10:5025"
                        value={b.endpoint}
                        onChange={(e) => {
                          // 同上: .value 读到 updater 外, 防 currentTarget 异步置 null 崩溃
                          const value = e.currentTarget.value
                          setState((s) => ({
                            ...s,
                            bindings: s.bindings.map((row) =>
                              row.categoryKey === b.categoryKey
                                ? { ...row, endpoint: value }
                                : row,
                            ),
                          }))
                        }}
                      />
                    </Group>
                  </Card>
                )
              })}
              <Text size="sm" c="dimmed">
                已配置 {configuredBindings.length} / {state.bindings.length} 个类别 ·
                需要至少 1 个
              </Text>
            </Stack>
          </Stepper.Step>

          {/* ---------------------------- Step 3 ---------------------------- */}
          <Stepper.Step label="确认创建" description="复核 + 创建">
            <Stack mt="lg">
              <Alert icon={<IconCheck size={16} />} color="blue" variant="light">
                复核下面的配置,确认无误后点击 "创建 Lab Profile"。
              </Alert>
              <Card withBorder radius="md">
                <Stack gap="xs">
                  <Group>
                    <Text fw={600} w={120}>Lab 名称</Text>
                    <Text>{state.labName.trim()}</Text>
                  </Group>
                  <Group>
                    <Text fw={600} w={120}>暗室</Text>
                    <Text>{state.duplicatedChamberName ?? '—'}</Text>
                  </Group>
                  <Group align="flex-start">
                    <Text fw={600} w={120}>仪表绑定</Text>
                    <Stack gap={2}>
                      {configuredBindings.map((b) => (
                        <Text key={b.categoryKey} size="sm">
                          {b.categoryLabel} → {b.endpoint} ({b.driverMode})
                        </Text>
                      ))}
                    </Stack>
                  </Group>
                </Stack>
              </Card>
            </Stack>
          </Stepper.Step>
        </Stepper>

        <Group justify="space-between" mt="md">
          <Button variant="subtle" color="gray" onClick={onCancel}>
            取消并清空
          </Button>
          <Group>
            {state.active > 0 && (
              <Button
                variant="default"
                leftSection={<IconArrowLeft size={16} />}
                onClick={() =>
                  setState((s) => ({ ...s, active: s.active - 1 }))
                }
              >
                上一步
              </Button>
            )}
            {state.active === 0 && (
              <Button
                rightSection={<IconArrowRight size={16} />}
                onClick={onStep1Next}
                disabled={!canAdvanceStep1}
                loading={fromPresetMutation.isPending}
              >
                下一步
              </Button>
            )}
            {state.active === 1 && (
              <Button
                rightSection={<IconArrowRight size={16} />}
                onClick={onStep2Next}
                disabled={!canAdvanceStep2}
                loading={updateCategoryMutation.isPending}
              >
                下一步
              </Button>
            )}
            {state.active === 2 && (
              <Button
                color="blue"
                rightSection={<IconCheck size={16} />}
                onClick={onStep3Create}
                disabled={!canCreate}
                loading={createMutation.isPending}
              >
                创建 Lab Profile
              </Button>
            )}
          </Group>
        </Group>
      </Stack>
    </Container>
  )
}
