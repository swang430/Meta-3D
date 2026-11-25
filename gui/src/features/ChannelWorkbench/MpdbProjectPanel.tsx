import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import {
  Alert,
  Button,
  FileInput,
  Group,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core'
import client from '../../api/client'
import { ClusterReport } from './ClusterVerificationPanel'
import { durations, projectParameters, readProject, type ProjectMode, type TimingMode } from './mpdbProject'
import type { components } from '../../types/api.generated'

type Project = ReturnType<typeof readProject> & { description: string }
const root = '/channel-assets/mpdb-projects'

export function MpdbProjectPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [source, setSource] = useState<components['schemas']['ImportedSource'] | null>(null)
  const [method, setMethod] = useState<string | null>(null)
  const [supplied, setSupplied] = useState<File | null>(null)
  const [mode, setMode] = useState<ProjectMode>('conducted')
  const [speed, setSpeed] = useState('')
  const [rate, setRate] = useState('standard')
  const [plan, setPlan] = useState<File | null>(null)
  const [choice, setChoice] = useState<TimingMode>('')
  const [segmentText, setSegmentText] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [projects, setProjects] = useState<
    Partial<Record<ProjectMode, Project>>
  >({})
  const timing = source?.timing
  const fileRevision = useRef(0)
  const [revision, refreshChamber] = useState(0)
  const [installation, setInstallation] = useState<Record<string,unknown> | null>(null)
  const [chamber, setChamber] = useState<{ source: string; name?: string; design?: boolean; count?: number; digest?: string; routes?: string[]; error?: string } | null>(null)
  useEffect(() => {
    if (mode !== 'ota' || !source) return
    let current = true
    setChamber(null)
    const url = root+'/'+source.source_id+'/ota-chamber'
    const request = installation ? client.post(url, installation) : client.get(url)
    request.then(({data}) => {
      if (current) setChamber({source:source.source_id,name:data.chamber_name,design:data.geometry_source === 'chamber_wiring_design',count:data.probe_connections.length, digest:data.configuration_sha256,
        routes:Object.entries(data.tx_inputs).map(([tx,input])=>"发射端口 "+tx+" → F64 输入 "+input).concat(data.probe_connections.flatMap((p:{index:number;feeds:Record<string,{probe_number:number;ce_port:string;value_db:number|null}>}) => Object.entries(p.feeds).map(([pol,f])=>
          "工程探头 "+p.index+" "+pol+" → 实物探头 "+f.probe_number+"，输出 "+f.ce_port+(f.value_db == null ? "，路径损耗未实测" : "，路径损耗 "+f.value_db+" dB"))))})
    }).catch(e => {
      if (current) setChamber({source:source.source_id,error:e.response?.data?.detail || '无法读取当前暗室配置'})
    })
    return () => { current = false }
  }, [mode, source, installation, revision])
  const selected = timing?.source_times_s ? 'original' : choice
  const distances = timing?.distances_m ?? []
  const choose = source?.clustering === 'missing'
  const parameters = projectParameters(mode, speed, rate, selected, segmentText, distances.length)
  const sections = durations(segmentText)
  const duration = (i: number, d: number | null): number | null => {
    if (timing?.source_times_s) return timing.source_times_s[i+1]-timing.source_times_s[i]
    if (selected === 'segments' && sections.length === distances.length && Number.isFinite(sections[i]) && sections[i]>0) return sections[i]
    if (selected === 'constant' && d !== null && d>0 && Number.isFinite(Number(speed)) && Number(speed)>0) return d/Number(speed)
    return null
  }
  const valid = parameters && (mode === 'conducted' || (distances.length > 0 && distances.every((d,i)=>duration(i,d)! > 0)))
  const project = projects[mode]

  async function inspectFile(next: File | null, groups: File | null = supplied, nextPlan: File | null = plan) {
    setFile(next); setSource(null); setProjects({}); setMethod(null); setError('')
    setSupplied(groups); setPlan(nextPlan)
    setSpeed(''); setRate('standard'); setChoice(''); setSegmentText('')
    if (!next) return
    setBusy('检查原始文件')
    try {
      const form = new FormData()
      form.append('file', next)
      if (nextPlan) form.append('plan_manifest', nextPlan)
      if (groups) form.append('members', groups)
      const {data} = await client.post(root+'/import', form)
      if (!data?.source_id || !Array.isArray(data.timing?.tx_ports) || !Array.isArray(data.timing?.rx_ports) || !Array.isArray(data.timing?.frame_ids) || !['matched','missing','supplied'].includes(data.clustering)) throw Error('服务器未返回完整的来源检查结果。')
      setSource(data)
    } catch(cause) {
      const detail = axios.isAxiosError(cause) && cause.response?.data?.detail
      setError((groups?'检查上传的射线分组失败：':'检查文件失败：')+(typeof detail === 'string' ? detail : cause instanceof Error ? cause.message : '请求失败'))
    } finally { setBusy('') }
  }

  async function build() {
    if (!file || !source || !valid || busy) return
    const stage = '生成工程'
    setError('')
    setBusy(stage)
    try {
      const { data } = await client.post(
        root + '/' + encodeURIComponent(source.source_id) + '/build',
        mode === 'conducted' && choose && method ? { ...parameters, clustering_method: method } : mode === "ota" ? {...parameters, installation, chamber_sha256:chamber?.digest} : parameters,
        { timeout: 0 },
      )
      const result = readProject(data, mode, window.location.origin)
      setProjects((previous) => ({
        ...previous,
        [mode]: {
          ...result,
          description:
            mode === 'conducted'
              ? file.name + ' · 源帧版'
              : file.name + ' · '+(selected==='original'?'原始帧时间':selected==='segments'?'操作员给出的逐段时长':'操作员假定恒速 '+speed+' m/s')+' · 系统计算更新率（'+(rate==='dense'?'加密':'标准')+'）',
        },
      }))
    } catch (cause) {
      if (
        stage === '生成工程' &&
        axios.isAxiosError(cause) &&
        cause.response?.status === 404
      )
        setSource(null)
      const detail = axios.isAxiosError(cause) && cause.response?.data?.detail
      setError(
        stage +
          '失败：' +
          (typeof detail === 'string'
            ? detail
            : cause instanceof Error
              ? cause.message
              : '请求失败'),
      )
    } finally {
      setBusy('')
    }
  }

  return (
    <Paper withBorder p="md">
      <Stack>
        <Title order={3}>从 MPDB 创建信道工程</Title>
        <FileInput
          label="MPDB 原始 ZIP 包"
          description="选择根目录含下行 R0B0S0D.mpdb 的 ZIP 文件。"
          accept=".zip"
          value={file}
          clearable
          disabled={!!busy}
          onChange={(next)=>inspectFile(next,null,plan)}
        />
        <FileInput label="Lauraycs 链路计算清单（可选）" description="选择配套的 compute-link-plan.manifest.json。核对链路和帧号后，直接使用原始时间。" accept=".json" clearable disabled={!!busy} value={plan} onChange={(next)=>inspectFile(file,supplied,next)}/>
        <SegmentedControl
          disabled={!!busy}
          value={mode}
          onChange={(value) => {
            setMode(value as ProjectMode)
            setError('')
          }}
          data={[
            { value: 'conducted', label: '传导' },
            { value: 'ota', label: '空口（OTA）' },
          ]}
        />
        {timing && <Text>发射端口 {timing.tx_ports.join('、')}；接收端口 {timing.rx_ports.join('、')}</Text>}
        {mode === 'conducted' ? (
          <>
          {source && !choose && <Text>{source.clustering === 'supplied' ? '已核对您提供的分组文件来源；每条通路的射线数量和组号将在生成时核对。' : '已找到这份原始数据此前离线聚簇保存的射线分组。'}这不是 MPDB 中的原始字段。系统核对原文件内容后，复用每条射线属于哪一组的记录来汇总各条通路，不需要另行制作文件。</Text>}
          {(choose || supplied) && <details><summary>使用已有的射线分组文件（可选）</summary>
            <FileInput label="此前保存的分组文件" description="仅在已有同一份原数据的离线分组结果时使用。选择后会重新核对来源；没有文件时直接选择分组方式即可。"
              accept=".npz" clearable disabled={!!busy} value={supplied} onChange={(next)=>inspectFile(file,next)}/></details>}
          {choose && <Select label="这份数据没有已收录的射线分组，请选择分组方式" placeholder="请选择分组方式"
            data={[{ value: 'delay_bins', label: '按每帧共享的时延区间分组（最多 24 组，不按角度分组）' }]}
            value={method} disabled={!!busy} onChange={(v)=>{setMethod(v);setProjects({})}} />}
          <Text size="sm">
            各收发端口对共用每帧的簇划分。每条通路的 ASC
            各自保留复系数，每行对应一个原始帧。文件头的 1 Hz
            仅用于按序查看。生成后自动核对各簇。
          </Text>
          </>
        ) : (
          <>
            <FileInput label="暗室安装登记或开发接线设计" description="现场工程可使用实验室保存的安装登记。开发工程请选择与本实验室接线设计一致的 JSON 文件。"
              accept=".json" disabled={!!busy} clearable onChange={async f => {
                const id = ++fileRevision.current
                setError(''); setChamber(null); setProjects({}); setInstallation(f ? {} : null)
                if (f) {
                  try { const value = JSON.parse(await f.text()); if (!value || typeof value !== "object" || Array.isArray(value)) throw Error(); if (id === fileRevision.current) setInstallation(value) }
                  catch { if (id === fileRevision.current) setError('安装登记必须是包含接线信息的 JSON 对象') }
                }
              }}/>
            <Text size="sm">{!timing ? '请先选择文件，检查是否记录了帧时间。' : timing.plan_sha256 ? '已核对清单中的下行收发节点、路径和全部源帧，使用清单记录的原始时间，无需填写车速。这些信息不能验证原始文件未记录的运行编号。' : timing.time_source ? '原始文件时间来源：'+timing.time_source : '原始文件未记录可确认的帧时间，帧编号不代表秒。请明确选择播放假设。'}</Text>
            {timing && !timing.source_times_s && <Select label="播放时间的依据" value={choice || null} disabled={!!busy}
              placeholder="请选择" onChange={(v)=>{setChoice((v || '') as TimingMode);setProjects({})}}
              data={[{value:'constant',label:'假定恒速，由各段位移推算时长'},{value:'segments',label:'逐段输入时长，支持变速或停车'}]}/>}
            <Button variant="subtle" disabled={!!busy || !source} onClick={()=>refreshChamber(v=>v+1)}>重新核对暗室配置</Button>
            {chamber?.routes && <details><summary>{chamber.design ? "查看逐路设计接线" : "查看逐路接线与采用的校准"}</summary>{chamber.routes.map(row=><Text key={row}>{row}</Text>)}</details>}
            <Group grow>
              {selected==='constant' && <TextInput
                label="操作员假定的恒定速度（m/s）"
                value={speed}
                disabled={!!busy}
                onChange={(e) => {setSpeed(e.currentTarget.value);setProjects({})}}
              />}
              {selected==='segments' && <Textarea label="各段时长（秒）" description={'依帧序输入 '+distances.length+' 个正数，用空格、逗号或换行分隔。停车也要填写经过的时间。'}
                value={segmentText} disabled={!!busy} onChange={(e)=>{setSegmentText(e.currentTarget.value);setProjects({})}}/>}
            </Group>
            {timing && <details open><summary>各段经过时间和区段平均速度（不是瞬时速度）</summary>
              <div style={{maxHeight:240,overflow:'auto'}}><table><thead><tr><th>源帧区段</th><th>位移（m）</th><th>时长（s）</th><th>区段平均速度（m/s）</th></tr></thead><tbody>
              {distances.map((d,i)=>{const dt=duration(i,d);return <tr key={i}><td>{timing.frame_ids[i]} → {timing.frame_ids[i+1]}</td><td>{d?.toFixed(3) ?? '未知'}</td>
                <td>{dt?.toFixed(3) ?? '未知'}</td><td>{d!==null && dt ? (d/dt).toFixed(3) : '未知'}</td></tr>})}
              </tbody></table></div></details>}
              <Select label="输出时间采样" description="系统按原始射线的最大频移和最短帧间隔计算标准更新率。加密档将标准率翻倍，不会恢复缺失的实测信息。"
                value={rate} disabled={!!busy} allowDeselect={false} onChange={(v)=>{setRate(v || 'standard');setProjects({})}}
                data={[{value:'standard',label:'标准'},{value:'dense',label:'加密（两倍更新率）'}]}/>
            <Alert color="yellow">
              {chamber?.source === source?.source_id && chamber ? chamber.error ||
                (chamber.design ? '开发工程：'+chamber.name+'，按登记的设计接线生成。现场连接及路径损耗未核验。' : '当前暗室：'+chamber.name+'，已核对 '+chamber.count+' 个双极化位置的接线和路径校准。')
                : '选择文件后读取当前暗室、探头接线和本次载频的校准记录。'}
              生成时再次核对。ASC 保留空间权重，播放前须核对路径补偿。实际播放效果待现场验证。
            </Alert>
          </>
        )}
        <Group>
          <Button
            loading={!!busy}
            disabled={!source || !valid || (mode === "ota" && (!chamber?.name || chamber.source !== source.source_id)) || (mode === 'conducted' && choose && !method)}
            onClick={build}
          >
            生成信道工程
          </Button>
          {file && !source && !busy && <Button variant="light" onClick={()=>inspectFile(file)}>重新检查文件</Button>}
          {busy && <Text role="status">正在{busy}，请稍候。</Text>}
        </Group>
        {error && (
          <Alert color="red" role="alert">
            {error}
          </Alert>
        )}
        {project && (
          <Stack gap="xs">
            <Text fw={600}>
              上次生成的{mode === 'ota' ? '空口' : '传导'}工程
            </Text>
            <Text>
              {project.description} · {mode === 'ota' ? '动态工程' : '传导工程'}
              共 {project.count} 个 ASC 文件
            </Text>
            <Group>
              <Button component="a" href={project.url} download variant="light">
                下载工程
              </Button>
            </Group>
            {project.summaries.map((summary) => <Text key={summary}>{summary}</Text>)}
            <Text>以上为离线生成结果，仪器播放效果待现场核验。</Text>
            {project.notice && <Alert color="yellow">{project.notice}</Alert>}
            {project.report && <ClusterReport report={project.report} />}
          </Stack>
        )}
      </Stack>
    </Paper>
  )
}
