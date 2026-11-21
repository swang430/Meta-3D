import assert from 'node:assert/strict'
import test from 'node:test'
import {
  projectParameters,
  readProject,
} from '../src/features/ChannelWorkbench/mpdbProject.ts'

const origin = 'https://example.test'
const project = { asc_count: 8, download_url: '/project.zip' }

test('逐段时长按源帧数校验，原始时间不提交假定速度', () => {
  assert.deepEqual(projectParameters('ota', '', '100', 'segments', '0.8, 1.2', 2),
    {mode:'ota', rate_hz:100, segment_durations_s:[0.8,1.2]})
  assert.equal(projectParameters('ota','','100','segments','1,',2),null)
  assert.deepEqual(projectParameters('ota','','100','original','',2),{mode:'ota',rate_hz:100})
})

test('保留播放参数精度，拒绝空值、非正数和无穷值', () => {
  assert.deepEqual(projectParameters('ota', '5', '171.18765176762867'), {
    mode: 'ota',
    speed_m_s: 5,
    rate_hz: 171.18765176762867,
  })
  assert.deepEqual(projectParameters('conducted', '', '-1'), {
    mode: 'conducted',
  })
  for (const value of ['', '0', '-2', 'Infinity', '未知'])
    assert.equal(projectParameters('ota', '5', value), null)
})

test('传导结果自动核验并保留未核验簇的位置', () => {
  const id = { frame: 2, tx: 1, rx: 3, cluster: 4 }
  const result = readProject(
    { ...project, results: { schema: 'joint-results/1', rows: [id] } },
    'conducted',
    origin,
  )
  assert.deepEqual(result.report?.unverified[0].id, id)
  assert.equal(result.url, origin + '/project.zip')
})

test('缺失或损坏的传导结果可下载并提示无法核验', () => {
  for (const results of [null, {}]) {
    const result = readProject({ ...project, results }, 'conducted', origin)
    assert.match(result.notice, /无法核验/)
    assert.equal(result.count, 8)
  }
})

test('空口结果独立于聚簇核验，损坏的下载地址和文件数不能表示成功', () => {
  assert.equal(readProject(project, 'ota', origin).report, undefined)
  for (const change of [
    { download_url: '' },
    { download_url: 'javascript:void(0)' },
    { asc_count: -1 },
  ])
    assert.throws(() => readProject({ ...project, ...change }, 'ota', origin))
})

test('动态清单直接给出本次模型相位结果，源帧缺证据单独提示', async () => {
  const { readFile } = await import('node:fs/promises')
  const path = new URL('../../docs/evidence/imt-dynamic/dynamic-manifest.json', import.meta.url)
  const dynamic = JSON.parse(await readFile(path, 'utf8'))
  const build = () => readProject({ ...project, asc_count: 128, manifests: { dynamic } }, 'ota', origin)
  assert.match(build().summaries.join(' '), /791531/)
  assert.match(build().summaries.join(' '), /源帧工程未核验/)
  dynamic.time_source = 'operator_segment_durations'
  dynamic.evidence = 'offline_timeline_doppler'
  assert.match(build().summaries.join(' '), /操作员提供的逐段时长/)
  assert.doesNotMatch(build().summaries.join(' '), /由帧间距离和速度估算/)
  const baseline = {
    ...dynamic, evidence: 'offline_ideal_plane_wave', source_frames_only: true,
    header: { ...dynamic.header, cir_count: 1 },
    metrics: Array.from({ length: 12 }, (_, i) => ({
      frame: 0, tx: Math.floor(i / 3), offset_hz: [-50e6, 0, 50e6][i % 3],
      field_nmse: i === 0 ? null : 0.125, power_ratio: 1,
    })),
  }
  const both = readProject({ ...project, asc_count: 128, manifests: { baseline, dynamic } }, 'ota', origin)
  assert.match(both.summaries[0], /1.25e-1/)
  assert.match(both.summaries[0], /1 项未核验/)
  dynamic.port_phase['0-1'].compared--
  assert.match(build().summaries.join(' '), /动态工程未核验/)
  assert.doesNotMatch(build().summaries.join(' '), /791531/)
})
