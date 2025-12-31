/**
 * Step Configuration Editor
 *
 * Main editor for configuring 8 test steps in scenarios.
 * Uses specialized sub-editors for Steps 2, 3, and 8.
 */

import { useState, useEffect } from 'react'
import {
  Accordion,
  Stack,
  Switch,
  TextInput,
  NumberInput,
  Select,
  Group,
  Text,
  Alert,
  Paper,
} from '@mantine/core'
import { IconSettings, IconInfoCircle } from '@tabler/icons-react'
import type { StepConfiguration, NetworkStepConfig, BaseStationStepConfig, DigitalTwinStepConfig } from '../../types/roadTest'
import { NetworkStepEditor } from './NetworkStepEditor'
import { BaseStationStepEditor } from './BaseStationStepEditor'
import { DigitalTwinStepEditor } from './DigitalTwinStepEditor'

interface Props {
  value?: StepConfiguration
  onChange: (config: StepConfiguration) => void
  scenarioDefaults?: {
    band?: string
    bandwidth_mhz?: number
    channel_model?: string
  }
}

export function StepConfigurationEditor({ value, onChange, scenarioDefaults }: Props) {
  // 跟踪每个步骤是否启用
  const [enabledSteps, setEnabledSteps] = useState({
    chamber_init: !!value?.chamber_init,
    network_config: !!value?.network_config,
    base_station_setup: !!value?.base_station_setup,
    ota_mapper: !!value?.ota_mapper,
    route_execution: !!value?.route_execution,
    kpi_validation: !!value?.kpi_validation,
    report_generation: !!value?.report_generation,
    environment_setup: !!value?.environment_setup,
  })

  // 步骤配置状态
  const [config, setConfig] = useState<StepConfiguration>(value || {})

  // 同步外部 value 变化到内部状态
  useEffect(() => {
    setConfig(value || {})
    setEnabledSteps({
      chamber_init: !!value?.chamber_init,
      network_config: !!value?.network_config,
      base_station_setup: !!value?.base_station_setup,
      ota_mapper: !!value?.ota_mapper,
      route_execution: !!value?.route_execution,
      kpi_validation: !!value?.kpi_validation,
      report_generation: !!value?.report_generation,
      environment_setup: !!value?.environment_setup,
    })
  }, [value])

  const updateConfig = (stepKey: keyof StepConfiguration, stepData: any) => {
    const newConfig = { ...config, [stepKey]: stepData }
    setConfig(newConfig)
    onChange(newConfig)
  }

  const toggleStep = (stepKey: keyof StepConfiguration, enabled: boolean) => {
    setEnabledSteps({ ...enabledSteps, [stepKey]: enabled })
    if (!enabled) {
      // 禁用步骤时移除配置
      const newConfig = { ...config }
      delete newConfig[stepKey]
      setConfig(newConfig)
      onChange(newConfig)
    } else {
      // 启用步骤时初始化默认值
      const defaults = getStepDefaults(stepKey)
      updateConfig(stepKey, defaults)
    }
  }

  const getStepDefaults = (stepKey: keyof StepConfiguration) => {
    switch (stepKey) {
      case 'chamber_init':
        return {
          chamber_id: 'MPAC-1',
          timeout_seconds: 300,
          verify_connections: true,
          calibrate_position_table: true,
        }
      case 'network_config':
        return {
          authentication: { method: 'open' },
          ip_config: { mode: 'dhcp' },
          pdu_session: { type: 'ipv4', sst: 1, dnn: 'internet' },
          qos: { fiveqi: 9 },
          applications: { enabled: false, tests: [], sequential: true },
          verify_registration: true,
          verify_pdu_session: true,
          timeout_seconds: 300,
        } as NetworkStepConfig
      case 'base_station_setup':
        return {
          rf: {
            frequency_mhz: 3500,
            bandwidth_mhz: scenarioDefaults?.bandwidth_mhz || 100,
            scs_khz: 30,
            duplex_mode: 'TDD',
            mimo_layers: 4,
          },
          cell: {
            pci: 1,
            tac: 1,
            cell_id: 1,
            plmn: { mcc: '460', mnc: '00' },
            band: scenarioDefaults?.band || 'n78',
          },
          power: { total_power_dbm: 43 },
          deployment: { num_base_stations: 1, topology: 'single' },
          antenna: {
            type: 'sector',
            mimo_config: '4x4',
            antenna_height_m: 25,
            polarization: 'dual',
            gain_dbi: 18,
            azimuth_deg: 0,
            mechanical_tilt_deg: 6,
          },
          verify_coverage: true,
          verify_neighbor_relations: false,
          verify_signal: true,
          timeout_seconds: 300,
        } as BaseStationStepConfig
      case 'ota_mapper':
        return {
          route_type: 'urban',
          update_rate_hz: 10,
          enable_handover: true,
          timeout_seconds: 180,
        }
      case 'route_execution':
        return {
          monitor_kpis: true,
          log_interval_s: 1,
          auto_screenshot: true,
          timeout_seconds: 2100,
        }
      case 'kpi_validation':
        return {
          kpi_thresholds: {
            min_throughput_mbps: 50,
            max_latency_ms: 50,
            min_rsrp_dbm: -110,
            max_packet_loss_percent: 5,
          },
          generate_plots: true,
          timeout_seconds: 300,
        }
      case 'report_generation':
        return {
          report_format: 'PDF',
          include_raw_data: false,
          include_screenshots: true,
          include_recommendations: true,
          timeout_seconds: 180,
        }
      case 'environment_setup':
        return {
          channel_model: {
            type: 'statistical',
            use_scenario_default: true,
          },
          validate_environment: true,
          export_channel_data: false,
          timeout_seconds: 600,
        } as DigitalTwinStepConfig
      default:
        return {}
    }
  }

  return (
    <Stack gap="md">
      <Alert icon={<IconInfoCircle size={16} />} title="测试步骤配置" color="blue">
        <Stack gap="xs">
          <Text size="sm">
            开启某个步骤的开关后，可以自定义该步骤的参数。
          </Text>
          <Text size="sm" c="dimmed">
            未开启的步骤将使用系统默认值。场景定义中的参数会作为步骤配置的默认值。
          </Text>
        </Stack>
      </Alert>

      <Accordion variant="separated" multiple>
        {/* 步骤1: 初始化OTA暗室 */}
        <Accordion.Item value="chamber_init">
          <Accordion.Control icon={<IconSettings size={20} />}>
            <Group justify="space-between" style={{ width: '100%', paddingRight: '1rem' }}>
              <Text fw={600}>步骤1: 初始化OTA暗室</Text>
              <Switch
                checked={enabledSteps.chamber_init}
                onChange={(e) => {
                  e.stopPropagation()
                  toggleStep('chamber_init', e.currentTarget.checked)
                }}
                onClick={(e) => e.stopPropagation()}
                label={enabledSteps.chamber_init ? '自定义' : '默认'}
                size="sm"
              />
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            {enabledSteps.chamber_init && (
              <Paper p="md" withBorder>
                <Stack gap="sm">
                  <Select
                    label="暗室ID"
                    data={['MPAC-1', 'MPAC-2', 'MPAC-3']}
                    value={config.chamber_init?.chamber_id || 'MPAC-1'}
                    onChange={(val) => updateConfig('chamber_init', { ...config.chamber_init, chamber_id: val })}
                  />
                  <NumberInput
                    label="超时时间（秒）"
                    value={config.chamber_init?.timeout_seconds || 300}
                    onChange={(val) => updateConfig('chamber_init', { ...config.chamber_init, timeout_seconds: val })}
                    min={60}
                    max={1200}
                  />
                  <Switch
                    label="验证连接"
                    checked={config.chamber_init?.verify_connections ?? true}
                    onChange={(e) => updateConfig('chamber_init', { ...config.chamber_init, verify_connections: e.currentTarget.checked })}
                  />
                  <Switch
                    label="校准位置台"
                    checked={config.chamber_init?.calibrate_position_table ?? true}
                    onChange={(e) => updateConfig('chamber_init', { ...config.chamber_init, calibrate_position_table: e.currentTarget.checked })}
                  />
                </Stack>
              </Paper>
            )}
          </Accordion.Panel>
        </Accordion.Item>

        {/* 步骤2: 配置网络 (Core Network) */}
        <Accordion.Item value="network_config">
          <Accordion.Control icon={<IconSettings size={20} />}>
            <Group justify="space-between" style={{ width: '100%', paddingRight: '1rem' }}>
              <Text fw={600}>步骤2: 配置网络 (核心网)</Text>
              <Switch
                checked={enabledSteps.network_config}
                onChange={(e) => {
                  e.stopPropagation()
                  toggleStep('network_config', e.currentTarget.checked)
                }}
                onClick={(e) => e.stopPropagation()}
                label={enabledSteps.network_config ? '自定义' : '默认'}
                size="sm"
              />
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            {enabledSteps.network_config && (
              <NetworkStepEditor
                value={config.network_config as NetworkStepConfig}
                onChange={(val) => updateConfig('network_config', val)}
              />
            )}
          </Accordion.Panel>
        </Accordion.Item>

        {/* 步骤3: 设置基站 (RAN) */}
        <Accordion.Item value="base_station_setup">
          <Accordion.Control icon={<IconSettings size={20} />}>
            <Group justify="space-between" style={{ width: '100%', paddingRight: '1rem' }}>
              <Text fw={600}>步骤3: 配置基站 (无线接入网)</Text>
              <Switch
                checked={enabledSteps.base_station_setup}
                onChange={(e) => {
                  e.stopPropagation()
                  toggleStep('base_station_setup', e.currentTarget.checked)
                }}
                onClick={(e) => e.stopPropagation()}
                label={enabledSteps.base_station_setup ? '自定义' : '默认'}
                size="sm"
              />
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            {enabledSteps.base_station_setup && (
              <BaseStationStepEditor
                value={config.base_station_setup as BaseStationStepConfig}
                onChange={(val) => updateConfig('base_station_setup', val)}
                scenarioDefaults={scenarioDefaults}
              />
            )}
          </Accordion.Panel>
        </Accordion.Item>

        {/* 步骤4: 配置OTA映射器 */}
        <Accordion.Item value="ota_mapper">
          <Accordion.Control icon={<IconSettings size={20} />}>
            <Group justify="space-between" style={{ width: '100%', paddingRight: '1rem' }}>
              <Text fw={600}>步骤4: 配置OTA映射器</Text>
              <Switch
                checked={enabledSteps.ota_mapper}
                onChange={(e) => {
                  e.stopPropagation()
                  toggleStep('ota_mapper', e.currentTarget.checked)
                }}
                onClick={(e) => e.stopPropagation()}
                label={enabledSteps.ota_mapper ? '自定义' : '默认'}
                size="sm"
              />
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            {enabledSteps.ota_mapper && (
              <Paper p="md" withBorder>
                <Stack gap="sm">
                  <TextInput
                    label="路径文件"
                    placeholder="可选，留空使用场景默认路径"
                    value={config.ota_mapper?.route_file || ''}
                    onChange={(e) => updateConfig('ota_mapper', { ...config.ota_mapper, route_file: e.currentTarget.value })}
                  />
                  <Select
                    label="路径类型"
                    data={['urban', 'highway', 'rural', 'tunnel']}
                    value={config.ota_mapper?.route_type || 'urban'}
                    onChange={(val) => updateConfig('ota_mapper', { ...config.ota_mapper, route_type: val })}
                  />
                  <NumberInput
                    label="更新速率 (Hz)"
                    value={config.ota_mapper?.update_rate_hz || 10}
                    onChange={(val) => updateConfig('ota_mapper', { ...config.ota_mapper, update_rate_hz: val })}
                    min={1}
                    max={100}
                    step={1}
                  />
                  <NumberInput
                    label="位置容差 (米)"
                    value={config.ota_mapper?.position_tolerance_m || 1.0}
                    onChange={(val) => updateConfig('ota_mapper', { ...config.ota_mapper, position_tolerance_m: val })}
                    min={0.1}
                    max={10}
                    step={0.1}
                  />
                  <NumberInput
                    label="超时时间（秒）"
                    value={config.ota_mapper?.timeout_seconds || 180}
                    onChange={(val) => updateConfig('ota_mapper', { ...config.ota_mapper, timeout_seconds: val })}
                    min={60}
                    max={600}
                  />
                  <Switch
                    label="启用切换"
                    checked={config.ota_mapper?.enable_handover ?? true}
                    onChange={(e) => updateConfig('ota_mapper', { ...config.ota_mapper, enable_handover: e.currentTarget.checked })}
                  />
                </Stack>
              </Paper>
            )}
          </Accordion.Panel>
        </Accordion.Item>

        {/* 步骤5: 执行路径测试 */}
        <Accordion.Item value="route_execution">
          <Accordion.Control icon={<IconSettings size={20} />}>
            <Group justify="space-between" style={{ width: '100%', paddingRight: '1rem' }}>
              <Text fw={600}>步骤5: 执行路径测试</Text>
              <Switch
                checked={enabledSteps.route_execution}
                onChange={(e) => {
                  e.stopPropagation()
                  toggleStep('route_execution', e.currentTarget.checked)
                }}
                onClick={(e) => e.stopPropagation()}
                label={enabledSteps.route_execution ? '自定义' : '默认'}
                size="sm"
              />
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            {enabledSteps.route_execution && (
              <Paper p="md" withBorder>
                <Stack gap="sm">
                  <NumberInput
                    label="日志间隔 (秒)"
                    description="设置更小值以获得更高频率的数据采样"
                    value={config.route_execution?.log_interval_s || 1}
                    onChange={(val) => updateConfig('route_execution', { ...config.route_execution, log_interval_s: val })}
                    min={0.1}
                    max={10}
                    step={0.1}
                  />
                  <NumberInput
                    label="超时时间（秒）"
                    value={config.route_execution?.timeout_seconds || 2100}
                    onChange={(val) => updateConfig('route_execution', { ...config.route_execution, timeout_seconds: val })}
                    min={300}
                    max={7200}
                  />
                  <Switch
                    label="监控KPI"
                    checked={config.route_execution?.monitor_kpis ?? true}
                    onChange={(e) => updateConfig('route_execution', { ...config.route_execution, monitor_kpis: e.currentTarget.checked })}
                  />
                  <Switch
                    label="自动截图"
                    checked={config.route_execution?.auto_screenshot ?? true}
                    onChange={(e) => updateConfig('route_execution', { ...config.route_execution, auto_screenshot: e.currentTarget.checked })}
                  />
                </Stack>
              </Paper>
            )}
          </Accordion.Panel>
        </Accordion.Item>

        {/* 步骤6: 验证KPI */}
        <Accordion.Item value="kpi_validation">
          <Accordion.Control icon={<IconSettings size={20} />}>
            <Group justify="space-between" style={{ width: '100%', paddingRight: '1rem' }}>
              <Text fw={600}>步骤6: 验证KPI和性能指标</Text>
              <Switch
                checked={enabledSteps.kpi_validation}
                onChange={(e) => {
                  e.stopPropagation()
                  toggleStep('kpi_validation', e.currentTarget.checked)
                }}
                onClick={(e) => e.stopPropagation()}
                label={enabledSteps.kpi_validation ? '自定义' : '默认'}
                size="sm"
              />
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            {enabledSteps.kpi_validation && (
              <Paper p="md" withBorder>
                <Stack gap="sm">
                  <Text fw={600} size="sm">KPI阈值</Text>
                  <NumberInput
                    label="最小吞吐量 (Mbps)"
                    value={config.kpi_validation?.kpi_thresholds?.min_throughput_mbps || 50}
                    onChange={(val) => updateConfig('kpi_validation', {
                      ...config.kpi_validation,
                      kpi_thresholds: { ...config.kpi_validation?.kpi_thresholds, min_throughput_mbps: val },
                    })}
                    min={1}
                    max={10000}
                  />
                  <NumberInput
                    label="最大延迟 (ms)"
                    value={config.kpi_validation?.kpi_thresholds?.max_latency_ms || 50}
                    onChange={(val) => updateConfig('kpi_validation', {
                      ...config.kpi_validation,
                      kpi_thresholds: { ...config.kpi_validation?.kpi_thresholds, max_latency_ms: val },
                    })}
                    min={1}
                    max={1000}
                  />
                  <NumberInput
                    label="最小RSRP (dBm)"
                    value={config.kpi_validation?.kpi_thresholds?.min_rsrp_dbm || -110}
                    onChange={(val) => updateConfig('kpi_validation', {
                      ...config.kpi_validation,
                      kpi_thresholds: { ...config.kpi_validation?.kpi_thresholds, min_rsrp_dbm: val },
                    })}
                    min={-140}
                    max={-40}
                  />
                  <NumberInput
                    label="最大丢包率 (%)"
                    value={config.kpi_validation?.kpi_thresholds?.max_packet_loss_percent || 5}
                    onChange={(val) => updateConfig('kpi_validation', {
                      ...config.kpi_validation,
                      kpi_thresholds: { ...config.kpi_validation?.kpi_thresholds, max_packet_loss_percent: val },
                    })}
                    min={0}
                    max={100}
                    step={0.1}
                  />
                  <NumberInput
                    label="超时时间（秒）"
                    value={config.kpi_validation?.timeout_seconds || 300}
                    onChange={(val) => updateConfig('kpi_validation', { ...config.kpi_validation, timeout_seconds: val })}
                    min={60}
                    max={600}
                  />
                  <Switch
                    label="生成图表"
                    checked={config.kpi_validation?.generate_plots ?? true}
                    onChange={(e) => updateConfig('kpi_validation', { ...config.kpi_validation, generate_plots: e.currentTarget.checked })}
                  />
                </Stack>
              </Paper>
            )}
          </Accordion.Panel>
        </Accordion.Item>

        {/* 步骤7: 生成测试报告 */}
        <Accordion.Item value="report_generation">
          <Accordion.Control icon={<IconSettings size={20} />}>
            <Group justify="space-between" style={{ width: '100%', paddingRight: '1rem' }}>
              <Text fw={600}>步骤7: 生成测试报告</Text>
              <Switch
                checked={enabledSteps.report_generation}
                onChange={(e) => {
                  e.stopPropagation()
                  toggleStep('report_generation', e.currentTarget.checked)
                }}
                onClick={(e) => e.stopPropagation()}
                label={enabledSteps.report_generation ? '自定义' : '默认'}
                size="sm"
              />
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            {enabledSteps.report_generation && (
              <Paper p="md" withBorder>
                <Stack gap="sm">
                  <Select
                    label="报告格式"
                    data={['PDF', 'HTML', 'Word']}
                    value={config.report_generation?.report_format || 'PDF'}
                    onChange={(val) => updateConfig('report_generation', { ...config.report_generation, report_format: val })}
                  />
                  <NumberInput
                    label="超时时间（秒）"
                    value={config.report_generation?.timeout_seconds || 180}
                    onChange={(val) => updateConfig('report_generation', { ...config.report_generation, timeout_seconds: val })}
                    min={60}
                    max={600}
                  />
                  <Switch
                    label="包含原始数据"
                    checked={config.report_generation?.include_raw_data ?? false}
                    onChange={(e) => updateConfig('report_generation', { ...config.report_generation, include_raw_data: e.currentTarget.checked })}
                  />
                  <Switch
                    label="包含截图"
                    checked={config.report_generation?.include_screenshots ?? true}
                    onChange={(e) => updateConfig('report_generation', { ...config.report_generation, include_screenshots: e.currentTarget.checked })}
                  />
                  <Switch
                    label="包含建议"
                    checked={config.report_generation?.include_recommendations ?? true}
                    onChange={(e) => updateConfig('report_generation', { ...config.report_generation, include_recommendations: e.currentTarget.checked })}
                  />
                </Stack>
              </Paper>
            )}
          </Accordion.Panel>
        </Accordion.Item>

        {/* 步骤8: 配置数字孪生环境 */}
        <Accordion.Item value="environment_setup">
          <Accordion.Control icon={<IconSettings size={20} />}>
            <Group justify="space-between" style={{ width: '100%', paddingRight: '1rem' }}>
              <Text fw={600}>步骤8: 配置数字孪生环境</Text>
              <Switch
                checked={enabledSteps.environment_setup}
                onChange={(e) => {
                  e.stopPropagation()
                  toggleStep('environment_setup', e.currentTarget.checked)
                }}
                onClick={(e) => e.stopPropagation()}
                label={enabledSteps.environment_setup ? '自定义' : '默认'}
                size="sm"
              />
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            {enabledSteps.environment_setup && (
              <DigitalTwinStepEditor
                value={config.environment_setup as DigitalTwinStepConfig}
                onChange={(val) => updateConfig('environment_setup', val)}
                scenarioChannelModel={scenarioDefaults?.channel_model}
              />
            )}
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  )
}
