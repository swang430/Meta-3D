import { Stack, Text, Alert, List, ThemeIcon, Table, Group, Button, Card, Badge, Loader } from '@mantine/core'
import { IconCheck, IconX, IconAlertCircle, IconInfoCircle, IconAntenna, IconRotate3d } from '@tabler/icons-react'
import type { SessionResponse } from './api'

export function PrecheckPhase({ data }: { data: any }) {
  if (!data) return <Text c="dimmed">No data</Text>
  
  return (
    <Stack gap="md">
      <Alert 
        color={data.overall_pass ? 'green' : 'red'} 
        title={data.overall_pass ? "预检通过" : "预检失败"}
        icon={data.overall_pass ? <IconCheck /> : <IconX />}
      >
        {data.overall_pass ? "所有系统与校准状态正常，可进行下一步测试。" : "系统存在异常，请检查以下信息。"}
      </Alert>
      
      <Card withBorder>
        <Text fw={500} mb="sm">预检详情</Text>
        <List spacing="sm" size="sm">
          {data.messages?.map((msg: string, i: number) => (
            <List.Item
              key={i}
              icon={
                <ThemeIcon color={msg.includes('FAIL') || msg.includes('异常') ? 'red' : 'blue'} size={20} radius="xl">
                  {msg.includes('FAIL') || msg.includes('异常') ? <IconX size={12} /> : <IconInfoCircle size={12} />}
                </ThemeIcon>
              }
            >
              {msg}
            </List.Item>
          ))}
        </List>
      </Card>
      
      <Table striped>
        <Table.Tbody>
          <Table.Tr><Table.Td>暗室 ID</Table.Td><Table.Td>{data.chamber_id}</Table.Td></Table.Tr>
          <Table.Tr><Table.Td>校准有效性</Table.Td><Table.Td>{data.calibration_valid ? '有效' : '已过期'}</Table.Td></Table.Tr>
          <Table.Tr><Table.Td>静区纹波 (Ripple)</Table.Td><Table.Td>±{data.quiet_zone_ripple_db} dB</Table.Td></Table.Tr>
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
        <Table striped>
          <Table.Tbody>
            <Table.Tr><Table.Td>参考天线增益</Table.Td><Table.Td>{data.antenna_gain_dbi} dBi</Table.Td></Table.Tr>
            <Table.Tr><Table.Td>测得 TRP</Table.Td><Table.Td>{data.measured_trp_dbm.toFixed(1)} dBm</Table.Td></Table.Tr>
            <Table.Tr><Table.Td>计算补偿值</Table.Td><Table.Td>{data.compensation_factor_db.toFixed(1)} dB</Table.Td></Table.Tr>
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  )
}

export function MIMOTestPhase({ data, config }: { data: any, config: any }) {
  if (!data) return <Text c="dimmed">等待测试...</Text>
  
  return (
    <Stack gap="md">
      <Alert color="grape" title="静态 MIMO OTA 测量" icon={<IconRotate3d />}>
        系统正在或已完成在多个转台方位的 KPI 测量。CDL 模型为 {data.cdl_model_name}。
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
                <Table.Td>{az.rsrp_dbm}</Table.Td>
                <Table.Td>{az.sinr_db}</Table.Td>
                <Table.Td>{az.throughput_mbps}</Table.Td>
                <Table.Td>{az.rank_indicator}</Table.Td>
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
