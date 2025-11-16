/**
 * WeightResultDisplay Component
 * 权重结果显示
 */

import { Stack, Title, Group, Text, Table, Badge, Alert, Progress } from '@mantine/core'
import { IconCheck, IconAlertCircle, IconInfoCircle } from '@tabler/icons-react'
import type { ProbeWeightResponse } from '../../types/channelEngine'

interface WeightResultDisplayProps {
  result: ProbeWeightResponse
}

export function WeightResultDisplay({ result }: WeightResultDisplayProps) {
  const { probe_weights, channel_statistics, success, message } = result

  // 如果失败，显示错误信息
  if (!success) {
    return (
      <Alert
        icon={<IconAlertCircle />}
        title="权重生成失败"
        color="red"
      >
        {message || '未知错误'}
      </Alert>
    )
  }

  // 计算统计信息
  const avgMagnitude = probe_weights.reduce((sum, w) => sum + w.weight.magnitude, 0) / probe_weights.length
  const maxMagnitude = Math.max(...probe_weights.map(w => w.weight.magnitude))
  const minMagnitude = Math.min(...probe_weights.map(w => w.weight.magnitude))

  return (
    <Stack gap="md">
      {/* 标题和状态 */}
      <Group justify="space-between">
        <Title order={4}>生成结果</Title>
        <Badge
          size="lg"
          color="green"
          leftSection={<IconCheck size={14} />}
        >
          成功
        </Badge>
      </Group>

      {/* 消息 */}
      {message && (
        <Alert
          icon={<IconInfoCircle />}
          title="提示"
          color="blue"
          variant="light"
        >
          {message}
        </Alert>
      )}

      {/* 信道统计信息 */}
      <div>
        <Title order={5} mb="sm">信道统计信息</Title>
        <Stack gap="xs">
          <Group>
            <Text size="sm" fw={500} style={{ width: 150 }}>路径损耗:</Text>
            <Badge variant="light" color="red">
              {channel_statistics.pathloss_db.toFixed(2)} dB
            </Badge>
          </Group>

          {channel_statistics.condition && (
            <Group>
              <Text size="sm" fw={500} style={{ width: 150 }}>信道条件:</Text>
              <Badge
                variant="light"
                color={channel_statistics.condition === 'LOS' ? 'green' : 'orange'}
              >
                {channel_statistics.condition}
              </Badge>
            </Group>
          )}

          <Group>
            <Text size="sm" fw={500} style={{ width: 150 }}>簇数量:</Text>
            <Badge variant="light" color="blue">
              {channel_statistics.num_clusters}
            </Badge>
          </Group>

          {channel_statistics.rms_delay_spread_ns && (
            <Group>
              <Text size="sm" fw={500} style={{ width: 150 }}>RMS时延扩展:</Text>
              <Badge variant="light" color="grape">
                {channel_statistics.rms_delay_spread_ns.toFixed(2)} ns
              </Badge>
            </Group>
          )}

          {channel_statistics.angular_spread_deg && (
            <Group>
              <Text size="sm" fw={500} style={{ width: 150 }}>角度扩展:</Text>
              <Badge variant="light" color="violet">
                {channel_statistics.angular_spread_deg.toFixed(2)}°
              </Badge>
            </Group>
          )}
        </Stack>
      </div>

      {/* 权重统计 */}
      <div>
        <Title order={5} mb="sm">权重统计</Title>
        <Stack gap="xs">
          <Group>
            <Text size="sm" fw={500} style={{ width: 150 }}>探头数量:</Text>
            <Text size="sm">{probe_weights.length} 个</Text>
          </Group>

          <Group>
            <Text size="sm" fw={500} style={{ width: 150 }}>平均幅度:</Text>
            <Text size="sm">{avgMagnitude.toFixed(4)}</Text>
          </Group>

          <Group>
            <Text size="sm" fw={500} style={{ width: 150 }}>幅度范围:</Text>
            <Text size="sm">
              {minMagnitude.toFixed(4)} ~ {maxMagnitude.toFixed(4)}
            </Text>
          </Group>
        </Stack>
      </div>

      {/* 探头权重表格 */}
      <div>
        <Title order={5} mb="sm">探头权重详情</Title>
        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          <Table striped highlightOnHover withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th style={{ width: 80 }}>探头ID</Table.Th>
                <Table.Th style={{ width: 80 }}>极化</Table.Th>
                <Table.Th style={{ width: 120 }}>幅度</Table.Th>
                <Table.Th style={{ width: 120 }}>相位 (°)</Table.Th>
                <Table.Th style={{ width: 150 }}>归一化幅度</Table.Th>
                <Table.Th style={{ width: 80 }}>状态</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {probe_weights.map((weight) => {
                const normalizedMag = (weight.weight.magnitude / maxMagnitude) * 100

                return (
                  <Table.Tr key={weight.probe_id}>
                    <Table.Td>
                      <Badge variant="light" size="sm">
                        #{weight.probe_id}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        {weight.polarization}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        {weight.weight.magnitude.toFixed(4)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace">
                        {weight.weight.phase_deg.toFixed(2)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Stack gap={2}>
                        <Progress
                          value={normalizedMag}
                          size="md"
                          color="blue"
                        />
                        <Text size="xs" c="dimmed" ta="center">
                          {normalizedMag.toFixed(0)}%
                        </Text>
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        size="sm"
                        color={weight.enabled ? 'green' : 'gray'}
                        variant="dot"
                      >
                        {weight.enabled ? '启用' : '禁用'}
                      </Badge>
                    </Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
        </div>
      </div>
    </Stack>
  )
}
