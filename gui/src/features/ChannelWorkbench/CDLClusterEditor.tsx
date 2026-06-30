/**
 * 自定义 CDL 簇编辑器 (P2-16 S4-3): custom_static payload 的 clusters 数组增删 + 嵌套编辑单簇。
 *
 * 参考现有 components/CustomCDLProfile/CustomCDLProfileManager 的簇编辑 UI; 这里编辑的是
 * ChannelAsset custom_static payload (snapshots[0].clusters) 的 CDLClusterPayload[]。
 */
import { useState } from 'react'
import {
  ActionIcon, Button, Group, Modal, NumberInput, SimpleGrid, Stack, Table, Text,
} from '@mantine/core'
import { IconEdit, IconPlus, IconTrash } from '@tabler/icons-react'

import { DEFAULT_CDL_CLUSTER, type CDLClusterPayload } from '../../api/channelAssetService'

const numOr0 = (v: number | string): number => (typeof v === 'number' ? v : Number(v) || 0)

interface Props {
  clusters: CDLClusterPayload[]
  onChange: (clusters: CDLClusterPayload[]) => void
}

export function CDLClusterEditor({ clusters, onChange }: Props) {
  // editIdx: null=关闭; idx<length=编辑现有; idx===length=新建
  const [editIdx, setEditIdx] = useState<number | null>(null)
  const [draft, setDraft] = useState<CDLClusterPayload>(DEFAULT_CDL_CLUSTER)

  const openNew = () => { setDraft({ ...DEFAULT_CDL_CLUSTER }); setEditIdx(clusters.length) }
  const openEdit = (i: number) => { setDraft({ ...clusters[i] }); setEditIdx(i) }
  const remove = (i: number) => onChange(clusters.filter((_, j) => j !== i))
  const saveCluster = () => {
    if (editIdx == null) return
    const next = [...clusters]
    next[editIdx] = draft
    onChange(next)
    setEditIdx(null)
  }

  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Text size="sm" fw={500}>簇 (clusters) — {clusters.length} 个</Text>
        <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={openNew}>
          添加簇
        </Button>
      </Group>

      {clusters.length === 0 ? (
        <Text size="xs" c="dimmed">至少加 1 个簇（自定义 CDL 的多径簇参数）。</Text>
      ) : (
        <Table withTableBorder striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th><Table.Th>时延 (ns)</Table.Th><Table.Th>功率</Table.Th>
              <Table.Th>AoA</Table.Th><Table.Th>AoD</Table.Th><Table.Th>子径</Table.Th>
              <Table.Th ta="right">操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {clusters.map((c, i) => (
              <Table.Tr key={i}>
                <Table.Td>{i + 1}</Table.Td>
                <Table.Td>{(c.delay_s * 1e9).toFixed(1)}</Table.Td>
                <Table.Td>{c.power_linear}</Table.Td>
                <Table.Td>{c.aoa_deg}°</Table.Td>
                <Table.Td>{c.aod_deg}°</Table.Td>
                <Table.Td>{c.num_rays ?? 20}</Table.Td>
                <Table.Td>
                  <Group gap={2} justify="flex-end">
                    <ActionIcon size="sm" variant="subtle" onClick={() => openEdit(i)}>
                      <IconEdit size={14} />
                    </ActionIcon>
                    <ActionIcon size="sm" variant="subtle" color="red" onClick={() => remove(i)}>
                      <IconTrash size={14} />
                    </ActionIcon>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Modal
        opened={editIdx != null}
        onClose={() => setEditIdx(null)}
        title={editIdx === clusters.length ? '添加簇' : '编辑簇'}
        size="md"
        zIndex={400}
      >
        <Stack gap="xs">
          <SimpleGrid cols={2}>
            <NumberInput label="时延 delay_s (s)" value={draft.delay_s} decimalScale={10}
              onChange={(v) => setDraft({ ...draft, delay_s: numOr0(v) })} />
            <NumberInput label="功率 power_linear" value={draft.power_linear} decimalScale={4}
              onChange={(v) => setDraft({ ...draft, power_linear: numOr0(v) })} />
            <NumberInput label="AoA (deg)" value={draft.aoa_deg}
              onChange={(v) => setDraft({ ...draft, aoa_deg: numOr0(v) })} />
            <NumberInput label="AoD (deg)" value={draft.aod_deg}
              onChange={(v) => setDraft({ ...draft, aod_deg: numOr0(v) })} />
            <NumberInput label="ZoA (deg)" value={draft.zoa_deg ?? 90}
              onChange={(v) => setDraft({ ...draft, zoa_deg: numOr0(v) })} />
            <NumberInput label="ZoD (deg)" value={draft.zod_deg ?? 90}
              onChange={(v) => setDraft({ ...draft, zod_deg: numOr0(v) })} />
            <NumberInput label="AS_AoA (deg)" value={draft.as_aoa_deg ?? 0}
              onChange={(v) => setDraft({ ...draft, as_aoa_deg: numOr0(v) })} />
            <NumberInput label="AS_AoD (deg)" value={draft.as_aod_deg ?? 0}
              onChange={(v) => setDraft({ ...draft, as_aod_deg: numOr0(v) })} />
            <NumberInput label="AS_ZoA (deg)" value={draft.as_zoa_deg ?? 0}
              onChange={(v) => setDraft({ ...draft, as_zoa_deg: numOr0(v) })} />
            <NumberInput label="AS_ZoD (deg)" value={draft.as_zod_deg ?? 0}
              onChange={(v) => setDraft({ ...draft, as_zod_deg: numOr0(v) })} />
            <NumberInput label="XPR (dB)" value={draft.xpr_db ?? ''}
              onChange={(v) => setDraft({ ...draft, xpr_db: v === '' ? null : numOr0(v) })} />
            <NumberInput label="子径数 num_rays" value={draft.num_rays ?? 20} min={1}
              onChange={(v) => setDraft({ ...draft, num_rays: numOr0(v) })} />
          </SimpleGrid>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setEditIdx(null)}>取消</Button>
            <Button onClick={saveCluster}>保存簇</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
