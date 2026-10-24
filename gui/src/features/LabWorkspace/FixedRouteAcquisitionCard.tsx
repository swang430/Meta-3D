import { Checkbox, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import type { RouteFields } from '../TopologyEditor/routeCalibrationState'

/** 共用采集参数：自动操作入口已迁到原拓扑侧栏；此处不再另选旧RF-chain或启动采集。 */
export function FixedRouteAcquisitionFields({ values, onChange }: {
  values:RouteFields; onChange:(key:keyof RouteFields,value:string|boolean)=>void
}) {
  return <Stack gap="sm"><SimpleGrid cols={{base:1,md:2}}>
    <TextInput label="采集频率（MHz）" required type="number" min={0.001} step="any" value={values.frequency} onChange={e=>onChange('frequency',e.currentTarget.value)} />
    <TextInput label="允许的单音设置功率（dBm，非实测）" required type="number" min={-100} max={0} step="any" value={values.power} onChange={e=>onChange('power',e.currentTarget.value)} />
    <TextInput label="参考天线身份、极化及位置" required maxLength={500} value={values.antenna} onChange={e=>onChange('antenna',e.currentTarget.value)} />
    <TextInput label="重复采样次数" required type="number" min={2} max={10} value={values.samples} onChange={e=>onChange('samples',e.currentTarget.value)} />
    <TextInput label="接收线缆损耗（dB，可空）" type="number" step="any" value={values.cable} onChange={e=>onChange('cable',e.currentTarget.value)} />
    <TextInput label="接收线缆记录来源及适用频率" maxLength={500} value={values.cableSource} onChange={e=>onChange('cableSource',e.currentTarget.value)} />
  </SimpleGrid>
  <Text size="xs">接收线缆只指参考天线到分析仪的一段；不从现有拓扑线损代填。缺少资料时只采集功率，不计算整条损耗。</Text>
  <Checkbox label="我已核对所选链的实际接线，开关已固定到该通路" checked={values.fixed} onChange={e=>onChange('fixed',e.currentTarget.checked)} />
  <Checkbox label="我已确认专用校准仿真正在运行、本输出口无其它混入信号，以及设置功率对功放和接收端安全" checked={values.safe} onChange={e=>onChange('safe',e.currentTarget.checked)} />
  </Stack>
}
