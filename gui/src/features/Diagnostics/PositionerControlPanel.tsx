/**
 * U-5: 转台 (Positioner) standalone 控制面板。
 *
 * 让现场连上转台 (Aerotech, 默认 :8000) 后单独验证回零 / 定位 / 4 方位扫, 不依赖
 * 完整 cal 流程 (2026-05-27 现场无 standalone 路径 → U-5 "无结论")。
 * 后端 /instruments/positioner/* (app/api/instrument.py)。
 */
import { useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  NumberInput,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconArrowRight,
  IconHome,
  IconPlayerStop,
  IconRefresh,
} from '@tabler/icons-react'
import {
  positionerHome,
  positionerMove,
  positionerPosition,
  positionerStop,
  positionerSweep,
  type PositionerResult,
  type PositionerSweepResult,
} from '../../api/service'

export function PositionerControlPanel() {
  const [az, setAz] = useState<number>(0)
  const [el, setEl] = useState<number>(0)
  const [pos, setPos] = useState<{ az: number; el: number } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [sweep, setSweep] = useState<PositionerSweepResult | null>(null)

  const handle = async (label: string, fn: () => Promise<PositionerResult>) => {
    setBusy(label)
    try {
      const r = await fn()
      if (r.ok) {
        if (typeof r.azimuth === 'number' && typeof r.elevation === 'number') {
          setPos({ az: r.azimuth, el: r.elevation })
        }
        notifications.show({ color: 'green', message: r.message || `${label} 成功` })
      } else {
        notifications.show({
          color: 'red',
          title: `${label} 失败`,
          message: r.message || r.reason || '未知错误',
        })
      }
    } catch (e) {
      notifications.show({
        color: 'red',
        title: `${label} 请求出错`,
        message: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setBusy(null)
    }
  }

  const runSweep = async () => {
    setBusy('sweep')
    setSweep(null)
    try {
      const r = await positionerSweep()
      setSweep(r)
      notifications.show({
        color: r.ok ? 'green' : 'red',
        title: r.ok ? '4 方位扫完成' : '4 方位扫有问题',
        message: r.message || '',
      })
    } catch (e) {
      notifications.show({
        color: 'red',
        title: '扫描请求出错',
        message: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setBusy(null)
    }
  }

  return (
    <Stack gap="md">
      <Alert color="blue" variant="light" title="转台 standalone 控制">
        现场连上转台 (Aerotech, 默认 :8000) 后, 这里可单独验证回零 / 定位 / 4 方位扫, 不依赖完整 cal
        流程。操作前确认仪器已选 + 连接 IP 已填 + HAL 已加载 positioner 驱动。急停按钮随时可用。
      </Alert>

      <Card withBorder padding="md">
        <Group justify="space-between" mb="sm">
          <Title order={5}>当前位置</Title>
          <Button
            size="xs"
            variant="light"
            leftSection={<IconRefresh size={14} />}
            loading={busy === '读位置'}
            onClick={() => handle('读位置', positionerPosition)}
          >
            刷新
          </Button>
        </Group>
        {pos ? (
          <Group gap="lg">
            <Badge size="lg" color="blue">
              方位 Az = {pos.az.toFixed(2)}°
            </Badge>
            <Badge size="lg" color="grape">
              俯仰 El = {pos.el.toFixed(2)}°
            </Badge>
          </Group>
        ) : (
          <Text c="dimmed" size="sm">
            尚未读取 (点刷新)
          </Text>
        )}
      </Card>

      <Card withBorder padding="md">
        <Title order={5} mb="sm">
          手动控制
        </Title>
        <Group align="flex-end" gap="sm">
          <NumberInput
            label="方位 Az (°)"
            value={az}
            onChange={(v) => setAz(typeof v === 'number' ? v : 0)}
            min={0}
            max={360}
            step={10}
            w={130}
          />
          <NumberInput
            label="俯仰 El (°)"
            value={el}
            onChange={(v) => setEl(typeof v === 'number' ? v : 0)}
            min={-90}
            max={90}
            step={5}
            w={130}
            description="单轴转台忽略"
          />
          <Button
            leftSection={<IconArrowRight size={16} />}
            loading={busy === '定位'}
            onClick={() => handle('定位', () => positionerMove(az, el))}
          >
            移动到
          </Button>
          <Button
            variant="default"
            leftSection={<IconHome size={16} />}
            loading={busy === '回零'}
            onClick={() => handle('回零', positionerHome)}
          >
            回零 (HOME)
          </Button>
          <Button
            color="red"
            leftSection={<IconPlayerStop size={16} />}
            loading={busy === '急停'}
            onClick={() => handle('急停', positionerStop)}
          >
            急停 (ABORT)
          </Button>
        </Group>
      </Card>

      <Card withBorder padding="md">
        <Group justify="space-between" mb="sm">
          <div>
            <Title order={5}>4 方位扫验证</Title>
            <Text c="dimmed" size="xs">
              回零 → 0°/90°/180°/270° 依次定位 + 回读比对 (P0-5 预演)
            </Text>
          </div>
          <Button color="teal" loading={busy === 'sweep'} onClick={runSweep}>
            运行 4 方位扫
          </Button>
        </Group>
        {sweep && (
          <Table withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>目标 (°)</Table.Th>
                <Table.Th>实测 Az (°)</Table.Th>
                <Table.Th>到位</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sweep.points.map((p) => (
                <Table.Tr key={p.target}>
                  <Table.Td>{p.target.toFixed(1)}</Table.Td>
                  <Table.Td>
                    {typeof p.actual_azimuth === 'number'
                      ? p.actual_azimuth.toFixed(2)
                      : '未知'}
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      color={
                        p.within_tolerance === true
                          ? 'green'
                          : p.within_tolerance === false
                            ? 'red'
                            : 'gray'
                      }
                      variant="light"
                    >
                      {p.within_tolerance === true
                        ? '✓ 到位'
                        : p.within_tolerance === false
                          ? '✗ 超差'
                          : '未知'}
                    </Badge>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Card>
    </Stack>
  )
}
