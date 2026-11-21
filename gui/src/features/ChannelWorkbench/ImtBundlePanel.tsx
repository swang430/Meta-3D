import { useRef, useState } from 'react'
import { Button, Group, Paper, Select, Stack, Text, Title } from '@mantine/core'
import { readBundle, verifyAscFile, type Mode } from './imtBundle'

export function ImtBundlePanel() {
  const [mode, setMode] = useState<Mode>('conducted')
  const [data, setData] = useState<ReturnType<typeof readBundle> | null>(null)
  const [error, setError] = useState(''),
    [tx, setTx] = useState('0'),
    [freq, setFreq] = useState('0')
  const [comparison, setComparison] = useState('')
  const [busy, setBusy] = useState(false)
  const generation = useRef(0),
    input = useRef<HTMLInputElement>(null)
  async function load(files: File[]) {
    const id = ++generation.current
    setData(null)
    setError('')
    setComparison('')
    setBusy(true)
    try {
      const list = files.filter((f) => f.name === 'manifest.json')
      if (list.length !== 1)
        throw Error('请选择一个工程目录，其中须有 manifest.json 和 ASC 文件')
      const parsed = readBundle(JSON.parse(await list[0].text()), mode)
      const directory = list[0].webkitRelativePath
        .split('/')
        .slice(0, -1)
        .join('/')
      const siblings = files.filter(
        (f) =>
          f.webkitRelativePath.split('/').slice(0, -1).join('/') === directory,
      )
      const byName = new Map(siblings.map((f) => [f.name, f]))
      for (const link of parsed.links) {
        if (id !== generation.current) return
        const f = byName.get(link.file)
        if (!f) throw Error('缺少 ' + link.file)
        await verifyAscFile(f, parsed, link)
      }
      const report = byName.get('宽带对照.txt')
      const notes =
        mode === 'conducted' && report && report.size <= 200000
          ? await report.text()
          : ''
      if (id === generation.current) {
        setComparison(notes)
        setData(parsed)
      }
    } catch (e) {
      if (id === generation.current)
        setError(e instanceof Error ? e.message : '读取工程失败')
    } finally {
      if (id === generation.current) setBusy(false)
    }
  }
  const metrics =
    data?.metrics.filter(
      (r) => r.tx === Number(tx) && r.offset_hz === Number(freq),
    ) ?? []
  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Title order={4}>查看下行信道工程</Title>
        <Group align="end">
          <Select
            label="测试方式"
            value={mode}
            allowDeselect={false}
            data={[
              { value: 'conducted', label: '电缆传导' },
              { value: 'ota', label: '暗室 OTA' },
            ]}
            onChange={(v) => {
              generation.current++
              setMode(v as Mode)
              setData(null)
              setError('')
              setBusy(false)
            }}
          />
          <Button
            onClick={() => {
              if (!globalThis.crypto?.subtle) {
                setError('浏览器需要 HTTPS 或本机地址才能核对文件校验值')
                return
              }
              input.current?.click()
            }}
          >
            选择工程目录
          </Button>
          <input
            hidden
            type="file"
            multiple
            ref={(el) => {
              input.current = el
              el?.setAttribute('webkitdirectory', '')
            }}
            onChange={(e) => {
              const files = Array.from(e.target.files ?? [])
              e.target.value = ''
              if (files.length) void load(files)
            }}
          />
        </Group>
        {busy && <Text>正在核对工程清单和 ASC 文件…</Text>}
        {error && (
          <Text c="red" role="alert">
            {error}
          </Text>
        )}
        {data && (
          <>
            <Text>
              {data.links.length} 份 ASC 文件校验一致 · {data.frames} 行 · 每行{' '}
              {data.taps} 个抽头 · {data.carrier / 1e6} MHz · {data.rate} Hz
            </Text>
            {mode === 'ota' && (
              <Text size="sm">
                发射极化 {data.txMode} · 参考接收端口 {data.referenceRx} ·
                更新率依据：{data.rateSource}
              </Text>
            )}
            <Text size="sm">厂商工程构建、仪器加载、现场验收均待核实。</Text>
            <Group>
              <Select
                label="发射端口"
                data={['0', '1', '2', '3']}
                value={tx}
                allowDeselect={false}
                onChange={(v) => setTx(v ?? '0')}
              />
              {mode === 'ota' && (
                <Select
                  label="相对中心频率"
                  data={[-50, 0, 50].map((n) => ({
                    label: n + ' MHz',
                    value: String(n * 1e6),
                  }))}
                  value={freq}
                  allowDeselect={false}
                  onChange={(v) => setFreq(v ?? '0')}
                />
              )}
            </Group>
            <details>
              <summary>查看端口对应的文件</summary>
              {data.links
                .filter((l) => l.tx === Number(tx))
                .map((l) => (
                  <Text key={l.file} size="sm">
                    TX{l.tx} → {l.destination} · {l.file}
                  </Text>
                ))}
            </details>
            {mode === 'conducted' &&
              (comparison ? (
                <details>
                  <summary>查看目录附带的宽带对照记录</summary>
                  <Text size="xs">
                    以下为同目录文本，清单未提供它的校验值。
                  </Text>
                  <pre style={{ whiteSpace: 'pre-wrap' }}>{comparison}</pre>
                </details>
              ) : (
                <Text size="sm">目录中没有宽带对照记录。</Text>
              ))}
            {mode === 'ota' && (
              <>
                <Text size="sm">
                  按源帧核对理想探头场。场误差取误差能量与目标场能量之比，功率比
                  1 表示两者功率相等。
                </Text>
                <details>
                  <summary>查看逐帧误差（误差最大者在前）</summary>
                  {[...metrics]
                    .sort((a, b) => (b.field_nmse ?? -1) - (a.field_nmse ?? -1))
                    .map((r) => (
                      <Text size="sm" key={r.frame}>
                        源帧 {r.frame} · 场误差{' '}
                        {r.field_nmse === null
                          ? '未知'
                          : r.field_nmse === 0
                            ? '0（零误差）'
                            : (10 * Math.log10(r.field_nmse)).toFixed(2) +
                              ' dB'}{' '}
                        · 功率比 {r.power_ratio?.toFixed(3) ?? '未知'}
                      </Text>
                    ))}
                </details>
              </>
            )}
          </>
        )}
      </Stack>
    </Paper>
  )
}
