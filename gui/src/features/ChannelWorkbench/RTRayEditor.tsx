/**
 * RT 动态多快照射线编辑器 (P2-16 S4-4): rt_dynamic payload 的 snapshots[].rays 两层增删 +
 * 嵌套编辑单条射线。比 CDLClusterEditor 多一层 —— 快照数组 (Accordion), 每快照一组原始 MPDB
 * 射线 (MPCInput, 非聚类后 CDL)。后端 _validate_rt_dynamic_payload: ≥1 快照, 每快照 ≥1 射线;
 * ray 必填 delay_s/power_linear/aoa_deg/aod_deg, power_linear>0, zoa/zod∈[0,180]。
 */
import { useState } from 'react'
import {
  Accordion, ActionIcon, Button, Group, Modal, NumberInput, SimpleGrid, Stack, Table, Text,
} from '@mantine/core'
import { IconEdit, IconPlus, IconTrash } from '@tabler/icons-react'

import { DEFAULT_MPC_RAY, type MPCRayPayload } from '../../api/channelAssetService'

const numOr0 = (v: number | string): number => (typeof v === 'number' ? v : Number(v) || 0)

/** rt_dynamic 的一个快照 (一组原始射线)。 */
export interface RtSnapshot {
  rays: MPCRayPayload[]
}

interface Props {
  snapshots: RtSnapshot[]
  onChange: (snapshots: RtSnapshot[]) => void
}

export function RTRayEditor({ snapshots, onChange }: Props) {
  // 编辑射线定位 {si, ri}: ri===snapshots[si].rays.length 为新建; null 关闭
  const [editing, setEditing] = useState<{ si: number; ri: number } | null>(null)
  const [draft, setDraft] = useState<MPCRayPayload>(DEFAULT_MPC_RAY)

  const addSnapshot = () => onChange([...snapshots, { rays: [] }])
  const removeSnapshot = (si: number) => {
    if (editing?.si === si) setEditing(null)
    onChange(snapshots.filter((_, j) => j !== si))
  }

  const openNewRay = (si: number) => { setDraft({ ...DEFAULT_MPC_RAY }); setEditing({ si, ri: snapshots[si].rays.length }) }
  const openEditRay = (si: number, ri: number) => { setDraft({ ...snapshots[si].rays[ri] }); setEditing({ si, ri }) }
  const removeRay = (si: number, ri: number) =>
    onChange(snapshots.map((s, j) => (j === si ? { rays: s.rays.filter((_, k) => k !== ri) } : s)))
  const saveRay = () => {
    if (!editing) return
    const { si, ri } = editing
    onChange(snapshots.map((s, j) => {
      if (j !== si) return s
      const rays = [...s.rays]
      rays[ri] = draft
      return { rays }
    }))
    setEditing(null)
  }

  const isNewRay = editing != null && editing.ri === (snapshots[editing.si]?.rays.length ?? -1)

  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Text size="sm" fw={500}>快照 (snapshots) — {snapshots.length} 个</Text>
        <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={addSnapshot}>
          添加快照
        </Button>
      </Group>

      {snapshots.length === 0 ? (
        <Text size="xs" c="dimmed">至少加 1 个快照，每快照 ≥1 条原始射线（MPDB 多径）。</Text>
      ) : (
        <Accordion variant="contained" multiple defaultValue={['0']}>
          {snapshots.map((snap, si) => (
            <Accordion.Item key={si} value={String(si)}>
              <Accordion.Control>
                <Text size="sm">快照 {si + 1} — {snap.rays.length} 条射线</Text>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack gap="xs">
                  <Group justify="space-between">
                    <Button size="xs" variant="light" leftSection={<IconPlus size={12} />}
                      onClick={() => openNewRay(si)}>
                      添加射线
                    </Button>
                    <Button size="xs" variant="subtle" color="red" leftSection={<IconTrash size={12} />}
                      onClick={() => removeSnapshot(si)}>
                      删除快照
                    </Button>
                  </Group>
                  {snap.rays.length === 0 ? (
                    <Text size="xs" c="dimmed">该快照暂无射线，点「添加射线」。</Text>
                  ) : (
                    <Table withTableBorder striped>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>#</Table.Th><Table.Th>时延 (ns)</Table.Th><Table.Th>功率</Table.Th>
                          <Table.Th>AoA</Table.Th><Table.Th>AoD</Table.Th><Table.Th ta="right">操作</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {snap.rays.map((r, ri) => (
                          <Table.Tr key={ri}>
                            <Table.Td>{ri + 1}</Table.Td>
                            <Table.Td>{(r.delay_s * 1e9).toFixed(1)}</Table.Td>
                            <Table.Td>{r.power_linear}</Table.Td>
                            <Table.Td>{r.aoa_deg}°</Table.Td>
                            <Table.Td>{r.aod_deg}°</Table.Td>
                            <Table.Td>
                              <Group gap={2} justify="flex-end">
                                <ActionIcon size="sm" variant="subtle" onClick={() => openEditRay(si, ri)}>
                                  <IconEdit size={14} />
                                </ActionIcon>
                                <ActionIcon size="sm" variant="subtle" color="red" onClick={() => removeRay(si, ri)}>
                                  <IconTrash size={14} />
                                </ActionIcon>
                              </Group>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  )}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          ))}
        </Accordion>
      )}

      <Modal
        opened={editing != null}
        onClose={() => setEditing(null)}
        title={isNewRay ? '添加射线' : '编辑射线'}
        size="md"
        zIndex={400}
      >
        <Stack gap="xs">
          <SimpleGrid cols={2}>
            <NumberInput label="时延 delay_s (s)" value={draft.delay_s} decimalScale={10} min={0}
              onChange={(v) => setDraft({ ...draft, delay_s: numOr0(v) })} />
            <NumberInput label="功率 power_linear" value={draft.power_linear} decimalScale={4}
              onChange={(v) => setDraft({ ...draft, power_linear: numOr0(v) })} />
            <NumberInput label="AoA (deg)" value={draft.aoa_deg}
              onChange={(v) => setDraft({ ...draft, aoa_deg: numOr0(v) })} />
            <NumberInput label="AoD (deg)" value={draft.aod_deg}
              onChange={(v) => setDraft({ ...draft, aod_deg: numOr0(v) })} />
            <NumberInput label="ZoA (deg)" value={draft.zoa_deg ?? 90} min={0} max={180}
              onChange={(v) => setDraft({ ...draft, zoa_deg: numOr0(v) })} />
            <NumberInput label="ZoD (deg)" value={draft.zod_deg ?? 90} min={0} max={180}
              onChange={(v) => setDraft({ ...draft, zod_deg: numOr0(v) })} />
            <NumberInput label="相位 phase_rad" value={draft.phase_rad ?? ''} decimalScale={4}
              onChange={(v) => setDraft({ ...draft, phase_rad: v === '' ? null : numOr0(v) })} />
          </SimpleGrid>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setEditing(null)}>取消</Button>
            <Button onClick={saveRay}>保存射线</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
