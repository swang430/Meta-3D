import { useState } from 'react'
import axios from 'axios'
import {
  Alert,
  Button,
  FileInput,
  Group,
  Paper,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import client from '../../api/client'
import { ClusterReport } from './ClusterVerificationPanel'
import { projectParameters, readProject, type ProjectMode } from './mpdbProject'

type Project = ReturnType<typeof readProject> & { description: string }
const root = '/channel-assets/mpdb-projects'

export function MpdbProjectPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [source, setSource] = useState('')
  const [mode, setMode] = useState<ProjectMode>('conducted')
  const [speed, setSpeed] = useState('5')
  const [rate, setRate] = useState('171.18765176762867')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [projects, setProjects] = useState<
    Partial<Record<ProjectMode, Project>>
  >({})
  const parameters = projectParameters(mode, speed, rate)
  const project = projects[mode]

  async function build() {
    if (!file || !parameters || busy) return
    let stage = '上传文件'
    setError('')
    setBusy(stage)
    try {
      let id = source
      if (!id) {
        const form = new FormData()
        form.append('file', file)
        const { data } = await client.post(root + '/import', form)
        if (typeof data?.source_id !== 'string' || !data.source_id.trim())
          throw Error('服务器未返回来源编号。')
        id = data.source_id
        setSource(id)
      }
      stage = '生成工程'
      setBusy(stage)
      const { data } = await client.post(
        root + '/' + encodeURIComponent(id) + '/build',
        parameters,
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
              : file.name + ' · ' + speed + ' m/s · ' + rate + ' Hz',
        },
      }))
    } catch (cause) {
      if (
        stage === '生成工程' &&
        axios.isAxiosError(cause) &&
        cause.response?.status === 404
      )
        setSource('')
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
          onChange={(next) => {
            setFile(next)
            setProjects({})
            setSource('')
            setError('')
          }}
        />
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
        {mode === 'conducted' ? (
          <Text size="sm">
            四个发射端口和两个接收端口共用每帧的簇划分。八路 ASC
            各自保留复系数，每行对应一个原始帧。文件头的 1 Hz
            仅用于按序查看。生成后自动核对各簇。
          </Text>
        ) : (
          <>
            <Text size="sm">以下数值仅用于播放，可按需要修改。</Text>
            <Group grow>
              <TextInput
                label="播放速度（m/s）"
                value={speed}
                disabled={!!busy}
                onChange={(e) => setSpeed(e.currentTarget.value)}
              />
              <TextInput
                label="播放更新频率（Hz）"
                value={rate}
                disabled={!!busy}
                onChange={(e) => setRate(e.currentTarget.value)}
              />
            </Group>
            {!parameters && (
              <Text c="red">速度和更新频率均须为大于零的有限数值。</Text>
            )}
            <Alert color="yellow">
              将生成含 128 个 ASC
              文件的动态工程，以及供比较的基线工程。计算假设使用 16
              个水平布置的理想双极化探头，将轨迹距离按米解释，并按恒定速度推算播放时间。探头布局和播放效果待现场验证。
            </Alert>
          </>
        )}
        <Group>
          <Button
            loading={!!busy}
            disabled={!file || !parameters}
            onClick={build}
          >
            生成信道工程
          </Button>
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
