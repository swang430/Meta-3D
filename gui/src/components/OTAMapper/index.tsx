/**
 * OTAMapper Component
 * OTA探头权重映射器 - 主组件
 */

import { useState } from 'react'
import {
  Stack,
  Title,
  Paper,
  Group,
  Button,
  Alert,
  LoadingOverlay,
  Box
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconMapPin,
  IconAlertCircle,
  IconCheck,
  IconRefresh
} from '@tabler/icons-react'

import type {
  ScenarioConfig,
  ProbeArrayConfig,
  MIMOConfig,
  ProbeWeightResponse
} from '../../types/channelEngine'

import { channelEngineClient } from '../../services/channelEngine'
import { ScenarioSelector } from './ScenarioSelector'
import { ProbeArraySelector } from './ProbeArraySelector'
import { MIMOConfigPanel } from './MIMOConfigPanel'
import { WeightResultDisplay } from './WeightResultDisplay'

/**
 * OTAMapper主组件
 */
export function OTAMapper() {
  // 状态管理
  const [scenario, setScenario] = useState<ScenarioConfig>({
    scenario_type: 'UMa',
    cluster_model: 'CDL-C',
    frequency_mhz: 3500,
    use_median_lsps: false
  })

  const [probeArray, setProbeArray] = useState<ProbeArrayConfig | null>(null)

  const [mimoConfig, setMIMOConfig] = useState<MIMOConfig>({
    num_tx_antennas: 2,
    num_rx_antennas: 2,
    tx_antenna_spacing: 0.5,
    rx_antenna_spacing: 0.5
  })

  const [result, setResult] = useState<ProbeWeightResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [serviceAvailable, setServiceAvailable] = useState<boolean | null>(null)

  // 检查服务可用性
  const checkService = async () => {
    try {
      const available = await channelEngineClient.isAvailable()
      setServiceAvailable(available)

      if (!available) {
        notifications.show({
          title: 'ChannelEngine服务不可用',
          message: '请确保服务已启动: python -m app.main',
          color: 'red',
          icon: <IconAlertCircle size={18} />
        })
      } else {
        notifications.show({
          title: 'ChannelEngine服务已就绪',
          message: '可以开始生成探头权重',
          color: 'green',
          icon: <IconCheck size={18} />
        })
      }
    } catch (error) {
      setServiceAvailable(false)
      console.error('Service check failed:', error)
    }
  }

  // 生成探头权重
  const handleGenerateWeights = async () => {
    if (!probeArray) {
      notifications.show({
        title: '配置不完整',
        message: '请先选择探头阵列配置',
        color: 'orange',
        icon: <IconAlertCircle size={18} />
      })
      return
    }

    setLoading(true)
    setResult(null)

    try {
      const response = await channelEngineClient.generateProbeWeights({
        scenario,
        probe_array: probeArray,
        mimo_config: mimoConfig
      })

      setResult(response)

      if (response.success) {
        notifications.show({
          title: '权重生成成功',
          message: response.message || `成功生成 ${response.probe_weights.length} 个探头权重`,
          color: 'green',
          icon: <IconCheck size={18} />
        })
      } else {
        notifications.show({
          title: '权重生成失败',
          message: response.message || '未知错误',
          color: 'red',
          icon: <IconAlertCircle size={18} />
        })
      }
    } catch (error) {
      console.error('Weight generation failed:', error)
      notifications.show({
        title: '请求失败',
        message: error instanceof Error ? error.message : '未知错误',
        color: 'red',
        icon: <IconAlertCircle size={18} />
      })
    } finally {
      setLoading(false)
    }
  }

  // 重置配置
  const handleReset = () => {
    setScenario({
      scenario_type: 'UMa',
      cluster_model: 'CDL-C',
      frequency_mhz: 3500,
      use_median_lsps: false
    })
    setProbeArray(null)
    setMIMOConfig({
      num_tx_antennas: 2,
      num_rx_antennas: 2,
      tx_antenna_spacing: 0.5,
      rx_antenna_spacing: 0.5
    })
    setResult(null)
  }

  // 组件挂载时检查服务
  useState(() => {
    checkService()
  })

  return (
    <Stack gap="md">
      {/* 标题栏 */}
      <Group justify="space-between">
        <Title order={3}>
          <Group gap="xs">
            <IconMapPin size={24} />
            <span>OTA探头权重映射器</span>
          </Group>
        </Title>

        <Group gap="sm">
          <Button
            variant="light"
            leftSection={<IconRefresh size={16} />}
            onClick={checkService}
            size="sm"
          >
            检查服务
          </Button>
          <Button
            variant="outline"
            onClick={handleReset}
            size="sm"
          >
            重置
          </Button>
        </Group>
      </Group>

      {/* 服务状态提示 */}
      {serviceAvailable === false && (
        <Alert
          variant="light"
          color="red"
          title="ChannelEngine服务未连接"
          icon={<IconAlertCircle />}
        >
          请在终端启动服务:
          <code style={{ display: 'block', marginTop: 8, padding: 8, background: '#f5f5f5' }}>
            cd channel-engine-service<br />
            source ../ChannelEgine/.venv/bin/activate<br />
            python -m app.main
          </code>
        </Alert>
      )}

      {serviceAvailable === true && (
        <Alert
          variant="light"
          color="green"
          title="ChannelEngine服务已连接"
          icon={<IconCheck />}
        >
          服务运行正常，可以开始配置并生成探头权重
        </Alert>
      )}

      {/* 配置面板 */}
      <Box pos="relative">
        <LoadingOverlay
          visible={loading}
          overlayProps={{ radius: 'sm', blur: 2 }}
          loaderProps={{ children: '正在生成探头权重...' }}
        />

        <Stack gap="md">
          {/* 场景选择器 */}
          <Paper p="md" withBorder>
            <ScenarioSelector
              value={scenario}
              onChange={setScenario}
            />
          </Paper>

          {/* 探头阵列选择器 */}
          <Paper p="md" withBorder>
            <ProbeArraySelector
              value={probeArray}
              onChange={setProbeArray}
            />
          </Paper>

          {/* MIMO配置面板 */}
          <Paper p="md" withBorder>
            <MIMOConfigPanel
              value={mimoConfig}
              onChange={setMIMOConfig}
            />
          </Paper>

          {/* 生成按钮 */}
          <Group justify="center">
            <Button
              size="lg"
              leftSection={<IconMapPin size={20} />}
              onClick={handleGenerateWeights}
              disabled={!probeArray || serviceAvailable === false}
              loading={loading}
            >
              生成探头权重
            </Button>
          </Group>
        </Stack>
      </Box>

      {/* 结果显示 */}
      {result && (
        <Paper p="md" withBorder>
          <WeightResultDisplay result={result} />
        </Paper>
      )}
    </Stack>
  )
}

export default OTAMapper
