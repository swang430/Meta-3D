/**
 * Network Step Editor (Step 2)
 *
 * Core Network layer configuration:
 * - Authentication
 * - IP Allocation
 * - PDU Session
 * - QoS
 * - Application Tests
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
  Button,
  ActionIcon,
  Card,
} from '@mantine/core'
import { IconPlus, IconTrash, IconNetwork, IconKey, IconRouter, IconGauge, IconApps } from '@tabler/icons-react'
import type { NetworkStepConfig, ApplicationTestConfig, ApplicationType } from '../../types/roadTest'

interface Props {
  value?: NetworkStepConfig
  onChange: (config: NetworkStepConfig) => void
}

const DEFAULT_CONFIG: NetworkStepConfig = {
  authentication: {
    method: 'open',
  },
  ip_config: {
    mode: 'dhcp',
  },
  pdu_session: {
    type: 'ipv4',
    sst: 1,
    dnn: 'internet',
  },
  qos: {
    fiveqi: 9,
  },
  applications: {
    enabled: false,
    tests: [],
    sequential: true,
  },
  verify_registration: true,
  verify_pdu_session: true,
  timeout_seconds: 300,
}

const AUTH_METHODS = [
  { value: 'open', label: 'Open (无鉴权)' },
  { value: '5g-aka', label: '5G-AKA' },
  { value: 'eap-tls', label: 'EAP-TLS' },
  { value: 'sim', label: 'SIM卡鉴权' },
]

const IP_MODES = [
  { value: 'dhcp', label: 'DHCP (动态分配)' },
  { value: 'static', label: 'Static (静态IP)' },
  { value: 'pdn', label: 'PDN (运营商分配)' },
]

const PDU_TYPES = [
  { value: 'ipv4', label: 'IPv4' },
  { value: 'ipv6', label: 'IPv6' },
  { value: 'ipv4v6', label: 'IPv4v6 (双栈)' },
  { value: 'ethernet', label: 'Ethernet' },
]

const SLICE_TYPES = [
  { value: '1', label: 'SST 1 - eMBB (增强移动宽带)' },
  { value: '2', label: 'SST 2 - URLLC (超可靠低延迟)' },
  { value: '3', label: 'SST 3 - MIoT (大规模物联网)' },
]

const FIVEQI_OPTIONS = [
  { value: '1', label: '5QI 1 - 会话语音 (GBR)' },
  { value: '2', label: '5QI 2 - 会话视频 (GBR)' },
  { value: '5', label: '5QI 5 - IMS信令 (Non-GBR)' },
  { value: '6', label: '5QI 6 - 视频流 (Non-GBR)' },
  { value: '7', label: '5QI 7 - 语音视频游戏 (Non-GBR)' },
  { value: '8', label: '5QI 8 - TCP应用 (Non-GBR)' },
  { value: '9', label: '5QI 9 - 默认互联网 (Non-GBR)' },
  { value: '80', label: '5QI 80 - URLLC (GBR)' },
  { value: '82', label: '5QI 82 - AR/VR (GBR)' },
  { value: '83', label: '5QI 83 - V2X消息 (GBR)' },
]

const APP_TYPES: { value: ApplicationType; label: string; icon: string }[] = [
  { value: 'ftp_dl', label: 'FTP 下载', icon: '📥' },
  { value: 'ftp_ul', label: 'FTP 上传', icon: '📤' },
  { value: 'udp_dl', label: 'UDP 下行', icon: '🔽' },
  { value: 'udp_ul', label: 'UDP 上行', icon: '🔼' },
  { value: 'iperf', label: 'iPerf 测试', icon: '📊' },
  { value: 'video_streaming', label: '视频流', icon: '🎬' },
  { value: 'video_call', label: '视频通话', icon: '📹' },
  { value: 'xr_vr', label: 'VR应用', icon: '🥽' },
  { value: 'xr_ar', label: 'AR应用', icon: '👓' },
  { value: 'xr_cloud', label: '云XR', icon: '☁️' },
  { value: 'voip', label: 'VoIP通话', icon: '📞' },
  { value: 'email', label: '邮件收发', icon: '📧' },
  { value: 'web_browsing', label: '网页浏览', icon: '🌐' },
  { value: 'ping', label: 'Ping测试', icon: '📡' },
]

// Deep merge helper to ensure all nested properties have defaults
function mergeWithDefaults(value?: Partial<NetworkStepConfig>): NetworkStepConfig {
  if (!value) return DEFAULT_CONFIG
  return {
    authentication: {
      ...DEFAULT_CONFIG.authentication,
      ...value.authentication,
    },
    ip_config: {
      ...DEFAULT_CONFIG.ip_config,
      ...value.ip_config,
    },
    pdu_session: {
      ...DEFAULT_CONFIG.pdu_session,
      ...value.pdu_session,
    },
    qos: {
      ...DEFAULT_CONFIG.qos,
      ...value.qos,
    },
    applications: {
      ...DEFAULT_CONFIG.applications,
      ...value.applications,
      tests: value.applications?.tests || DEFAULT_CONFIG.applications.tests,
    },
    verify_registration: value.verify_registration ?? DEFAULT_CONFIG.verify_registration,
    verify_pdu_session: value.verify_pdu_session ?? DEFAULT_CONFIG.verify_pdu_session,
    timeout_seconds: value.timeout_seconds ?? DEFAULT_CONFIG.timeout_seconds,
  }
}

export function NetworkStepEditor({ value, onChange }: Props) {
  const config = mergeWithDefaults(value)

  const updateConfig = <K extends keyof NetworkStepConfig>(
    key: K,
    val: NetworkStepConfig[K]
  ) => {
    onChange({ ...config, [key]: val })
  }

  const updateNested = <K extends keyof NetworkStepConfig>(
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

  const addApplicationTest = (type: ApplicationType) => {
    const newTest: ApplicationTestConfig = {
      type,
      enabled: true,
    }
    onChange({
      ...config,
      applications: {
        ...config.applications,
        tests: [...config.applications.tests, newTest],
      },
    })
  }

  const removeApplicationTest = (index: number) => {
    const tests = [...config.applications.tests]
    tests.splice(index, 1)
    onChange({
      ...config,
      applications: {
        ...config.applications,
        tests,
      },
    })
  }

  return (
    <Stack gap="md">
      <Accordion variant="separated" multiple defaultValue={['auth', 'ip', 'pdu', 'qos']}>
        {/* Authentication Section */}
        <Accordion.Item value="auth">
          <Accordion.Control icon={<IconKey size={20} />}>
            <Group gap="xs">
              <Text fw={600}>鉴权配置</Text>
              <Badge size="sm" variant="light">
                {AUTH_METHODS.find(m => m.value === config.authentication.method)?.label}
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Select
                  label="鉴权方式"
                  description="终端接入网络的身份验证方式"
                  data={AUTH_METHODS}
                  value={config.authentication.method}
                  onChange={(val) => updateNested('authentication', 'method', val || 'open')}
                />

                {config.authentication.method === 'sim' && (
                  <>
                    <Divider label="SIM卡配置" labelPosition="left" />
                    <SimpleGrid cols={2}>
                      <TextInput
                        label="IMSI"
                        description="国际移动用户识别码"
                        placeholder="460001234567890"
                        value={config.authentication.sim_profile?.imsi || ''}
                        onChange={(e) =>
                          updateNested('authentication', 'sim_profile', {
                            ...config.authentication.sim_profile,
                            imsi: e.currentTarget.value,
                          })
                        }
                      />
                      <TextInput
                        label="Ki"
                        description="鉴权密钥"
                        placeholder="可选"
                        value={config.authentication.sim_profile?.ki || ''}
                        onChange={(e) =>
                          updateNested('authentication', 'sim_profile', {
                            ...config.authentication.sim_profile,
                            ki: e.currentTarget.value,
                          })
                        }
                      />
                    </SimpleGrid>
                  </>
                )}

                {config.authentication.method === 'eap-tls' && (
                  <>
                    <Divider label="证书配置" labelPosition="left" />
                    <Switch
                      label="启用证书鉴权"
                      checked={config.authentication.certificate?.enabled || false}
                      onChange={(e) =>
                        updateNested('authentication', 'certificate', {
                          ...config.authentication.certificate,
                          enabled: e.currentTarget.checked,
                        })
                      }
                    />
                    {config.authentication.certificate?.enabled && (
                      <TextInput
                        label="证书文件路径"
                        placeholder="/path/to/cert.pem"
                        value={config.authentication.certificate?.cert_file || ''}
                        onChange={(e) =>
                          updateNested('authentication', 'certificate', {
                            ...config.authentication.certificate,
                            cert_file: e.currentTarget.value,
                          })
                        }
                      />
                    )}
                  </>
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* IP Configuration Section */}
        <Accordion.Item value="ip">
          <Accordion.Control icon={<IconNetwork size={20} />}>
            <Group gap="xs">
              <Text fw={600}>IP分配配置</Text>
              <Badge size="sm" variant="light">
                {IP_MODES.find(m => m.value === config.ip_config.mode)?.label}
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Select
                  label="IP分配模式"
                  data={IP_MODES}
                  value={config.ip_config.mode}
                  onChange={(val) => updateNested('ip_config', 'mode', val || 'dhcp')}
                />

                <TextInput
                  label="APN"
                  description="接入点名称"
                  placeholder="internet"
                  value={config.ip_config.apn || ''}
                  onChange={(e) => updateNested('ip_config', 'apn', e.currentTarget.value)}
                />

                {config.ip_config.mode === 'static' && (
                  <>
                    <Divider label="IPv4配置" labelPosition="left" />
                    <SimpleGrid cols={2}>
                      <TextInput
                        label="IP地址"
                        placeholder="192.168.1.100"
                        value={config.ip_config.ipv4?.address || ''}
                        onChange={(e) =>
                          updateNested('ip_config', 'ipv4', {
                            ...config.ip_config.ipv4,
                            address: e.currentTarget.value,
                          })
                        }
                      />
                      <TextInput
                        label="子网掩码"
                        placeholder="255.255.255.0"
                        value={config.ip_config.ipv4?.subnet || ''}
                        onChange={(e) =>
                          updateNested('ip_config', 'ipv4', {
                            ...config.ip_config.ipv4,
                            subnet: e.currentTarget.value,
                          })
                        }
                      />
                      <TextInput
                        label="网关"
                        placeholder="192.168.1.1"
                        value={config.ip_config.ipv4?.gateway || ''}
                        onChange={(e) =>
                          updateNested('ip_config', 'ipv4', {
                            ...config.ip_config.ipv4,
                            gateway: e.currentTarget.value,
                          })
                        }
                      />
                      <TextInput
                        label="DNS服务器"
                        placeholder="8.8.8.8"
                        value={config.ip_config.ipv4?.dns?.join(', ') || ''}
                        onChange={(e) =>
                          updateNested('ip_config', 'ipv4', {
                            ...config.ip_config.ipv4,
                            dns: e.currentTarget.value.split(',').map(s => s.trim()),
                          })
                        }
                      />
                    </SimpleGrid>
                  </>
                )}

                <Switch
                  label="启用IPv6"
                  checked={config.ip_config.ipv6?.enabled || false}
                  onChange={(e) =>
                    updateNested('ip_config', 'ipv6', {
                      ...config.ip_config.ipv6,
                      enabled: e.currentTarget.checked,
                    })
                  }
                />
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* PDU Session Section */}
        <Accordion.Item value="pdu">
          <Accordion.Control icon={<IconRouter size={20} />}>
            <Group gap="xs">
              <Text fw={600}>PDU会话 / 网络切片</Text>
              <Badge size="sm" variant="light" color="cyan">
                SST {config.pdu_session.sst}
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <SimpleGrid cols={2}>
                  <Select
                    label="PDU会话类型"
                    data={PDU_TYPES}
                    value={config.pdu_session.type}
                    onChange={(val) => updateNested('pdu_session', 'type', val || 'ipv4')}
                  />

                  <Select
                    label="切片类型 (SST)"
                    description="Slice/Service Type"
                    data={SLICE_TYPES}
                    value={String(config.pdu_session.sst)}
                    onChange={(val) => updateNested('pdu_session', 'sst', parseInt(val || '1'))}
                  />

                  <TextInput
                    label="切片区分符 (SD)"
                    description="可选，用于区分相同SST的不同切片"
                    placeholder="000001"
                    value={config.pdu_session.sd || ''}
                    onChange={(e) => updateNested('pdu_session', 'sd', e.currentTarget.value)}
                  />

                  <TextInput
                    label="DNN"
                    description="Data Network Name"
                    placeholder="internet"
                    value={config.pdu_session.dnn}
                    onChange={(e) => updateNested('pdu_session', 'dnn', e.currentTarget.value)}
                  />
                </SimpleGrid>
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* QoS Section */}
        <Accordion.Item value="qos">
          <Accordion.Control icon={<IconGauge size={20} />}>
            <Group gap="xs">
              <Text fw={600}>QoS配置</Text>
              <Badge size="sm" variant="light" color="orange">
                5QI {config.qos.fiveqi}
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Select
                  label="5QI"
                  description="5G QoS Identifier"
                  data={FIVEQI_OPTIONS}
                  value={String(config.qos.fiveqi)}
                  onChange={(val) => updateNested('qos', 'fiveqi', parseInt(val || '9'))}
                />

                <SimpleGrid cols={2}>
                  <NumberInput
                    label="优先级"
                    description="1-127, 数字越小优先级越高"
                    value={config.qos.priority_level}
                    onChange={(val) => updateNested('qos', 'priority_level', val)}
                    min={1}
                    max={127}
                  />

                  <NumberInput
                    label="包延迟预算 (ms)"
                    value={config.qos.packet_delay_budget_ms}
                    onChange={(val) => updateNested('qos', 'packet_delay_budget_ms', val)}
                    min={1}
                    max={500}
                  />
                </SimpleGrid>

                <Divider label="GBR配置" labelPosition="left" />
                <Switch
                  label="启用GBR (保证比特率)"
                  description="适用于语音、视频等需要保证带宽的业务"
                  checked={config.qos.gbr?.enabled || false}
                  onChange={(e) =>
                    updateNested('qos', 'gbr', {
                      ...config.qos.gbr,
                      enabled: e.currentTarget.checked,
                    })
                  }
                />

                {config.qos.gbr?.enabled && (
                  <SimpleGrid cols={2}>
                    <NumberInput
                      label="下行GBR (kbps)"
                      value={config.qos.gbr?.dl_gbr_kbps}
                      onChange={(val) =>
                        updateNested('qos', 'gbr', {
                          ...config.qos.gbr,
                          dl_gbr_kbps: val,
                        })
                      }
                      min={0}
                    />
                    <NumberInput
                      label="上行GBR (kbps)"
                      value={config.qos.gbr?.ul_gbr_kbps}
                      onChange={(val) =>
                        updateNested('qos', 'gbr', {
                          ...config.qos.gbr,
                          ul_gbr_kbps: val,
                        })
                      }
                      min={0}
                    />
                  </SimpleGrid>
                )}
              </Stack>
            </Paper>
          </Accordion.Panel>
        </Accordion.Item>

        {/* Application Tests Section */}
        <Accordion.Item value="apps">
          <Accordion.Control icon={<IconApps size={20} />}>
            <Group gap="xs">
              <Text fw={600}>应用层测试</Text>
              {config.applications.enabled && (
                <Badge size="sm" variant="light" color="green">
                  {config.applications.tests.length} 个测试
                </Badge>
              )}
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Paper p="md" withBorder>
              <Stack gap="md">
                <Switch
                  label="启用应用层测试"
                  description="在测试期间运行FTP、UDP、视频流等应用测试"
                  checked={config.applications.enabled}
                  onChange={(e) =>
                    updateNested('applications', 'enabled', e.currentTarget.checked)
                  }
                />

                {config.applications.enabled && (
                  <>
                    <Switch
                      label="顺序执行"
                      description="按顺序依次执行测试，否则并行执行"
                      checked={config.applications.sequential}
                      onChange={(e) =>
                        updateNested('applications', 'sequential', e.currentTarget.checked)
                      }
                    />

                    <Divider label="添加测试" labelPosition="left" />
                    <Group gap="xs" wrap="wrap">
                      {APP_TYPES.map((app) => (
                        <Button
                          key={app.value}
                          size="xs"
                          variant="light"
                          leftSection={<span>{app.icon}</span>}
                          onClick={() => addApplicationTest(app.value)}
                        >
                          {app.label}
                        </Button>
                      ))}
                    </Group>

                    {config.applications.tests.length > 0 && (
                      <>
                        <Divider label="已配置的测试" labelPosition="left" />
                        <Stack gap="xs">
                          {config.applications.tests.map((test, index) => {
                            const appInfo = APP_TYPES.find(a => a.value === test.type)
                            return (
                              <Card key={index} withBorder p="sm">
                                <Group justify="space-between">
                                  <Group gap="xs">
                                    <Text>{appInfo?.icon}</Text>
                                    <Text fw={500}>{appInfo?.label || test.type}</Text>
                                    <Switch
                                      size="xs"
                                      checked={test.enabled}
                                      onChange={(e) => {
                                        const tests = [...config.applications.tests]
                                        tests[index] = { ...test, enabled: e.currentTarget.checked }
                                        updateNested('applications', 'tests', tests)
                                      }}
                                    />
                                  </Group>
                                  <ActionIcon
                                    color="red"
                                    variant="subtle"
                                    onClick={() => removeApplicationTest(index)}
                                  >
                                    <IconTrash size={16} />
                                  </ActionIcon>
                                </Group>
                              </Card>
                            )
                          })}
                        </Stack>
                      </>
                    )}
                  </>
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
          <SimpleGrid cols={2}>
            <Switch
              label="验证终端注册"
              checked={config.verify_registration}
              onChange={(e) => updateConfig('verify_registration', e.currentTarget.checked)}
            />
            <Switch
              label="验证PDU会话建立"
              checked={config.verify_pdu_session}
              onChange={(e) => updateConfig('verify_pdu_session', e.currentTarget.checked)}
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
