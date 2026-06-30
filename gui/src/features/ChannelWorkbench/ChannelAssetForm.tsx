/**
 * 信道资产建/编辑表单 (P2-16 S4): 四 source_type 全 payload 可编辑 —— standard_3gpp (CDL 名) /
 * custom_static (簇编辑器 S4-3) / rt_dynamic (多快照射线编辑器 S4-4) / vendor_file (scd_config)。
 *
 * 用 channelAssetService.createChannelAsset / updateChannelAsset。source_type 建后不可改
 * (后端 update 不暴露), 故仅建时可选 source_type。custom_static / rt_dynamic 的 payload 含
 * 表单 UI 未表示的字段 (pathloss_db / sampling_meta / scenario_meta) → 编辑时 merge 既有
 * payload 仅覆盖 snapshots (见 buildSourcePayload)。
 */
import { useEffect, useState } from 'react'
import {
  Alert, Button, Divider, Group, Modal, NumberInput, Select, SimpleGrid, Stack,
  Text, Textarea, TextInput,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import {
  createChannelAsset,
  updateChannelAsset,
  type CDLClusterPayload,
  type ChannelAsset,
  type ChannelAssetCreatePayload,
  type ChannelSourceType,
} from '../../api/channelAssetService'
import { CDLClusterEditor } from './CDLClusterEditor'
import { RTRayEditor, type RtSnapshot } from './RTRayEditor'

// 可【新建】的 source_type (四类全可建)
const CREATABLE: { value: ChannelSourceType; label: string }[] = [
  { value: 'standard_3gpp', label: '标准 3GPP' },
  { value: 'custom_static', label: '自定义 CDL' },
  { value: 'rt_dynamic', label: 'RT 动态' },
  { value: 'vendor_file', label: '厂商文件' },
]

const numOrNull = (v: number | string): number | null =>
  v === '' || v == null ? null : Number(v)
const blankNull = (s: string): string | null => (s.trim() === '' ? null : s.trim())

interface Props {
  opened: boolean
  /** 编辑现有资产; null = 新建。 */
  asset: ChannelAsset | null
  onClose: () => void
}

export function ChannelAssetForm({ opened, asset, onClose }: Props) {
  const queryClient = useQueryClient()
  const isEdit = asset != null

  const [sourceType, setSourceType] = useState<ChannelSourceType>('standard_3gpp')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [centerGhz, setCenterGhz] = useState<number | string>('')
  const [bandwidthMhz, setBandwidthMhz] = useState<number | string>('')
  const [isLos, setIsLos] = useState<'unset' | 'los' | 'nlos'>('unset')
  const [kFactorDb, setKFactorDb] = useState<number | string>('')
  // standard_3gpp
  const [cdlModelName, setCdlModelName] = useState('')
  // vendor_file scd_config + .smu
  const [scd, setScd] = useState({
    band: '', arfcn: '' as number | string, bandwidth_mhz: '' as number | string,
    model: '', scenario: '', mimo: '', polarization: '', version: 1 as number | string,
  })
  const [filePath, setFilePath] = useState('')
  // custom_static: snapshots[0].clusters
  const [clusters, setClusters] = useState<CDLClusterPayload[]>([])
  // rt_dynamic: snapshots[].rays (多快照, 每快照一组原始射线)
  const [raySnapshots, setRaySnapshots] = useState<RtSnapshot[]>([])
  const [formError, setFormError] = useState<string | null>(null)

  // 打开时按 asset 回填 (或清空新建)
  useEffect(() => {
    if (!opened) return
    setFormError(null)
    if (asset) {
      setSourceType(asset.source_type)
      setName(asset.name)
      setDescription(asset.description ?? '')
      setCenterGhz(asset.center_frequency_hz != null ? asset.center_frequency_hz / 1e9 : '')
      setBandwidthMhz(asset.bandwidth_mhz ?? '')
      setIsLos(asset.is_los == null ? 'unset' : asset.is_los ? 'los' : 'nlos')
      setKFactorDb(asset.k_factor_db ?? '')
      const p = (asset.payload ?? {}) as Record<string, unknown>
      setCdlModelName(String(p.cdl_model_name ?? ''))
      const sc = (p.scd_config ?? {}) as Record<string, unknown>
      setScd({
        band: String(sc.band ?? ''), arfcn: (sc.arfcn as number) ?? '',
        bandwidth_mhz: (sc.bandwidth_mhz as number) ?? '', model: String(sc.model ?? ''),
        scenario: String(sc.scenario ?? ''), mimo: String(sc.mimo ?? ''),
        polarization: String(sc.polarization ?? ''), version: (sc.version as number) ?? 1,
      })
      setFilePath(asset.associated_file_path ?? '')
      const snaps = (p.snapshots ?? []) as Array<{ clusters?: CDLClusterPayload[] }>
      setClusters(snaps[0]?.clusters ?? [])
      const raySnaps = (p.snapshots ?? []) as RtSnapshot[]
      setRaySnapshots(raySnaps.map((s) => ({ rays: s.rays ?? [] })))
    } else {
      setSourceType('standard_3gpp')
      setName(''); setDescription(''); setCenterGhz(''); setBandwidthMhz('')
      setIsLos('unset'); setKFactorDb(''); setCdlModelName('')
      setScd({ band: '', arfcn: '', bandwidth_mhz: '', model: '', scenario: '', mimo: '', polarization: '', version: 1 })
      setFilePath('')
      setClusters([])
      setRaySnapshots([])
    }
  }, [opened, asset])

  const createMutation = useMutation({
    mutationFn: (p: ChannelAssetCreatePayload) => createChannelAsset(p),
    onSuccess: (a) => {
      notifications.show({ title: '信道资产已创建', message: a.name, color: 'green' })
      queryClient.invalidateQueries({ queryKey: ['channel-assets'] })
      onClose()
    },
    onError: (e) => setFormError(extractDetail(e)),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateChannelAsset(id, payload),
    onSuccess: (a) => {
      notifications.show({ title: '信道资产已更新', message: a.name, color: 'green' })
      queryClient.invalidateQueries({ queryKey: ['channel-assets'] })
      onClose()
    },
    onError: (e) => setFormError(extractDetail(e)),
  })

  function commonFields() {
    const center = numOrNull(centerGhz)
    const isLosVal = isLos === 'unset' ? null : isLos === 'los'
    return {
      name: name.trim(),
      description: blankNull(description),
      center_frequency_hz: center == null ? null : center * 1e9,
      bandwidth_mhz: numOrNull(bandwidthMhz),
      is_los: isLosVal,
      k_factor_db: numOrNull(kFactorDb),
    }
  }

  function buildSourcePayload(): Record<string, unknown> | null {
    if (sourceType === 'standard_3gpp') {
      return { cdl_model_name: cdlModelName.trim() }
    }
    if (sourceType === 'vendor_file') {
      return {
        scd_config: {
          band: scd.band.trim(), arfcn: numOrNull(scd.arfcn),
          bandwidth_mhz: numOrNull(scd.bandwidth_mhz), model: scd.model.trim(),
          scenario: scd.scenario.trim(), mimo: scd.mimo.trim(),
          polarization: scd.polarization.trim(), version: numOrNull(scd.version),
        },
      }
    }
    if (sourceType === 'custom_static') {
      // 保留既有 payload 的非 snapshots 字段, 仅覆盖 snapshots: 迁移 (c8e1f5a2d4b7) 把
      // CustomCDLProfile.pathloss_db 与 snapshots 平铺进 payload 同级, 后端 asc_strategy
      // ._synthesize_from_clusters 从 payload.pathloss_db 读路损 (CustomStaticPayload 类型
      // 未声明该字段, 但运行时存在)。整体替换会丢 pathloss_db, 合成 fallback 100 dB 改 OTA
      // 结果 (Codex #183 P1)。建时 asset==null → existing={} → 退化成 {snapshots:[{clusters}]}。
      const existing = (asset?.payload ?? {}) as Record<string, unknown>
      const firstSnap = (Array.isArray(existing.snapshots) ? existing.snapshots[0] : null) as
        | Record<string, unknown>
        | null
      return { ...existing, snapshots: [{ ...(firstSnap ?? {}), clusters }] }
    }
    if (sourceType === 'rt_dynamic') {
      // 同 custom_static: merge 既有 payload, 仅覆盖 snapshots —— rt_dynamic payload 还含表单
      // 未表示的 sampling_meta / scenario_meta (RtDynamicPayload 声明), 整体替换会丢。建时
      // asset==null → existing={} → 退化成 {snapshots: raySnapshots}。
      const existing = (asset?.payload ?? {}) as Record<string, unknown>
      return { ...existing, snapshots: raySnapshots }
    }
    return null
  }

  function handleSubmit() {
    setFormError(null)
    if (name.trim() === '') { setFormError('名称必填'); return }
    if (sourceType === 'custom_static' && clusters.length === 0) {
      setFormError('自定义 CDL 至少需 1 个簇'); return
    }
    if (sourceType === 'rt_dynamic') {
      if (raySnapshots.length === 0) { setFormError('RT 动态至少需 1 个快照'); return }
      if (raySnapshots.some((s) => s.rays.length === 0)) {
        setFormError('每个快照至少需 1 条射线（MPDB 原始多径）'); return
      }
    }
    // S2 校验前置: center 与 bandwidth 须同时给 (standard/rt 频率一致性网)
    if (numOrNull(centerGhz) != null && numOrNull(bandwidthMhz) == null
        && (sourceType === 'standard_3gpp')) {
      setFormError('标准 3GPP 设了中心频率须同时给带宽 (否则频率一致性网静默跳过)')
      return
    }
    const common = commonFields()
    if (isEdit && asset) {
      // 编辑: 档案 + 物理字段 + payload (四 source_type 全可编辑 payload; custom/rt 的 merge
      // 模式在 buildSourcePayload 内保留表单未表示的顶层字段)
      const upd: Record<string, unknown> = { ...common, associated_file_path: blankNull(filePath) }
      const sp = buildSourcePayload()
      if (sp != null) upd.payload = sp
      updateMutation.mutate({ id: asset.id, payload: upd })
    } else {
      const sp = buildSourcePayload()
      if (sp == null) { setFormError('该 source_type 暂不支持新建'); return }
      const create: ChannelAssetCreatePayload = {
        name: common.name, source_type: sourceType, payload: sp,
        description: common.description, center_frequency_hz: common.center_frequency_hz,
        bandwidth_mhz: common.bandwidth_mhz, is_los: common.is_los, k_factor_db: common.k_factor_db,
        associated_file_path: blankNull(filePath),
      }
      createMutation.mutate(create)
    }
  }

  const submitting = createMutation.isPending || updateMutation.isPending

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={isEdit ? `编辑信道资产 — ${asset?.name}` : '新建信道资产'}
      size="lg"
    >
      <Stack gap="sm">
        {isEdit ? (
          <Text size="sm" c="dimmed">来源 source_type: <b>{labelOf(sourceType)}</b>（建后不可改）</Text>
        ) : (
          <Select
            label="来源 source_type"
            description="四类全可建：标准 3GPP / 自定义 CDL（簇）/ RT 动态（多快照射线）/ 厂商文件"
            data={CREATABLE}
            value={sourceType}
            onChange={(v) => v && setSourceType(v as ChannelSourceType)}
            allowDeselect={false}
          />
        )}

        <TextInput label="名称" required value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Textarea label="描述" autosize minRows={1} value={description}
          onChange={(e) => setDescription(e.currentTarget.value)} />

        {sourceType === 'standard_3gpp' && (
          <TextInput
            label="CDL 模型名 (cdl_model_name)" required
            placeholder="如 UMa CDL-C NLOS"
            value={cdlModelName} onChange={(e) => setCdlModelName(e.currentTarget.value)}
          />
        )}

        {sourceType === 'custom_static' && (
          <>
            <Divider label="自定义 CDL 簇 (clusters)" labelPosition="left" />
            <CDLClusterEditor clusters={clusters} onChange={setClusters} />
          </>
        )}

        {sourceType === 'rt_dynamic' && (
          <>
            <Divider label="RT 动态多快照射线 (snapshots[].rays)" labelPosition="left" />
            <RTRayEditor snapshots={raySnapshots} onChange={setRaySnapshots} />
          </>
        )}

        {sourceType === 'vendor_file' && (
          <>
            <Divider label="SCD 配置 (scd_config)" labelPosition="left" />
            <SimpleGrid cols={2}>
              <TextInput label="频段 band" placeholder="N78" value={scd.band}
                onChange={(e) => setScd({ ...scd, band: e.currentTarget.value })} />
              <NumberInput label="ARFCN" value={scd.arfcn}
                onChange={(v) => setScd({ ...scd, arfcn: v })} />
              <NumberInput label="带宽 MHz" value={scd.bandwidth_mhz}
                onChange={(v) => setScd({ ...scd, bandwidth_mhz: v })} />
              <TextInput label="模型 model" placeholder="CDLC" value={scd.model}
                onChange={(e) => setScd({ ...scd, model: e.currentTarget.value })} />
              <TextInput label="场景 scenario" placeholder="UMa" value={scd.scenario}
                onChange={(e) => setScd({ ...scd, scenario: e.currentTarget.value })} />
              <TextInput label="MIMO" placeholder="4x4" value={scd.mimo}
                onChange={(e) => setScd({ ...scd, mimo: e.currentTarget.value })} />
              <TextInput label="极化 polarization" placeholder="DP" value={scd.polarization}
                onChange={(e) => setScd({ ...scd, polarization: e.currentTarget.value })} />
              <NumberInput label="版本 version" value={scd.version}
                onChange={(v) => setScd({ ...scd, version: v })} />
            </SimpleGrid>
            <TextInput
              label="关联 .smu 文件 (associated_file_path)"
              description="declared-only (无文件) 时留空 — GCM 加载门会 fail-loud"
              placeholder="/smu/MF_....smu"
              value={filePath} onChange={(e) => setFilePath(e.currentTarget.value)}
            />
          </>
        )}

        <Divider label="物理声明 (频率一致性网)" labelPosition="left" />
        <SimpleGrid cols={2}>
          <NumberInput label="中心频率 (GHz)" value={centerGhz} decimalScale={4} step={0.1}
            onChange={(v) => setCenterGhz(v)} />
          <NumberInput label="带宽 (MHz)" value={bandwidthMhz}
            onChange={(v) => setBandwidthMhz(v)} />
          <Select label="LOS" data={[
            { value: 'unset', label: '未声明' }, { value: 'los', label: 'LOS' }, { value: 'nlos', label: 'NLOS' },
          ]} value={isLos} onChange={(v) => v && setIsLos(v as typeof isLos)} allowDeselect={false} />
          <NumberInput label="K 因子 (dB)" value={kFactorDb} onChange={(v) => setKFactorDb(v)} />
        </SimpleGrid>

        {formError && (
          <Alert color="red" variant="light">{formError}</Alert>
        )}

        <Group justify="flex-end" mt="sm">
          <Button variant="default" onClick={onClose} disabled={submitting}>取消</Button>
          <Button onClick={handleSubmit} loading={submitting}>
            {isEdit ? '保存' : '创建'}
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function labelOf(s: ChannelSourceType): string {
  return ({ standard_3gpp: '标准 3GPP', custom_static: '自定义 CDL', rt_dynamic: 'RT 动态', vendor_file: '厂商文件' } as const)[s]
}

function extractDetail(e: unknown): string {
  return (
    (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
    (e as Error)?.message ?? '未知错误'
  )
}
