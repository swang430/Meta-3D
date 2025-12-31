/**
 * Base Station Step Editor (Step 3)
 *
 * RAN layer configuration:
 * - RF Parameters
 * - Cell Parameters
 * - Power Parameters
 * - Deployment
 * - Antenna
 * - Beamforming
 * - Handover
 */

import {
  Stack,
  Paper,
  Text,
  Select,
  TextInput,
  NumberInput,
  Switch,
  Divider,
  SimpleGrid,
  Accordion,
  Group,
  Badge,
  Slider,
} from '@mantine/core'
import {
  IconAntenna,
  IconBroadcast,
  IconBuildingBroadcastTower,
  IconWaveSine,
  IconBolt,
  IconArrowsExchange,
  IconLocation,
} from '@tabler/icons-react'
import type { BaseStationStepConfig } from '../../types/roadTest'

interface Props {
  value?: BaseStationStepConfig
  onChange: (config: BaseStationStepConfig) => void
  scenarioDefaults?: {
    band?: string
    bandwidth_mhz?: number
  }
}

const DEFAULT_CONFIG: BaseStationStepConfig = {
  rf: {
    frequency_mhz: 3500,
    bandwidth_mhz: 100,
    scs_khz: 30,
    duplex_mode: 'TDD',
    mimo_layers: 4,
  },
  cell: {
    pci: 1,
    tac: 1,
    cell_id: 1,
    plmn: { mcc: '460', mnc: '00' },
    band: 'n78',
  },
  power: {
    total_power_dbm: 43,
  },
  deployment: {
    num_base_stations: 1,
    topology: 'single',
  },
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
}

const SCS_OPTIONS = [
  { value: '15', label: '15 kHz (LTE/NR Sub-6)' },
  { value: '30', label: '30 kHz (NR Sub-6, 推荐)' },
  { value: '60', label: '60 kHz (NR Sub-6/mmWave)' },
  { value: '120', label: '120 kHz (NR mmWave)' },
]

const DUPLEX_OPTIONS = [
  { value: 'TDD', label: 'TDD (时分双工)' },
  { value: 'FDD', label: 'FDD (频分双工)' },
]

const MIMO_LAYERS = [
  { value: '1', label: '1 层 (SISO)' },
  { value: '2', label: '2 层' },
  { value: '4', label: '4 层 (推荐)' },
  { value: '8', label: '8 层' },
]

const BAND_OPTIONS = [
  { value: 'n1', label: 'n1 (2100 MHz FDD)' },
  { value: 'n3', label: 'n3 (1800 MHz FDD)' },
  { value: 'n28', label: 'n28 (700 MHz FDD)' },
  { value: 'n41', label: 'n41 (2.5 GHz TDD)' },
  { value: 'n77', label: 'n77 (3.3-4.2 GHz TDD)' },
  { value: 'n78', label: 'n78 (3.3-3.8 GHz TDD, 推荐)' },
  { value: 'n79', label: 'n79 (4.4-5 GHz TDD)' },
  { value: 'n257', label: 'n257 (28 GHz mmWave)' },
  { value: 'n258', label: 'n258 (26 GHz mmWave)' },
  { value: 'n260', label: 'n260 (39 GHz mmWave)' },
  { value: 'B1', label: 'B1 (2100 MHz LTE)' },
  { value: 'B3', label: 'B3 (1800 MHz LTE)' },
  { value: 'B7', label: 'B7 (2600 MHz LTE)' },
  { value: 'B41', label: 'B41 (2.5 GHz LTE TDD)' },
]

const TOPOLOGY_OPTIONS = [
  { value: 'single', label: '单基站' },
  { value: 'linear', label: '线性部署' },
  { value: 'hexagonal', label: '六边形蜂窝' },
  { value: 'custom', label: '自定义位置' },
]

const ANTENNA_TYPES = [
  { value: 'omni', label: '全向天线' },
  { value: 'sector', label: '扇区天线 (推荐)' },
  { value: 'massive_mimo', label: 'Massive MIMO' },
  { value: 'aat', label: 'AAT (有源天线)' },
]

const MIMO_CONFIGS = [
  { value: '2x2', label: '2x2 MIMO' },
  { value: '4x4', label: '4x4 MIMO (推荐)' },
  { value: '8x8', label: '8x8 MIMO' },
  { value: '16x16', label: '16x16 MIMO' },
  { value: '32x32', label: '32x32 MIMO' },
  { value: '64x64', label: '64x64 Massive MIMO' },
]

const POLARIZATION_OPTIONS = [
  { value: 'single', label: '单极化' },
  { value: 'dual', label: '双极化 (推荐)' },
  { value: 'cross', label: '交叉极化' },
]

const BEAM_MODES = [
  { value: 'static', label: '静态波束' },
  { value: 'dynamic', label: '动态波束' },
  { value: 'codebook', label: '码本波束' },
  { value: 'eigenvalue', label: '特征值波束' },
]

// Deep merge helper to ensure all nested properties have defaults
function mergeWithDefaults(value?: Partial<BaseStationStepConfig>): BaseStationStepConfig {
  if (!value) return DEFAULT_CONFIG
  return {
    rf: {
      ...DEFAULT_CONFIG.rf,
      ...value.rf,
    },
    cell: {
      ...DEFAULT_CONFIG.cell,
      ...value.cell,
      plmn: {
        ...DEFAULT_CONFIG.cell.plmn,
        ...value.cell?.plmn,
      },
    },
    power: {
      ...DEFAULT_CONFIG.power,
      ...value.power,
    },
    deployment: {
      ...DEFAULT_CONFIG.deployment,
      ...value.deployment,
    },
    antenna: {
      ...DEFAULT_CONFIG.antenna,
      ...value.antenna,
    },
    beamforming: value.beamforming,
    handover: value.handover,
    verify_coverage: value.verify_coverage ?? DEFAULT_CONFIG.verify_coverage,
    verify_neighbor_relations: value.verify_neighbor_relations ?? DEFAULT_CONFIG.verify_neighbor_relations,
    verify_signal: value.verify_signal ?? DEFAULT_CONFIG.verify_signal,
    timeout_seconds: value.timeout_seconds ?? DEFAULT_CONFIG.timeout_seconds,
  }
}

export function BaseStationStepEditor({ value, onChange, scenarioDefaults }: Props) {
  const config = mergeWithDefaults(value)

  const updateConfig = <K extends keyof BaseStationStepConfig>(
    key: K,
    val: BaseStationStepConfig[K]
  ) => {
    onChange({ ...config, [key]: val })
  }

  const updateNested = <K extends keyof BaseStationStepConfig>(
    key: K,
    nestedKey: string,
    val: any
  ) => {
    onChange({
      ...config,
      [key]: {
        ...(config[key] as any),
        [nestedKey]: val,
      },
    })
  }

  const updateDeepNested = <K extends keyof BaseStationStepConfig>(
    key: K,
    path: string[],
    val: any
  ) => {
    const current = config[key] as any
    const newObj = { ...current }
    let ref = newObj
    for (let i = 0; i < path.length - 1; i++) {
      ref[path[i]] = { ...ref[path[i]] }
      ref = ref[path[i]]
    }
    ref[path[path.length - 1]] = val
    onChange({ ...config, [key]: newObj })
  }

  return (
    <Stack gap="md">
      <Accordion variant="separated" multiple defaultValue={['rf', 'cell', 'power', 'antenna']}>
        {/* RF Parameters Section */}
        <Accordion.Item value="rf">
          <Accordion.Control icon={<IconWaveSine size={20} />}>
            <Group gap="xs">
              <Text fw={600}>射频参数 (RF)</Text>
              <Badge size="sm" variant="light">
                {config.rf.frequency_mhz} MHz / {config.rf.bandwidth_mhz} MHz
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <SimpleGrid cols={2}>
                  <NumberInput
                    label="中心频率 (MHz)"
                    description="射频载波中心频率"
                    value={config.rf.frequency_mhz}
                    onChange={(val) => updateNested('rf', 'frequency_mhz', val || 3500)}
                    min={600}
                    max={52600}
                  />

                  <NumberInput
                    label="带宽 (MHz)"
                    description={scenarioDefaults?.bandwidth_mhz ? `场景默认: ${scenarioDefaults.bandwidth_mhz} MHz` : undefined}
                    value={config.rf.bandwidth_mhz}
                    onChange={(val) => updateNested('rf', 'bandwidth_mhz', val || 100)}
                    min={5}
                    max={400}
                  />

                  <Select
                    label="子载波间隔 (SCS)"
                    data={SCS_OPTIONS}
                    value={String(config.rf.scs_khz)}
                    onChange={(val) => updateNested('rf', 'scs_khz', parseInt(val || '30'))}
                  />

                  <Select
                    label="双工模式"
                    data={DUPLEX_OPTIONS}
                    value={config.rf.duplex_mode}
                    onChange={(val) => updateNested('rf', 'duplex_mode', val || 'TDD')}
                  />

                  <Select
                    label="MIMO层数"
                    data={MIMO_LAYERS}
                    value={String(config.rf.mimo_layers)}
                    onChange={(val) => updateNested('rf', 'mimo_layers', parseInt(val || '4'))}
                  />
                </SimpleGrid>

                {config.rf.duplex_mode === 'TDD' && (
                  <>
                    <Divider label="TDD配置" labelPosition="left" />
                    <SimpleGrid cols={2}>
                      <TextInput
                        label="TDD模式"
                        description="D=下行, U=上行, S=特殊子帧"
                        placeholder="DDDSU"
                        value={config.rf.tdd_config?.pattern || 'DDDSU'}
                        onChange={(e) =>
                          updateNested('rf', 'tdd_config', {
                            ...config.rf.tdd_config,
                            pattern: e.currentTarget.value,
                          })
                        }
                      />
                      <NumberInput
                        label="特殊子帧配置"
                        value={config.rf.tdd_config?.special_slot_config}
                        onChange={(val) =>
                          updateNested('rf', 'tdd_config', {
                            ...config.rf.tdd_config,
                            special_slot_config: val,
                          })
                        }
                        min={0}
                        max={13}
                      />
                    </SimpleGrid>
                  </>
                )}

                <Divider label="载波聚合" labelPosition="left" />
                <Switch
                  label="启用载波聚合 (CA)"
                  checked={config.rf.carrier_aggregation?.enabled || false}
                  onChange={(e) =>
                    updateNested('rf', 'carrier_aggregation', {
                      ...config.rf.carrier_aggregation,
                      enabled: e.currentTarget.checked,
                    })
                  }
                />

                {config.rf.carrier_aggregation?.enabled && (
                  <NumberInput
                    label="载波数量"
                    value={config.rf.carrier_aggregation?.num_carriers || 2}
                    onChange={(val) =>
                      updateNested('rf', 'carrier_aggregation', {
                        ...config.rf.carrier_aggregation,
                        num_carriers: val,
                      })
                    }
                    min={2}
                    max={8}
                  />
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Cell Parameters Section */}
        <Accordion.Item value="cell">
          <Accordion.Control icon={<IconBroadcast size={20} />}>
            <Group gap="xs">
              <Text fw={600}>小区参数 (Cell)</Text>
              <Badge size="sm" variant="light" color="cyan">
                PCI {config.cell.pci}
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <SimpleGrid cols={2}>
                  <NumberInput
                    label="PCI"
                    description="Physical Cell ID (0-1007)"
                    value={config.cell.pci}
                    onChange={(val) => updateNested('cell', 'pci', val || 1)}
                    min={0}
                    max={1007}
                  />

                  <NumberInput
                    label="TAC"
                    description="Tracking Area Code"
                    value={config.cell.tac}
                    onChange={(val) => updateNested('cell', 'tac', val || 1)}
                    min={0}
                  />

                  <NumberInput
                    label="Cell ID"
                    value={config.cell.cell_id}
                    onChange={(val) => updateNested('cell', 'cell_id', val || 1)}
                    min={0}
                  />

                  <Select
                    label="频段"
                    description={scenarioDefaults?.band ? `场景默认: ${scenarioDefaults.band}` : undefined}
                    data={BAND_OPTIONS}
                    value={config.cell.band}
                    onChange={(val) => updateNested('cell', 'band', val || 'n78')}
                    searchable
                  />
                </SimpleGrid>

                <Divider label="PLMN配置" labelPosition="left" />
                <SimpleGrid cols={2}>
                  <TextInput
                    label="MCC"
                    description="Mobile Country Code"
                    placeholder="460"
                    value={config.cell.plmn.mcc}
                    onChange={(e) =>
                      updateDeepNested('cell', ['plmn', 'mcc'], e.currentTarget.value)
                    }
                  />
                  <TextInput
                    label="MNC"
                    description="Mobile Network Code"
                    placeholder="00"
                    value={config.cell.plmn.mnc}
                    onChange={(e) =>
                      updateDeepNested('cell', ['plmn', 'mnc'], e.currentTarget.value)
                    }
                  />
                </SimpleGrid>

                <NumberInput
                  label="ARFCN"
                  description="E-UTRA/NR Absolute Radio Frequency Channel Number"
                  value={config.cell.earfcn_nrarfcn}
                  onChange={(val) => updateNested('cell', 'earfcn_nrarfcn', val)}
                />
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Power Parameters Section */}
        <Accordion.Item value="power">
          <Accordion.Control icon={<IconBolt size={20} />}>
            <Group gap="xs">
              <Text fw={600}>功率参数 (Power)</Text>
              <Badge size="sm" variant="light" color="orange">
                {config.power.total_power_dbm} dBm
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <NumberInput
                  label="总发射功率 (dBm)"
                  description="基站总发射功率"
                  value={config.power.total_power_dbm}
                  onChange={(val) => updateNested('power', 'total_power_dbm', val || 43)}
                  min={10}
                  max={60}
                />

                <SimpleGrid cols={2}>
                  <NumberInput
                    label="SSB功率 (dBm)"
                    description="同步信号块功率"
                    value={config.power.ssb_power_dbm}
                    onChange={(val) => updateNested('power', 'ssb_power_dbm', val)}
                    min={-60}
                    max={60}
                  />

                  <NumberInput
                    label="PDSCH功率偏移 (dB)"
                    value={config.power.pdsch_power_offset_db}
                    onChange={(val) => updateNested('power', 'pdsch_power_offset_db', val)}
                    min={-10}
                    max={10}
                  />
                </SimpleGrid>

                <Divider label="PUSCH功率控制" labelPosition="left" />
                <SimpleGrid cols={2}>
                  <NumberInput
                    label="P0 Nominal (dBm)"
                    value={config.power.pusch_power_control?.p0_nominal_dbm}
                    onChange={(val) =>
                      updateNested('power', 'pusch_power_control', {
                        ...config.power.pusch_power_control,
                        p0_nominal_dbm: val,
                      })
                    }
                    min={-202}
                    max={24}
                  />
                  <NumberInput
                    label="Alpha"
                    description="路损补偿因子"
                    value={config.power.pusch_power_control?.alpha}
                    onChange={(val) =>
                      updateNested('power', 'pusch_power_control', {
                        ...config.power.pusch_power_control,
                        alpha: val,
                      })
                    }
                    min={0}
                    max={1}
                    step={0.1}
                    decimalScale={1}
                  />
                </SimpleGrid>
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Deployment Section */}
        <Accordion.Item value="deployment">
          <Accordion.Control icon={<IconLocation size={20} />}>
            <Group gap="xs">
              <Text fw={600}>部署配置</Text>
              <Badge size="sm" variant="light">
                {config.deployment.num_base_stations} 基站
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <SimpleGrid cols={2}>
                  <NumberInput
                    label="基站数量"
                    value={config.deployment.num_base_stations}
                    onChange={(val) => updateNested('deployment', 'num_base_stations', val || 1)}
                    min={1}
                    max={20}
                  />

                  <Select
                    label="部署拓扑"
                    data={TOPOLOGY_OPTIONS}
                    value={config.deployment.topology}
                    onChange={(val) => updateNested('deployment', 'topology', val || 'single')}
                  />
                </SimpleGrid>

                {config.deployment.topology !== 'single' && config.deployment.topology !== 'custom' && (
                  <NumberInput
                    label="站间距 (m)"
                    value={config.deployment.inter_site_distance_m}
                    onChange={(val) => updateNested('deployment', 'inter_site_distance_m', val)}
                    min={50}
                    max={10000}
                  />
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Antenna Section */}
        <Accordion.Item value="antenna">
          <Accordion.Control icon={<IconAntenna size={20} />}>
            <Group gap="xs">
              <Text fw={600}>天线配置</Text>
              <Badge size="sm" variant="light" color="violet">
                {config.antenna.mimo_config}
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <SimpleGrid cols={2}>
                  <Select
                    label="天线类型"
                    data={ANTENNA_TYPES}
                    value={config.antenna.type}
                    onChange={(val) => updateNested('antenna', 'type', val || 'sector')}
                  />

                  <Select
                    label="MIMO配置"
                    data={MIMO_CONFIGS}
                    value={config.antenna.mimo_config}
                    onChange={(val) => updateNested('antenna', 'mimo_config', val || '4x4')}
                  />

                  <NumberInput
                    label="天线高度 (m)"
                    value={config.antenna.antenna_height_m}
                    onChange={(val) => updateNested('antenna', 'antenna_height_m', val || 25)}
                    min={1}
                    max={200}
                  />

                  <NumberInput
                    label="天线增益 (dBi)"
                    value={config.antenna.gain_dbi}
                    onChange={(val) => updateNested('antenna', 'gain_dbi', val || 18)}
                    min={0}
                    max={30}
                  />

                  <Select
                    label="极化方式"
                    data={POLARIZATION_OPTIONS}
                    value={config.antenna.polarization}
                    onChange={(val) => updateNested('antenna', 'polarization', val || 'dual')}
                  />
                </SimpleGrid>

                <Divider label="方向配置" labelPosition="left" />
                <SimpleGrid cols={3}>
                  <Stack gap="xs">
                    <Text size="sm">方位角: {config.antenna.azimuth_deg}°</Text>
                    <Slider
                      value={config.antenna.azimuth_deg}
                      onChange={(val) => updateNested('antenna', 'azimuth_deg', val)}
                      min={0}
                      max={360}
                      marks={[
                        { value: 0, label: 'N' },
                        { value: 90, label: 'E' },
                        { value: 180, label: 'S' },
                        { value: 270, label: 'W' },
                      ]}
                    />
                  </Stack>

                  <Stack gap="xs">
                    <Text size="sm">机械下倾: {config.antenna.mechanical_tilt_deg}°</Text>
                    <Slider
                      value={config.antenna.mechanical_tilt_deg}
                      onChange={(val) => updateNested('antenna', 'mechanical_tilt_deg', val)}
                      min={0}
                      max={15}
                    />
                  </Stack>

                  <Stack gap="xs">
                    <Text size="sm">电下倾: {config.antenna.electrical_tilt_deg || 0}°</Text>
                    <Slider
                      value={config.antenna.electrical_tilt_deg || 0}
                      onChange={(val) => updateNested('antenna', 'electrical_tilt_deg', val)}
                      min={0}
                      max={15}
                    />
                  </Stack>
                </SimpleGrid>

                {(config.antenna.type === 'massive_mimo' || config.antenna.type === 'aat') && (
                  <>
                    <Divider label="天线阵元" labelPosition="left" />
                    <SimpleGrid cols={2}>
                      <NumberInput
                        label="水平阵元数"
                        value={config.antenna.antenna_elements?.horizontal || 8}
                        onChange={(val) =>
                          updateNested('antenna', 'antenna_elements', {
                            ...config.antenna.antenna_elements,
                            horizontal: val,
                          })
                        }
                        min={1}
                        max={32}
                      />
                      <NumberInput
                        label="垂直阵元数"
                        value={config.antenna.antenna_elements?.vertical || 8}
                        onChange={(val) =>
                          updateNested('antenna', 'antenna_elements', {
                            ...config.antenna.antenna_elements,
                            vertical: val,
                          })
                        }
                        min={1}
                        max={32}
                      />
                    </SimpleGrid>
                  </>
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Beamforming Section */}
        <Accordion.Item value="beamforming">
          <Accordion.Control icon={<IconBuildingBroadcastTower size={20} />}>
            <Group gap="xs">
              <Text fw={600}>波束成形</Text>
              {config.beamforming?.enabled && (
                <Badge size="sm" variant="light" color="green">
                  {config.beamforming.num_ssb_beams} 波束
                </Badge>
              )}
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Switch
                  label="启用波束成形"
                  checked={config.beamforming?.enabled || false}
                  onChange={(e) =>
                    updateConfig('beamforming', {
                      ...config.beamforming,
                      enabled: e.currentTarget.checked,
                      mode: config.beamforming?.mode || 'dynamic',
                      num_ssb_beams: config.beamforming?.num_ssb_beams || 8,
                    })
                  }
                />

                {config.beamforming?.enabled && (
                  <>
                    <SimpleGrid cols={2}>
                      <Select
                        label="波束模式"
                        data={BEAM_MODES}
                        value={config.beamforming.mode}
                        onChange={(val) =>
                          updateNested('beamforming', 'mode', val || 'dynamic')
                        }
                      />

                      <Select
                        label="SSB波束数"
                        data={['4', '8', '16', '32', '64'].map(v => ({ value: v, label: `${v} 波束` }))}
                        value={String(config.beamforming.num_ssb_beams)}
                        onChange={(val) =>
                          updateNested('beamforming', 'num_ssb_beams', parseInt(val || '8'))
                        }
                      />

                      <NumberInput
                        label="波束扫描周期 (ms)"
                        value={config.beamforming.beam_sweep_period_ms}
                        onChange={(val) =>
                          updateNested('beamforming', 'beam_sweep_period_ms', val)
                        }
                        min={5}
                        max={160}
                      />
                    </SimpleGrid>

                    <Divider label="波束跟踪" labelPosition="left" />
                    <Switch
                      label="启用波束跟踪"
                      checked={config.beamforming.beam_tracking?.enabled || false}
                      onChange={(e) =>
                        updateNested('beamforming', 'beam_tracking', {
                          ...config.beamforming?.beam_tracking,
                          enabled: e.currentTarget.checked,
                        })
                      }
                    />

                    {config.beamforming.beam_tracking?.enabled && (
                      <NumberInput
                        label="更新周期 (ms)"
                        value={config.beamforming.beam_tracking.update_period_ms || 20}
                        onChange={(val) =>
                          updateNested('beamforming', 'beam_tracking', {
                            ...config.beamforming?.beam_tracking,
                            update_period_ms: val,
                          })
                        }
                        min={1}
                        max={100}
                      />
                    )}
                  </>
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Handover Section */}
        <Accordion.Item value="handover">
          <Accordion.Control icon={<IconArrowsExchange size={20} />}>
            <Group gap="xs">
              <Text fw={600}>切换配置</Text>
              {config.handover?.enabled && (
                <Badge size="sm" variant="light" color="teal">已启用</Badge>
              )}
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Switch
                  label="启用切换"
                  description="配置小区间切换参数"
                  checked={config.handover?.enabled || false}
                  onChange={(e) =>
                    updateConfig('handover', {
                      ...config.handover,
                      enabled: e.currentTarget.checked,
                      a3_offset_db: config.handover?.a3_offset_db || 3,
                      hysteresis_db: config.handover?.hysteresis_db || 1,
                      time_to_trigger_ms: config.handover?.time_to_trigger_ms || 256,
                    })
                  }
                />

                {config.handover?.enabled && (
                  <SimpleGrid cols={3}>
                    <NumberInput
                      label="A3偏移 (dB)"
                      description="Event A3 Offset"
                      value={config.handover.a3_offset_db}
                      onChange={(val) => updateNested('handover', 'a3_offset_db', val || 3)}
                      min={-15}
                      max={15}
                      step={0.5}
                      decimalScale={1}
                    />

                    <NumberInput
                      label="迟滞 (dB)"
                      description="Hysteresis"
                      value={config.handover.hysteresis_db}
                      onChange={(val) => updateNested('handover', 'hysteresis_db', val || 1)}
                      min={0}
                      max={15}
                      step={0.5}
                      decimalScale={1}
                    />

                    <NumberInput
                      label="触发时间 (ms)"
                      description="Time to Trigger"
                      value={config.handover.time_to_trigger_ms}
                      onChange={(val) => updateNested('handover', 'time_to_trigger_ms', val || 256)}
                      min={0}
                      max={5120}
                    />
                  </SimpleGrid>
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>

      {/* Verification Options */}
      <Paper p="md" withBorder>
        <Stack gap="sm">
          <Text fw={600} size="sm">验证选项</Text>
          <SimpleGrid cols={3}>
            <Switch
              label="验证覆盖"
              checked={config.verify_coverage}
              onChange={(e) => updateConfig('verify_coverage', e.currentTarget.checked)}
            />
            <Switch
              label="验证邻接关系"
              checked={config.verify_neighbor_relations}
              onChange={(e) => updateConfig('verify_neighbor_relations', e.currentTarget.checked)}
            />
            <Switch
              label="验证信号"
              checked={config.verify_signal}
              onChange={(e) => updateConfig('verify_signal', e.currentTarget.checked)}
            />
          </SimpleGrid>
          <NumberInput
            label="超时时间 (秒)"
            value={config.timeout_seconds}
            onChange={(val) => updateConfig('timeout_seconds', typeof val === 'number' ? val : 300)}
            min={60}
            max={1800}
          />
        </Stack>
      </Paper>
    </Stack>
  )
}
