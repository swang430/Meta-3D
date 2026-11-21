import { useEffect, useState } from 'react'
import { Alert, FileInput, Paper, Stack, Text, Title } from '@mantine/core'
import { verifyClusters } from './clusterVerification'
const location = (id: {
  frame: number
  tx: number
  rx: number
  cluster: number
}) => `帧 ${id.frame} · TX${id.tx} → RX${id.rx} · 簇 ${id.cluster}`

export function ClusterVerificationPanel() {
  const [result, setResult] = useState<File | null>(null)
  const [evidence, setEvidence] = useState<File | null>(null)
  const [report, setReport] = useState<ReturnType<
    typeof verifyClusters
  > | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => {
    let current = true
    setReport(null)
    setError('')
    setNotice('')
    if (result?.name.toLowerCase().endsWith('.asc')) {
      setNotice(
        '聚簇结果未核验。ASC 文件记录信道抽头，缺少每个簇包含哪些射线以及如何分簇的信息，无法据此核对聚簇结果。',
      )
      return
    }
    if (result)
      void Promise.all([result.text(), evidence?.text()])
        .then(([r, e]) => {
          const value = verifyClusters(
            JSON.parse(r),
            e === undefined ? null : JSON.parse(e),
          )
          if (current) setReport(value)
        })
        .catch((err) => {
          if (current)
            setError(err instanceof Error ? err.message : '无法读取文件')
        })
    return () => {
      current = false
    }
  }, [result, evidence])
  return (
    <Paper withBorder p="md">
      <Stack>
        <Title order={4}>聚簇结果核验</Title>
        <Text size="sm">
          先选择 results.json，读取每个簇的汇总结果。再选择同一次计算的
          evidence.json，用簇内各条射线的记录核对合成后的复系数和代表多普勒频移。缺少成员记录时，对应结果显示为未核验。
        </Text>
        <FileInput
          clearable
          label="聚簇结果（results.json）或单个 ASC 文件"
          accept=".json,.asc"
          value={result}
          onChange={(file) => {
            setResult(file)
            setEvidence(null)
            setReport(null)
            setError('')
            setNotice('')
          }}
        />
        <FileInput
          clearable
          label="簇内射线成员记录（evidence.json，可选）"
          accept=".json"
          disabled={!result || result.name.toLowerCase().endsWith('.asc')}
          value={evidence}
          onChange={(file) => {
            setEvidence(file)
            setReport(null)
            setError('')
          }}
        />
        {notice && <Text>{notice}</Text>}
        {error && <Alert color="red">{error}</Alert>}
        {report && <ClusterReport report={report} />}
      </Stack>
    </Paper>
  )
}

export function ClusterReport({
  report,
}: {
  report: ReturnType<typeof verifyClusters>
}) {
  return (
    <>
      <Text>
        两项均已核对 {report.checked} 簇，未完整核验 {report.unknown} 簇，发现{' '}
        {report.warnings.length} 条异常。
      </Text>
      {report.warnings.length > 0 && (
        <Alert color="orange" title="聚簇结果有异常">
          {report.warnings.map(({ id, message }) => (
            <Text key={location(id) + message}>
              {location(id)}：{message}
            </Text>
          ))}
        </Alert>
      )}
      {report.unknown > 0 && (
        <details>
          <summary>未核验，可继续 · {report.unverified[0].reason}</summary>
          {report.unverified.map(({ id, reason }) => (
            <Text key={location(id)}>
              {location(id)}：{reason}
            </Text>
          ))}
        </details>
      )}
    </>
  )
}
