import assert from 'node:assert/strict'
import test from 'node:test'
import { verifyClusters } from '../src/features/ChannelWorkbench/clusterVerification.ts'

const hash = 'a'.repeat(64)
const source = { mpdb: hash, members: hash }
const id = { frame: 3, tx: 1, rx: 0, cluster: 7 }
const results = {
  schema: 'joint-results/1',
  source,
  rows: [{ ...id, real: 1, imag: 0, doppler: 2 }],
}
const evidence = {
  schema: 'joint-evidence/1',
  source,
  rows: [
    { ...id, sumReal: 1, sumImag: 0, sumAbs: 1, count: 1, minHz: 2, maxHz: 2 },
  ],
}
test('真实边界通过，单簇频移越界定位，证据缺失放行', () => {
  assert.equal(verifyClusters(results, evidence).checked, 1)
  const wrong = structuredClone(results)
  wrong.rows[0].doppler = 3
  const report = verifyClusters(wrong, evidence)
  assert.equal(report.warnings.length, 1)
  assert.deepEqual(report.warnings[0].id, id)
  assert.equal(verifyClusters(results, null).unknown, 1)
  assert.equal(
    verifyClusters(results, {
      ...evidence,
      source: { ...source, mpdb: 'b'.repeat(64) },
    }).unknown,
    1,
  )
})

test('有效的多普勒证据不因另一项缺测而丢失，相干相消允许放行', () => {
  const r = { ...results, rows: [{ ...id, real: 0, imag: 0, doppler: 5 }] }
  const e = {
    ...evidence,
    rows: [
      {
        ...id,
        sumReal: 0,
        sumImag: 0,
        sumAbs: 2,
        count: 2,
        minHz: 4,
        maxHz: 6,
      },
    ],
  }
  assert.equal(verifyClusters(r, e).warnings.length, 0)
  r.rows[0].real = 1
  assert.match(verifyClusters(r, e).warnings[0].message, /复系数/)
  const partial = { ...e, rows: [{ ...e.rows[0], sumReal: null, maxHz: 4 }] }
  const report = verifyClusters(r, partial)
  assert.equal(report.unknown, 1)
  assert.equal(report.warnings.length, 1)
  assert.match(report.warnings[0].message, /多普勒/)
})

test('成员统计自相矛盾时不能指控复系数异常', () => {
  const report = verifyClusters(results, {...evidence, rows: [{...evidence.rows[0], sumAbs:0, sumReal:2}]})
  assert.equal(report.unknown, 1)
  assert.equal(report.warnings.length, 0)
})
