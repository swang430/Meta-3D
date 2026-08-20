import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const read = (rel: string) =>
  readFileSync(join(import.meta.dirname, '..', rel), 'utf8')

import { readdirSync, statSync } from 'node:fs'
function walkSrc(dir = join(import.meta.dirname, '..', 'src')): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...walkSrc(p))
    else if (/\.(ts|tsx)$/.test(name)) out.push(p)
  }
  return out
}

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

test('Commissioning 的 guard 有真实的释放出口（结束会话）', () => {
  // 外审 R1：「重置会话」是立即重建（session 永不为 null），guard 永远解不开。
  const s = read('src/components/Commissioning/index.tsx')
  assert.match(s, /结束会话/)
  assert.match(s, /setSession\(null\)/,
    '没有把 session 置回 null 的出口 —— 操作员只能离开页面才能切 LabProfile')
})

test('「结束会话」在硬件请求在途时禁用 —— 不许边跑边释放 guard', () => {
  // 外审 R2 P1：runPhase/runAll 在途时点结束，请求继续驱动硬件而 guard 已释放，
  // 旧请求回来还会把 session 塞回新 lab 上下文。
  const s = read('src/components/Commissioning/index.tsx')
  // 锚在最后一处「结束会话」（按钮文本）—— 前面还有 guard 文案与提示语
  const i = s.lastIndexOf('结束会话')
  assert.ok(i > -1)
  const btn = s.slice(s.lastIndexOf('<Button', i), i)
  // 外审 R3：真值换成 provider 的在途工作登记表（页面卸载不消失、并发计数）。
  // 共享布尔那套已死：先落定的请求会提前放行。
  assert.match(btn, /disabled=\{hardwareBusy\}/,
    '结束会话的禁用没读在途工作登记表')
  // 内审 F3：token 在、语义坏的绕法 —— 判据源也钉住
  assert.match(s, /hardwareBusy = activeWork\.length > 0/,
    'hardwareBusy 的派生判据被改动（如 > 1），单请求在途时按钮会可点')
})

test('硬件请求路径全部登记在途工作，且 release 在 finally/出口路径里', () => {
  // 外审 R3 + 内审 F1/F2：登记表是 guard 的真值 —— 漏包一条路径就留窗口；
  // release 挪出 finally（begin 后立即调）计数照样对，所以逐处验位置。
  const EXPECT = [
    ['src/components/Commissioning/index.tsx', 'commissioning', 5],
    ['src/components/SystemCalibration/CalibrationWizard.tsx', 'calibration', 1],
    ['src/components/SystemCalibration/BaselineCalibrationCard.tsx', 'calibration', 2],
  ] as const
  for (const [rel, key, n] of EXPECT) {
    const s = read(rel)
    const begins = (s.match(new RegExp(`beginWork\\('${key}'`, 'g')) ?? []).length
    assert.equal(begins, n, `${rel} 应登记 ${n} 处，实际 ${begins}`)
    const releases = (s.match(/releaseWork\(\)/g) ?? []).length
    assert.equal(releases, begins, `${rel} begin/release 不成对`)
    // 内审 F2：release 必须出现在 finally 块或 catch/成功出口里 ——
    // 判据：每个 releaseWork() 之前最近的块关键字不能是 beginWork 所在行
    // （即不许 begin 后立即 release）。机械可验的最小形态：
    assert.doesNotMatch(s, /beginWork\([^)]*\)[\s\S]{0,80}?releaseWork\(\)/,
      `${rel} 存在 begin 后立即 release 的空登记 —— 请求全程不受保护`)
  }
})

test('「一键执行全流程」在途时禁用', () => {
  const s = read('src/components/Commissioning/index.tsx')
  const i = s.indexOf('一键执行全流程')
  const btn = s.slice(s.lastIndexOf('<Button', i), i)
  assert.match(btn, /disabled=\{hardwareBusy\}/)
})

test('校准页不再写死暗室 id —— 全仓无硬编码 chamber UUID', () => {
  // 外审 R3：CalibrationWizard 写死 b7cd8de0…（P1-28 审计里已删除的孤儿暗室），
  // BaselineCalibrationCard 写死全零 —— 全集门按「拉 lab 列表」的形状 grep，
  // 抓不到这类写死 UUID 的消费者。补一条不变量。
  const offenders: string[] = []
  for (const abs of walkSrc()) {
    const t = readFileSync(abs, 'utf8')
    for (const m of t.matchAll(/chamberId\s*=\s*['"][0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}['"]/gi)) {
      offenders.push(`${abs}: ${m[0]}`)
    }
  }
  assert.deepEqual(offenders, [], '写死的 chamber UUID：\n' + offenders.join('\n'))
})
