import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const read = (rel: string) =>
  readFileSync(join(import.meta.dirname, '..', rel), 'utf8')

const svc = () => read('src/api/switchTopologyService.ts')
const editor = () => read('src/features/TopologyEditor/TopologyEditor.tsx')

test('service 的每个数据方法都携带 lab_profile_id', () => {
  const s = svc()
  // 五个方法（listTemplates 除外）都必须把 lab 真值发给后端
  for (const m of ['getTopologies', 'getTopology', 'updateTopology', 'importFromTemplate', 'validateTopology']) {
    const i = s.indexOf(`async ${m}(`)
    assert.ok(i > -1, `缺方法 ${m}`)
    const seg = s.slice(i, s.indexOf('},', i))
    assert.match(seg, /lab_profile_id|labProfileId/, `${m} 没带 lab_profile_id`)
  }
})

test('重导入走服务端 replace_existing，编辑器不再客户端先删后导', () => {
  assert.match(svc(), /replace_existing/)
  assert.doesNotMatch(editor(), /apiClient\.delete\(/,
    '编辑器还在客户端删行 —— lab/模板解析失败时行已经没了（先删后验）')
})

test('编辑器不再拉全部暗室、不再渲染「目标暗室」下拉', () => {
  const s = editor()
  assert.doesNotMatch(s, /fetchChamberConfigurations/)
  assert.doesNotMatch(s, /目标暗室/)
})

test('编辑器不再维护页面级暗室选择，也不从最新 topology 行播种', () => {
  const s = editor()
  assert.doesNotMatch(s, /setSelectedChamberId|selectedChamberId/,
    '页面级 selectedChamberId 还在 —— 平行真值源没删干净')
})

test('编辑器消费全局上下文，dirty 时注册切换阻断', () => {
  const s = editor()
  assert.match(s, /useOperationalLab\(/)
  assert.match(s, /useOperationalLabSwitchGuard\(/)
  assert.match(s, /onDirtyChange/)
})

test('保存不再自行提交 chamber_id —— 暗室由后端从 lab 派生', () => {
  const s = editor()
  assert.doesNotMatch(s, /chamber_id:\s*selectedChamberId/)
})
