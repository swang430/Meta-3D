import { Stack, Text, Alert, List, ThemeIcon, Table, Group, Button, Card, Badge, Loader } from '@mantine/core'
import { IconCheck, IconX, IconInfoCircle, IconAntenna, IconRotate3d, IconAlertTriangle } from '@tabler/icons-react'

import { DUTCapabilityCrosscheckCard } from './DUTCapabilityCrosscheckCard'
import {
  describePathLossApplication,
  describePathLossSelection,
} from './pathLossApplication'
import { describeRfKpiEvidence, formatRfKpiValue } from './rfKpiEvidence'
import {
  describePrecheckMessages,
  describePrecheckOutcome,
  describeQuietZoneEvidence,
} from './quietZoneEvidence'

export function PrecheckPhase({ data }: { data: any }) {
  if (!data) return <Text c="dimmed">No data</Text>
  const pathLossSelection = describePathLossSelection(
    data.path_loss_calibration_reason,
    data.path_loss_calibration_valid === true,
  )
  const precheckOutcome = describePrecheckOutcome(
    data.overall_pass,
    data.quiet_zone_evidence,
    data.operational_ready,
  )
  const quietZoneView = describeQuietZoneEvidence(data.quiet_zone_evidence)
  const precheckMessages = describePrecheckMessages(data.messages, data.quiet_zone_evidence)
  
  return (
    <Stack gap="md">
      <Alert
        color={precheckOutcome.color}
        title={precheckOutcome.title}
        icon={precheckOutcome.color === 'green' ? <IconCheck /> : precheckOutcome.color === 'red' ? <IconX /> : <IconAlertTriangle />}
      >
        {precheckOutcome.message}
      </Alert>

      {/* Only a current operational gate failure may publish red failure
          reasons. A legacy overall_pass=false can represent an untrusted
          quiet-zone verdict and must remain UNKNOWN. */}
      {data.overall_pass === false && data.operational_ready === false && (() => {
        const reasons: string[] = []
        if (data.critical_instruments_online === false) reasons.push('关键仪表离线 — 无法继续')
        if (data.cal_pass === false && data.cal_pass_reason) reasons.push(`校准门未通过：${data.cal_pass_reason}`)
        if (data.dut_pass === false && data.dut_pass_reason) reasons.push(`DUT 门未通过：${data.dut_pass_reason}`)
        if (quietZoneView.verified && data.quiet_zone_pass === false) reasons.push(`静区纹波超阈值（±${data.quiet_zone_ripple_db} dB）`)
        if (data.ue_capability_pass === false) reasons.push('UE 能力不足（max_dl_layers < 请求层数）')
        if (typeof data.error_message === 'string' && reasons.length === 0) reasons.push(data.error_message)
        const strictGateFailed = data.dut_pass === false || data.cal_pass === false
        return (
          <Alert color="red" variant="light" title="失败原因" icon={<IconX />}>
            <List spacing="xs" size="sm">
              {reasons.map((r, i) => (
                <List.Item key={i}>{r}</List.Item>
              ))}
            </List>
            {strictGateFailed && (
              <Text size="sm" mt="sm" c="dimmed">
                严格门只在<strong>接了真实仪表</strong>时生效（mock 模式会自动跳过）。现场真测请
                完成校准；DUT 连接会在 MEASURE 按本次 TestCase 初始化后自动建立并核对。
                若只是想在真仪表下空跑调试，可打开顶部「<strong>强制跳过严格门</strong>」
                开关后点「重置会话」。
              </Text>
            )}
          </Alert>
        )
      })()}

      {Array.isArray(data.warnings) && data.warnings.length > 0 && (
        <Alert color="yellow" variant="light" title="预检警告">
          <List spacing="xs" size="sm">
            {data.warnings.map((w: string, i: number) => (
              <List.Item key={i}>{w}</List.Item>
            ))}
          </List>
        </Alert>
      )}

      {/* 阶段 4: DUT 声明 vs 实测协商交叉核对 + operator 显式反写 */}
      <DUTCapabilityCrosscheckCard data={data} />

      <Card withBorder>
        <Text fw={500} mb="sm">预检详情</Text>
        <List spacing="sm" size="sm">
          {precheckMessages.map((msg: string, i: number) => {
            const isError = msg.includes('FAIL') || msg.includes('异常')
            // 未判定/诊断代理类消息用黄色警告色，与正式 PASS 区分。
            const isWarn = !isError && (msg.includes('未验证') || msg.includes('未判定') || msg.includes('诊断代理') || msg.includes('⚠️'))
            const color = isError ? 'red' : isWarn ? 'yellow' : 'blue'
            return (
              <List.Item
                key={i}
                icon={
                  <ThemeIcon color={color} size={20} radius="xl">
                    {isError ? <IconX size={12} /> : isWarn ? <IconAlertTriangle size={12} /> : <IconInfoCircle size={12} />}
                  </ThemeIcon>
                }
              >
                {msg}
              </List.Item>
            )
          })}
        </List>
      </Card>

      <Table striped>
        <Table.Tbody>
          <Table.Tr><Table.Td>暗室 ID</Table.Td><Table.Td>{data.chamber_id}</Table.Td></Table.Tr>
          <Table.Tr><Table.Td>路损证书状态</Table.Td><Table.Td>{pathLossSelection}</Table.Td></Table.Tr>
          <Table.Tr>
            <Table.Td>静区纹波 (Ripple)</Table.Td>
            <Table.Td>
              {quietZoneView.formalRipple}
              <Text span c="yellow.8" fw={600} ml={6}>
                ⚠️ {quietZoneView.label}
              </Text>
            </Table.Td>
          </Table.Tr>
          {quietZoneView.proxyRipple && (
            <Table.Tr>
              <Table.Td>ProbePattern 峰值离散</Table.Td>
              <Table.Td>
                {quietZoneView.proxyRipple}
                <Text span c="yellow.8" fw={600} ml={6}>
                  诊断代理，非静区实测
                </Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
    </Stack>
  )
}

export function ReferencePhase({ 
  data, 
  status, 
  onConfirm 
}: { 
  data: any, 
  status: string, 
  onConfirm: () => void 
}) {
  return (
    <Stack gap="md">
      <Alert color="blue" title="参考天线测量 (TRP)" icon={<IconAntenna />}>
        为了准确计算路径损耗和系统增益，请手动在暗室中心(静区)安装标准增益喇叭天线。
      </Alert>
      
      {status === 'waiting' && (
        <Card withBorder bg="yellow.0">
          <Group justify="space-between" align="center">
            <Text fw={500} c="yellow.8">等待人工确认: 请安装天线后点击继续</Text>
            <Button color="yellow" onClick={onConfirm}>已安装, 开始参考测量</Button>
          </Group>
        </Card>
      )}
      
      {status === 'running' && (
        <Group><Loader size="sm" /><Text>正在执行参考测量...</Text></Group>
      )}
      
      {data?.measured_trp_dbm && (
        <>
          {data.trp_verified !== true && (
            <Alert color="yellow" variant="light" icon={<IconAlertTriangle />} title="参考 TRP 未验证（兜底默认值）">
              无 signalAnalyzer 实测，TRP 与补偿值为兜底默认值、非实测。真实参考测量需 SA 入 HAL（P0-4）+ 喇叭天线。
            </Alert>
          )}
          <Table striped>
            <Table.Tbody>
              <Table.Tr><Table.Td>参考天线增益</Table.Td><Table.Td>{data.antenna_gain_dbi} dBi</Table.Td></Table.Tr>
              <Table.Tr>
                <Table.Td>测得 TRP</Table.Td>
                <Table.Td>
                  {data.measured_trp_dbm.toFixed(1)} dBm
                  {data.trp_verified !== true && (
                    <Text span c="yellow.8" fw={600} ml={6}>⚠️ 未验证（兜底值，非实测）</Text>
                  )}
                </Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>计算补偿值</Table.Td>
                <Table.Td>
                  {data.compensation_factor_db.toFixed(1)} dB
                  {data.trp_verified !== true && (
                    <Text span c="yellow.8" fw={600} ml={6}>⚠️ 非实测</Text>
                  )}
                </Table.Td>
              </Table.Tr>
            </Table.Tbody>
          </Table>
        </>
      )}
    </Stack>
  )
}

export function MIMOTestPhase({ data, config: _config }: { data: any, config: any }) {
  if (!data) return <Text c="dimmed">等待测试...</Text>
  const pathLossView = describePathLossApplication(data.path_loss_application)
  const rfKpiView = describeRfKpiEvidence(data.formal_rf_kpi_verified)
  
  return (
    <Stack gap="md">
      <Alert color="grape" title="静态 MIMO OTA 测量" icon={<IconRotate3d />}>
        系统正在或已完成在多个转台方位的 KPI 测量。CDL 模型为 {data.cdl_model_name}。
      </Alert>

      {/* managed RF attach 把真实 UE 能力核对延期到本次 RF 初始化及 attach 后，
          结果位于 MEASURE 的 controlled_dut_attach；继续复用既有卡片与“采纳
          实测值”动作，不能让证据换阶段后从 UI 消失。 */}
      <DUTCapabilityCrosscheckCard data={data.controlled_dut_attach} />

      <Alert
        color={pathLossView.color}
        variant="light"
        icon={pathLossView.showCompensationValue ? <IconCheck /> : <IconAlertTriangle />}
        title={pathLossView.title}
      >
        <Text size="sm">{pathLossView.message}</Text>
        <Text size="sm" mt={4}>
          证书：{pathLossView.certificateId ?? '—'}；来源：{pathLossView.sourceLabel}
        </Text>
        {pathLossView.showCompensationValue && typeof data.path_loss_compensation_db === 'number' && (
          <Text size="sm" mt={4}>应用补偿：{data.path_loss_compensation_db.toFixed(2)} dB</Text>
        )}
      </Alert>

      <Alert
        color={rfKpiView.color}
        variant="light"
        icon={rfKpiView.verified ? <IconCheck /> : <IconAlertTriangle />}
        title={rfKpiView.title}
      >
        {rfKpiView.message}
      </Alert>

      {data.azimuth_results?.length > 0 && (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>方位角 (°)</Table.Th>
              <Table.Th>RSRP (dBm)</Table.Th>
              <Table.Th>SINR (dB)</Table.Th>
              <Table.Th>吞吐量 (Mbps)</Table.Th>
              <Table.Th>Rank</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.azimuth_results.map((az: any) => (
              <Table.Tr key={az.azimuth_deg}>
                <Table.Td>{az.azimuth_deg}</Table.Td>
                <Table.Td>{formatRfKpiValue(az.rsrp_dbm, rfKpiView.verified, 1)}</Table.Td>
                <Table.Td>{formatRfKpiValue(az.sinr_db, rfKpiView.verified, 1)}</Table.Td>
                <Table.Td>{az.throughput_mbps}</Table.Td>
                <Table.Td>{formatRfKpiValue(az.rank_indicator, rfKpiView.verified, 2)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  )
}

export function AnalysisPhase({ data }: { data: any }) {
  if (!data) return <Text c="dimmed">无分析数据</Text>
  
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start">
        <Text fw={500} size="lg">判定结果：
          <Badge 
            size="xl" 
            color={data.verdict === 'PASS' ? 'green' : data.verdict === 'FAIL' ? 'red' : 'yellow'}
          >
            {data.verdict}
          </Badge>
        </Text>
      </Group>

      <Card withBorder>
        <List spacing="sm" size="sm">
          {data.details?.map((msg: string, i: number) => (
            <List.Item
              key={i}
              icon={
                <ThemeIcon color={msg.includes('FAIL') ? 'red' : msg.includes('PASS') ? 'green' : 'blue'} size={20} radius="xl">
                  {msg.includes('FAIL') ? <IconX size={12} /> : msg.includes('PASS') ? <IconCheck size={12} /> : <IconInfoCircle size={12} />}
                </ThemeIcon>
              }
            >
              {msg}
            </List.Item>
          ))}
        </List>
      </Card>
    </Stack>
  )
}

export function ReportPhase({ data }: { data: any }) {
  if (!data?.report_id) return <Text c="dimmed">报告未生成</Text>
  return (
    <Alert color="teal" title="测试完成" icon={<IconCheck />}>
      报告已生成并归档。报告 ID: <strong>{data.report_id}</strong>
    </Alert>
  )
}
