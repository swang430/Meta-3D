import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const read = (rel: string) =>
  readFileSync(join(import.meta.dirname, '..', rel), 'utf8')

const ctx = () => read('src/features/OperationalLab/OperationalLabContext.tsx')

test('provider 只用 fetchLabProfiles(true)，不拉全量也不拉停用行', () => {
  const s = ctx()
  assert.match(s, /fetchLabProfiles\(true\)/)
  assert.doesNotMatch(s, /fetchLabProfiles\(false\)/)
  assert.doesNotMatch(s, /fetchAllLabProfiles/)
})

test('localStorage 唯一 key：mimo.operationalLabProfileId，且旧 key 迁移后删除', () => {
  const s = ctx()
  assert.match(s, /['"]mimo\.operationalLabProfileId['"]/)
  // 迁移只认这一个旧 key（全集搜索实证：ProbeManager 的选择不落盘）
  assert.match(s, /['"]mimo\.commissioning\.lastLabId['"]/)
  // 迁移尝试之后必须删旧 key —— 不允许双读
  assert.match(s, /removeItem\(/)
})

test('决策走 Task 1 的纯函数，provider 自己不许猜第一项', () => {
  const s = ctx()
  assert.match(s, /decideOperationalLabSelection/)
  assert.doesNotMatch(s, /activeLabs\[0\]|labs\[0\]|profiles\[0\]/)
})

test('暴露 lab 与派生的 chamber identity', () => {
  const s = ctx()
  assert.match(s, /chamberId/)
  assert.match(s, /chamberName/)
  assert.match(s, /chamber_config_id/)
})

test('guard 有阻断时 requestLabChange 先返回，不碰状态与 localStorage', () => {
  const s = ctx()
  const fn = s.slice(s.indexOf('const requestLabChange'))
  const blockCheck = fn.search(/blockers\.length/)
  const persist = fn.search(/setItem\(/)
  assert.ok(blockCheck > -1, 'requestLabChange 里没有阻断检查')
  assert.ok(persist > -1, 'requestLabChange 里没有持久化写入')
  assert.ok(blockCheck < persist, '阻断检查必须发生在持久化写入之前')
})

test('main.tsx 在 QueryClientProvider 内挂 OperationalLabProvider', () => {
  const s = read('src/main.tsx')
  const qcp = s.indexOf('<QueryClientProvider')
  const olp = s.indexOf('<OperationalLabProvider')
  assert.ok(olp > -1, 'main.tsx 没挂 OperationalLabProvider')
  assert.ok(qcp > -1 && olp > qcp, 'provider 必须在 QueryClientProvider 之内')
})

test('App header 渲染唯一选择器', () => {
  const s = read('src/App.tsx')
  assert.match(s, /<OperationalLabSelector/)
})

test('selector 同时展示 LabProfile 与派生暗室，三种异常态分开', () => {
  const s = read('src/features/OperationalLab/OperationalLabSelector.tsx')
  assert.match(s, /chamberName/)
  assert.match(s, /请选择当前 LabProfile/)   // 多项未选
  assert.match(s, /未绑定暗室/)              // 绑定缺失 fail-closed 展示
})
