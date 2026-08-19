/**
 * P1-57 全集门：运行态暗室消费者只许读全局上下文。
 *
 * 不变量（而非逐文件存在性）：全仓 src 里凡出现 fetchLabProfiles /
 * fetchAllLabProfiles 的文件 ⊆ 显式 allowlist。新页面想自拉 LabProfile
 * 列表当运行态真值 → 本门当场红，逼它走 useOperationalLab()。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = join(import.meta.dirname, '..', 'src')

function walk(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...walk(p))
    else if (/\.(ts|tsx)$/.test(name)) out.push(p)
  }
  return out
}

const read = (rel: string) => readFileSync(join(ROOT, rel), 'utf8')

/** 运行态消费者（设计稿 §7）：必须读全局上下文，不许自拉列表 */
const OPERATIONAL_CONSUMERS = [
  'components/OTAMapper/ProbeArraySelector.tsx',
  'features/Diagnostics/CommissioningAdhocPanel.tsx',
  'features/Diagnostics/SequenceRunnerPanel.tsx',
  'features/ProbeCalibration/components/RFChainDiagramPanel.tsx',
  'components/ChamberConfigCard.tsx',
  'components/Commissioning/index.tsx',
  'features/TopologyEditor/TopologyEditor.tsx',
]

/** 允许触碰 fetchLabProfiles 的文件（各自理由必须成立） */
const FETCH_ALLOWLIST = new Map<string, RegExp | null>([
  // API 层定义本体
  ['api/labProfileService.ts', null],
  // 上下文 provider —— 全局唯一的数据入口
  ['features/OperationalLab/OperationalLabContext.tsx', null],
  // 纯函数模块只是 doc 注释里提到，不实际调用
  ['features/OperationalLab/operationalLabSelection.ts', null],
  // App.tsx 只剩 0-labs wizard 门那一处（拉不到就渲染首启向导）
  ['App.tsx', /needsLabProfileWizard|wizard/i],
  // 记录绑定编辑器（设计稿 §7 明确保留）：TestCase 的 lab 绑定是业务记录，
  // 不是运行态上下文 —— 这两个 modal 用 fetchAllLabProfiles（含停用行）
  ['components/TestPlanManagement/TestCaseEditModal.tsx', /fetchAllLabProfiles/],
  ['components/TestPlanManagement/TestCaseCreateModal.tsx', /fetchAllLabProfiles/],
])

test('运行态消费者逐个：读全局上下文，不自拉列表、不留页面级选择', () => {
  for (const rel of OPERATIONAL_CONSUMERS) {
    const s = read(rel)
    assert.match(s, /useOperationalLab/, `${rel} 没有消费全局上下文`)
    assert.doesNotMatch(s, /fetchLabProfiles\(|fetchAllLabProfiles\(/,
      `${rel} 还在自拉 LabProfile 列表`)
    assert.doesNotMatch(s, /setSelectedLab(Profile)?Id/,
      `${rel} 还维护页面级 LabProfile 选择 —— 平行真值源`)
  }
})

test('全仓不变量：触碰 fetchLabProfiles 的文件 ⊆ allowlist', () => {
  const offenders: string[] = []
  for (const abs of walk(ROOT)) {
    const rel = relative(ROOT, abs)
    const s = readFileSync(abs, 'utf8')
    if (!/fetchLabProfiles|fetchAllLabProfiles/.test(s)) continue
    if (!FETCH_ALLOWLIST.has(rel)) {
      offenders.push(rel)
      continue
    }
    const guard = FETCH_ALLOWLIST.get(rel)
    if (guard && !guard.test(s)) {
      offenders.push(`${rel}（allowlist 理由不再成立：${guard}）`)
    }
  }
  assert.deepEqual(offenders, [],
    '这些文件绕过全局上下文自拉 LabProfile —— 要么改读 useOperationalLab()，' +
    '要么在本门写明记录绑定理由：\n  ' + offenders.join('\n  '))
})

test('App.tsx 的 fetchLabProfiles 只剩 wizard 门那一处', () => {
  const s = read('App.tsx')
  const calls = s.match(/fetchLabProfiles\(/g) ?? []
  assert.equal(calls.length, 1,
    `App.tsx 里 fetchLabProfiles 调用应恰好 1 处（0-labs wizard 门），实际 ${calls.length}`)
})
