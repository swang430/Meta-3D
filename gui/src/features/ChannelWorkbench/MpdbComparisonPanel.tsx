import { useState, type FormEvent } from 'react'
import { Alert, Anchor, Button, Group, Stack, Table, Text, Title } from '@mantine/core'
import { isAxiosError } from 'axios'
import client from '../../api/client'
import { comparisonParameters, metric, readComparison, type Comparison } from './comparison'

export function MpdbComparisonPanel() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<Comparison | null>(null)
  async function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = new FormData(event.currentTarget)
    setResult(null); setError('')
    try {
      const parameters = comparisonParameters(Number(body.get('bandwidth_mhz')), Number(body.get('points')), Number(body.get('amplitude_floor')))
      for (const [name, limit] of [['archive',256], ['asc',256], ['members',32]] as const) {
        const file = body.get(name)
        if (!(file instanceof File) || !file.size || file.size > limit * 1024 * 1024) throw Error(`${name === 'archive' ? '原始 MPDB ZIP' : name === 'asc' ? '八路传导 ASC ZIP' : '射线成员表'}不能为空且不得超过 ${limit} MiB。`)
      }
      for (const [key,value] of Object.entries(parameters)) body.set(key, String(value))
      setBusy(true)
      const { data } = await client.post('/channel-assets/mpdb-projects/comparisons', body, { timeout: 31 * 60 * 1000 })
      setResult(readComparison(data))
    } catch (cause) {
      const detail = isAxiosError(cause) ? cause.response?.data?.detail : null
      setError(typeof detail === 'string' ? detail : cause instanceof Error ? cause.message : '比较未完成，请检查服务连接。')
    } finally { setBusy(false) }
  }
  return <Stack>
    <Title order={3}>比较原始数据与传导工程</Title>
    <Text>选择同一来源的三类文件，比较 Lauraycs 与 Meta-3D。只读分析，不写回工程、不改变方案、不调用硬件。</Text>
    <form onSubmit={compare} onChange={() => { setResult(null); setError('') }}>
      <fieldset disabled={busy}><legend>比较文件与参数</legend><Stack>
        <label>原始 MPDB 外层 ZIP（最大 256 MiB） <input required type="file" name="archive" accept=".zip" /></label>
        <label>已有八路传导 ASC ZIP（最大 256 MiB） <input required type="file" name="asc" accept=".zip" /></label>
        <Text size="sm">ZIP 根目录须包含 TX0 至 TX3、RX0 至 RX1 的八份 R0B0S0D_TX*_RX*_H.asc，可附 manifest.json。</Text>
        <label>同源射线成员表（members.npz，最大 32 MiB） <input required type="file" name="members" accept=".npz" /></label>
        <Text size="sm">使用同一链路、源行顺序中非零复系数对应的成员标签，不重新聚簇。</Text>
        <label>比较带宽（MHz） <input required type="number" name="bandwidth_mhz" defaultValue="100" max="10000" step="any" /></label>
        <label>频点数（3 至 257 的奇数） <input required type="number" name="points" defaultValue="41" min="3" max="257" step="2" /></label>
        <label>共同相位掩码的幅度下限 <input required type="number" name="amplitude_floor" defaultValue="1e-8" step="any" /></label>
        <Button type="submit" loading={busy}>开始文件比较</Button>
      </Stack></fieldset>
    </form>
    {busy && <Text role="status">正在上传并计算，请稍候。</Text>}
    {error && <Alert color="red" role="alert">{error}</Alert>}
    {result && <Stack aria-live="polite">
      <Alert color="yellow" title={result.status === 'partial' ? '部分比较完成，证据未核验' : '证据未核验'}>
        无正式通过结论；源时间与时延零点对齐未核验；非模拟结果，硬件效果未核验。
      </Alert>
      <Text>{result.message}</Text>
      <Text>源帧共 {result.source_frame_count} 帧；已配对 {result.source_frame_count - result.unmatched_source_frames.length} 帧。</Text>
      <Alert color="yellow" title="未配对源帧（仍计入覆盖分母）">{result.unmatched_source_frames.length ? `帧 ${result.unmatched_source_frames.join('、')}，未参与误差比较，不能视为零误差。` : '服务器未报告未配对源帧。'}</Alert>
      <Text>共同相位有效点：{result.coverage.phase_valid} / {result.coverage.phase_total}；比例 {metric(result.coverage.phase_fraction)}。参考和两方案对应端口对均须高于同一幅度下限。</Text>
      <Text>矩阵有效点：{result.coverage.matrix_valid} / {result.coverage.matrix_total}；比例 {metric(result.coverage.matrix_fraction)}。分母保留全部源帧。</Text>
      <Table withTableBorder><Table.Thead><Table.Tr><Table.Th>方案</Table.Th><Table.Th>矩阵归一化均方误差中位数（线性比值）</Table.Th><Table.Th>矩阵误差第95百分位（线性比值）</Table.Th><Table.Th>相位误差第95百分位（度）</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{(['Lauraycs','Meta-3D'] as const).map(name => <Table.Tr key={name}><Table.Td>{name}</Table.Td><Table.Td>{metric(result.summary[name].matrix_nmse_median)}</Table.Td><Table.Td>{metric(result.summary[name].matrix_nmse_p95)}</Table.Td><Table.Td>{metric(result.summary[name].phase_error_p95_deg)}</Table.Td></Table.Tr>)}</Table.Tbody>
      </Table>
      <Text>H 是复系数列名，不能解释为水平极化。ASC 仅由 _H.asc 文件名绑定，独立极化来源未核验。复系数不是 dBm；未提供输入功率参考时，绝对接收功率未知。</Text>
      <details><summary>查看来源摘要、成员顺序及极化依据</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({source:result.source,member_row_order:result.member_row_order,polarization_basis:result.polarization_basis}, null, 2)}</pre></details>
      <Group><Anchor href={result.download_url} download>下载完整比较报告 ZIP</Anchor><Anchor href={result.points_url} download>下载逐点 CSV</Anchor></Group>
      <Text size="sm">下载有效期 24 小时，过期请重新比较。完整报告含逐帧、外推差异、载频误差、使用抽头及八端口功率；逐点 CSV 含频偏、端口对、有效掩码和误差。</Text>
    </Stack>}
  </Stack>
}
