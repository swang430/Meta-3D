import { useRef, useState } from 'react'
import { Button, Group, Paper, Select, Stack, Text, Title } from '@mantine/core'
import { readBundle, verifyAscFile, type Mode } from './imtBundle'

import { imtProjectDirectories } from './imtProjectDirectories'

export function ImtBundlePanel() {
  const [mode, setMode] = useState<Mode | null>(null)
  const [projects, setProjects] = useState<
    ReturnType<typeof imtProjectDirectories>
  >([])
  const [selected, setSelected] = useState('')
  const [data, setData] = useState<ReturnType<typeof readBundle> | null>(null)
  const [error, setError] = useState(''),
    [tx, setTx] = useState('0'),
    [freq, setFreq] = useState('0')
  const [comparison, setComparison] = useState('')
  const [busy, setBusy] = useState(false)
  const generation = useRef(0),
    input = useRef<HTMLInputElement>(null)
  async function load(files: File[], path: string) {
    setSelected(path)
    setMode(null)
    setTx('0')
    setFreq('0')
    const id = ++generation.current
    setData(null)
    setError('')
    setComparison('')
    setBusy(true)
    try {
      if (!globalThis.crypto?.subtle)
        throw Error('浏览器需要 HTTPS 或本机地址才能核对文件校验值')
      const list = files.filter((f) => f.name === 'manifest.json')
      if (list.length !== 1)
        throw Error('请选择一个工程目录，其中须有 manifest.json 和 ASC 文件')
      const manifest = JSON.parse(await list[0].text())
      const mode = manifest?.mode
      if (mode !== 'conducted' && mode !== 'ota')
        throw Error('清单未注明可识别的测试方式')
      if (
        path &&
        (mode !== 'ota' ||
          manifest.evidence !==
            (path === 'baseline'
              ? 'offline_ideal_plane_wave'
              : 'offline_distance_doppler'))
      )
        throw Error('清单记录的工程类型与子目录不符：' + path)
      const parsed = readBundle(manifest, mode)
      const byName = new Map(files.map((f) => [f.name, f]))
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
        setMode(mode)
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
          <Button
            onClick={() => {
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
              if (!files.length) return
              try {
                const next = imtProjectDirectories(files)
                setProjects(next)
                void load(next[0][1], next[0][0])
              } catch (error) {
                generation.current++
                setProjects([])
                setData(null)
                setBusy(false)
                setMode(null)
                setComparison('')
                setError(
                  error instanceof Error ? error.message : '读取目录失败',
                )
              }
            }}
          />
        </Group>
        <Text size="sm">
          选择含清单和 ASC
          文件的目录，系统会根据清单识别测试方式。也可选择解压后的 OTA 总目录。
        </Text>
        {projects.some(([path]) => path) && (
          <Select
            label="查看子工程"
            value={selected}
            allowDeselect={false}
            data={projects.map(([path]) => ({
              value: path,
              label:
                path === 'baseline'
                  ? '基准工程（baseline）'
                  : '动态工程（dynamic）',
            }))}
            onChange={(value) => {
              const project = projects.find(([path]) => path === value)
              if (project) void load(project[1], project[0])
            }}
          />
        )}
        {busy && <Text>正在核对工程清单和 ASC 文件…</Text>}
        {error && (
          <Text c="red" role="alert">
            {error}
          </Text>
        )}
        {data && (
          <>
            <Text>
              {mode === 'conducted' ? '电缆传导' : '暗室 OTA'} ·{' '}
              {data.links.length} 份 ASC 文件校验一致 · {data.frames} 行 · 每行{' '}
              {data.taps} 个抽头 · {data.carrier / 1e6} MHz · {data.rate} Hz
            </Text>
            {data.phaseSummary && <Text>{data.phaseSummary}</Text>}
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
              {data.metrics.length > 0 && (
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
            {data.metrics.length > 0 && (
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
