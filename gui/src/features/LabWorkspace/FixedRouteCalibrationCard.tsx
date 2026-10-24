import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Alert, Button, Card, Code, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core'
import { previewFixedRouteCalibration } from '../../api/labProfileService'
import type { FixedRouteCalibrationDeclaration } from '../../types/api'

const textFields = [
  ['chain_id', '链编号'], ['ce_port', 'F64输出口'],
  ['switch_identity', '射频开关身份'], ['fixed_route', '开关固定通路'],
  ['reference_antenna', '参考天线及位置'], ['ce_power_source', '输出口功率来源'],
  ['sa_power_source', '分析仪读数来源'], ['receive_cable_source', '接收线缆记录来源'],
] as const
const numberFields = [
  ['frequency_mhz', '工作频率（MHz）'], ['ce_output_power_dbm', 'F64输出口功率（dBm）'],
  ['sa_input_power_dbm', '分析仪输入口功率（dBm）'], ['receive_cable_loss_db', '接收线缆损耗（dB）'],
] as const

/** 人工参考值预览，不操作硬件。父层按实验室key挂载，不跨实验室保留输入。 */
export function FixedRouteCalibrationCard({ labId }: { labId: string }) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [inputError, setInputError] = useState('')
  const preview = useMutation({ mutationFn: previewFixedRouteCalibration })
  const update = (key: string, value: string) => {
    setValues(old => ({ ...old, [key]: value }))
    setInputError('')
    preview.reset()
  }
  const result = !preview.isPending && !preview.isError ? preview.data : undefined
  return <Card withBorder data-testid="fixed-route-calibration">
    <Stack gap="sm">
      <Title order={4}>人工参考值计算（PC-02A，不连接仪器）</Title>
      <Alert color="yellow">开关固定在一条通路，不自动切换。这里只按人工输入计算，不连接仪器、不保存校准证书、不应用补偿、不改变就绪状态。</Alert>
      <Text size="sm">测量从F64物理输出口到参考天线端口的整条路径，包含开关、功放、线缆和探头。不要再加减这些器件的标称增益。</Text>
      <form onSubmit={event => {
        event.preventDefault()
        const numbers = Object.fromEntries(numberFields.map(([key]) => [key, Number(values[key])]))
        if (numberFields.some(([key]) => !values[key]?.trim() || !Number.isFinite(numbers[key])) || numbers.frequency_mhz <= 0) {
          setInputError('请填写有效的功率、接收线缆损耗和正数工作频率；没有读数时不要填0。')
          return
        }
        const body = { ...values, ...numbers, lab_profile_id: labId, switch_mode: 'fixed' } as FixedRouteCalibrationDeclaration
        preview.mutate(body)
      }}>
        <fieldset disabled={preview.isPending} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
          <Stack gap="sm">
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              {textFields.map(([key, label]) => <TextInput key={key} label={label} required maxLength={500}
                value={values[key] ?? ''} onChange={event => update(key, event.currentTarget.value)} />)}
              {numberFields.map(([key, label]) => <TextInput key={key} label={label} required type="number" step="any"
                value={values[key] ?? ''} onChange={event => update(key, event.currentTarget.value)} />)}
            </SimpleGrid>
            <Text size="xs">输出口功率不能用F64设定值代替；分析仪须使用输入口绝对功率，不是功率密度。接收线缆仅指参考天线到分析仪这一段，损耗为正、增益为负，来源应对应同一频率。</Text>
            <Button type="submit" loading={preview.isPending} style={{ alignSelf: 'start' }}>计算预览</Button>
          </Stack>
        </fieldset>
      </form>
      {inputError && <Alert color="red">{inputError}</Alert>}
      {preview.isPaused && <Alert color="yellow">计算请求等待网络恢复，尚无新结果。</Alert>}
      {preview.isError && <Alert color="red">计算未完成：{preview.error.message}</Alert>}
      {result && <Alert color="blue">
        <Text fw={600}>{result.net_loss_db < 0 ? '整条路径增益' : '整条路径损耗'}：{Math.abs(result.net_loss_db)} dB</Text>
        <Text size="sm">{result.warning}</Text>
        <details><summary>查看本次计算输入及来源</summary><Code block style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{JSON.stringify(result.declaration, null, 2)}</Code></details>
      </Alert>}
    </Stack>
  </Card>
}
