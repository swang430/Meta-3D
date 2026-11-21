import assert from 'node:assert/strict'
import test from 'node:test'
import {
  projectParameters,
  readProject,
} from '../src/features/ChannelWorkbench/mpdbProject.ts'

const origin = 'https://example.test'
const project = { asc_count: 8, download_url: '/project.zip' }

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
