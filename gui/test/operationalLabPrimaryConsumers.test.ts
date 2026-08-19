import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const read = (rel: string) =>
  readFileSync(join(import.meta.dirname, '..', rel), 'utf8')

test('ProbeManager 不再声明自己的 LabProfile 选择状态', () => {
  const s = read('src/App.tsx')
  assert.doesNotMatch(s, /setSelectedLabProfileId/,
    'App.tsx 里还有页面级 LabProfile 选择 —— 平行真值源没删干净')
  // ProbeManager 段消费全局上下文
  const pm = s.slice(s.indexOf('function ProbeManager'))
  assert.match(pm, /useOperationalLab\(/)
})

test('ChamberConfigCard 读全局上下文，不再收页面级选择 props', () => {
  const s = read('src/components/ChamberConfigCard.tsx')
  assert.match(s, /useOperationalLab\(/)
  assert.doesNotMatch(s, /onLabProfileChange/,
    '还在从父组件收 LabProfile 选择回调 —— 选择入口必须只有 header 一个')
})

test('ChamberConfigCard 重绑暗室成功后刷新全局上下文', () => {
  const s = read('src/components/ChamberConfigCard.tsx')
  assert.match(s, /invalidateQueries\(\{\s*queryKey:\s*\['lab-profiles'\]/,
    '改了 LabProfile 的 chamber 绑定却不刷新全局上下文 —— header 会显示旧暗室名')
})

test('Commissioning 不再读写 mimo.commissioning.lastLabId', () => {
  const s = read('src/components/Commissioning/index.tsx')
  assert.doesNotMatch(s, /mimo\.commissioning\.lastLabId|LAST_LAB_LS_KEY/,
    '旧 localStorage key 还在 —— 迁移已由全局上下文一次性完成，不许双读')
})

test('Commissioning 的会话创建使用全局 LabProfile，且不再自拉列表', () => {
  const s = read('src/components/Commissioning/index.tsx')
  assert.match(s, /useOperationalLab\(/)
  assert.doesNotMatch(s, /fetchLabProfiles/,
    '还在自己拉 LabProfile 列表 —— 运行态消费者只该读全局上下文')
})

test('Commissioning 有会话时注册切换阻断', () => {
  const s = read('src/components/Commissioning/index.tsx')
  assert.match(s, /useOperationalLabSwitchGuard\(/)
  // guard 的 reason 必须依赖 session 存在与否
  const i = s.indexOf('useOperationalLabSwitchGuard(')
  const seg = s.slice(i, i + 300)
  assert.match(seg, /session/, 'guard 没跟 session 状态挂钩')
})

test('Commissioning 不把「列表加载失败」当成「尚无 LabProfile」', () => {
  // 内审 F1（设计 §8）：失败时引导操作员去建重复 LabProfile 比不提示更糟。
  const s = read('src/components/Commissioning/index.tsx')
  const i = s.indexOf('noActiveLab =')
  assert.ok(i > -1)
  const line = s.slice(i, s.indexOf('\n', i))
  assert.match(line, /labsError|error/,
    'noActiveLab 的判定没排除加载失败 —— 瞬断会被当成 0 个 LabProfile')
})
