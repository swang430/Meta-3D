/**
 * MIMOConfigPanel Component
 * MIMO配置面板
 */

import { Stack, Title, NumberInput, Group, Text, Badge } from '@mantine/core'
import type { MIMOConfig } from '../../types/channelEngine'

interface MIMOConfigPanelProps {
  value: MIMOConfig
  onChange: (config: MIMOConfig) => void
}

export function MIMOConfigPanel({ value, onChange }: MIMOConfigPanelProps) {
  // 计算MIMO配置描述
  const mimoDescription = `${value.num_tx_antennas}T${value.num_rx_antennas}R MIMO`

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={4}>3. MIMO配置</Title>
        <Badge size="lg" variant="dot" color="blue">
          {mimoDescription}
        </Badge>
      </Group>

      <Group grow>
        {/* 发射天线数 */}
        <NumberInput
          label="发射天线数 (Tx)"
          value={value.num_tx_antennas}
          onChange={(val) =>
            onChange({
              ...value,
              num_tx_antennas: Number(val) || 1
            })
          }
          min={1}
          max={8}
          step={1}
          required
          description="基站侧发射天线数量"
        />

        {/* 接收天线数 */}
        <NumberInput
          label="接收天线数 (Rx)"
          value={value.num_rx_antennas}
          onChange={(val) =>
            onChange({
              ...value,
              num_rx_antennas: Number(val) || 1
            })
          }
          min={1}
          max={8}
          step={1}
          required
          description="UE侧接收天线数量"
        />
      </Group>

      <Group grow>
        {/* 发射天线间距 */}
        <NumberInput
          label="Tx天线间距 (λ)"
          value={value.tx_antenna_spacing}
          onChange={(val) =>
            onChange({
              ...value,
              tx_antenna_spacing: Number(val) || 0.5
            })
          }
          min={0.1}
          max={5.0}
          step={0.1}
          decimalScale={2}
          description="单位：波长 (λ)"
        />

        {/* 接收天线间距 */}
        <NumberInput
          label="Rx天线间距 (λ)"
          value={value.rx_antenna_spacing}
          onChange={(val) =>
            onChange({
              ...value,
              rx_antenna_spacing: Number(val) || 0.5
            })
          }
          min={0.1}
          max={5.0}
          step={0.1}
          decimalScale={2}
          description="单位：波长 (λ)"
        />
      </Group>

      <Text size="xs" c="dimmed">
        💡 提示：0.5λ间距常用于相关天线配置，≥1.0λ用于非相关配置
      </Text>
    </Stack>
  )
}
