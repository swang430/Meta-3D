import { useEffect, useState, type FormEvent } from 'react'
import { Alert, Anchor, Button, Stack, Text, Title } from '@mantine/core'
import { isAxiosError } from 'axios'
import client from '../../api/client'

type WarningLocation = {frame: number, tx: number, rx: number, cluster: number}

const statusLabels = {
  warning: '发现异常',
  partial: '部分已核验',
  unverified: '未核验',
}

export function PortEvidencePanel() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ message: string, lines: string[], status: string, warnings: WarningLocation[], url: string }>()
  useEffect(() => () => { if (result) URL.revokeObjectURL(result.url) }, [result])

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = new FormData(event.currentTarget)
    for (const name of ['members', 'expected', 'amplitude_floor']) {
      const value = body.get(name)
      if (value === '' || (value instanceof File && !value.name)) body.delete(name)
    }
    setResult(undefined)
    setError('')
    setBusy(true)
    try {
      const { data } = await client.post<Blob>('/channel-assets/mpdb-projects/port-evidence', body,
        { responseType: 'blob', timeout: 31 * 60 * 1000 })
      const report = JSON.parse(await data.text())
      if (typeof report?.message !== 'string' || !Object.hasOwn(statusLabels, report.status) ||
          !Array.isArray(report.summary) || !report.summary.every((line: unknown) => typeof line === 'string') ||
          !Array.isArray(report.warnings) || !report.warnings.every((row: WarningLocation) => row &&
            [row.frame, row.tx, row.rx, row.cluster].every(Number.isInteger)) || !Array.isArray(report.frames))
        throw Error('结果文件缺少分析说明或逐帧记录。')
      setResult({ message: report.message, lines: report.summary, warnings: report.warnings, status: statusLabels[report.status as keyof typeof statusLabels], url: URL.createObjectURL(data) })
    } catch (cause) {
      let message = '分析未完成，请检查文件或服务连接。'
      if (isAxiosError(cause) && cause.response?.data instanceof Blob) {
        try {
          const detail = JSON.parse(await cause.response.data.text()).detail
          if (typeof detail === 'string') message = detail
        } catch { /* 服务可能没有返回详细说明。 */ }
      } else if (cause instanceof Error) message = cause.message
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  return <form onSubmit={analyze} onChange={() => { setResult(undefined); setError('') }}>
    <fieldset disabled={busy}>
      <legend>端口成员与时延分析</legend>
      <Stack>
        <Text>先核对各端口的射线分组，再比较同一批成员采用端口独立时延和共享时延的差异。</Text>
        <label>原始传播数据（ZIP） <input required type="file" name="archive" accept=".zip" /></label>
        <label>射线成员表（NPZ，可选） <input type="file" name="members" accept=".npz" /></label>
        <label>既有聚簇结果（results.json，可选） <input type="file" name="expected" accept=".json" /></label>
        <label>分析带宽（MHz） <input type="number" name="bandwidth_mhz" required max="10000" step="any"
          onInput={event => event.currentTarget.setCustomValidity(
            event.currentTarget.valueAsNumber > 0 ? '' : '带宽须为正数。')} /></label>
        <label>频点数（含中心及带边） <input type="number" required name="points" min="3" max="257" step="2" defaultValue="101" /></label>
        <label>相位比较的幅度下限（可选） <input type="number" name="amplitude_floor" step="any" onInput={event => event.currentTarget.setCustomValidity(
          !event.currentTarget.value || event.currentTarget.valueAsNumber > 0 ? '' : '幅度下限须为正数。')} /></label>
        <Button loading={busy} type="submit">开始只读分析</Button>
      </Stack>
    </fieldset>
    {error && <Alert color="red">{error}</Alert>}
    {result && <Stack aria-live="polite">
      <Title order={4}>{result.status}</Title><Text>{result.message}</Text>
      {result.lines.map((line, index) => <Text key={index}>{line}</Text>)}
      {result.warnings.map((row, index) => <Text key={index}>
        异常位置：帧 {row.frame}，发射端口 {row.tx}，接收端口 {row.rx}，簇 {row.cluster}
      </Text>)}
      <Anchor href={result.url} download="port-evidence.json">下载完整分析结果</Anchor>
    </Stack>}
  </form>
}
