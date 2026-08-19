import test from 'node:test'
import assert from 'node:assert/strict'

import {
  decideOperationalLabSelection,
  type OperationalLabCandidate,
} from '../src/features/OperationalLab/operationalLabSelection.ts'

const lab = (
  id: string,
  overrides: Partial<OperationalLabCandidate> = {},
): OperationalLabCandidate => ({
  id,
  name: `Lab ${id}`,
  is_active: true,
  chamber_config_id: `chamber-${id}`,
  ...overrides,
})

test('0 个活动 LabProfile：无选择', () => {
  const r = decideOperationalLabSelection({
    activeLabs: [],
    persistedId: null,
    legacyIds: [],
  })
  assert.equal(r.selectedId, null)
  assert.equal(r.source, null)
})

test('恰好 1 个活动项：自动选择（即使无 chamber 绑定 —— fail-closed 在消费端）', () => {
  const only = lab('a', { chamber_config_id: null })
  const r = decideOperationalLabSelection({
    activeLabs: [only],
    persistedId: null,
    legacyIds: [],
  })
  assert.equal(r.selectedId, 'a')
  assert.equal(r.source, 'single')
})

test('多个活动项且无持久化值：不选第一项，要求显式选择', () => {
  const r = decideOperationalLabSelection({
    activeLabs: [lab('a'), lab('b')],
    persistedId: null,
    legacyIds: [],
  })
  assert.equal(r.selectedId, null)
  assert.equal(r.source, null)
})

test('有效持久化值：恢复它（而不是第一项）', () => {
  const r = decideOperationalLabSelection({
    activeLabs: [lab('a'), lab('b')],
    persistedId: 'b',
    legacyIds: [],
  })
  assert.equal(r.selectedId, 'b')
  assert.equal(r.source, 'persisted')
})

test('持久化值不在活动集合：拒绝，不回退到第一项', () => {
  const r = decideOperationalLabSelection({
    activeLabs: [lab('a'), lab('b')],
    persistedId: 'gone',
    legacyIds: [],
  })
  assert.equal(r.selectedId, null)
  assert.equal(r.source, null)
})

test('持久化值已停用：拒绝（列表里仍有多个活动项，不自动替它挑）', () => {
  // b 停用但混进了列表（防御场景）；a/c 都活动 → 多项 + 无效持久化 = 无选择
  const r = decideOperationalLabSelection({
    activeLabs: [lab('a'), lab('b', { is_active: false }), lab('c')],
    persistedId: 'b',
    legacyIds: [],
  })
  assert.equal(r.selectedId, null)
})

test('持久化值停用后只剩唯一活动项：按单项规则自动选它', () => {
  const r = decideOperationalLabSelection({
    activeLabs: [lab('a'), lab('b', { is_active: false })],
    persistedId: 'b',
    legacyIds: [],
  })
  assert.equal(r.selectedId, 'a')
  assert.equal(r.source, 'single')
})

test('持久化值无 chamber 绑定：拒绝恢复（宁可要求重选，不加载错暗室）', () => {
  const r = decideOperationalLabSelection({
    activeLabs: [lab('a'), lab('b', { chamber_config_id: null })],
    persistedId: 'b',
    legacyIds: [],
  })
  assert.equal(r.selectedId, null)
})

test('旧 commissioning key 迁移：仅当它仍指向有效且有绑定的 LabProfile', () => {
  const r = decideOperationalLabSelection({
    activeLabs: [lab('a'), lab('b')],
    persistedId: null,
    legacyIds: ['b'],
  })
  assert.equal(r.selectedId, 'b')
  assert.equal(r.source, 'legacy')
})

test('旧 key 指向失效项：迁移失败，无选择（不猜第一项）', () => {
  const r = decideOperationalLabSelection({
    activeLabs: [lab('a'), lab('b')],
    persistedId: null,
    legacyIds: ['dead', null],
  })
  assert.equal(r.selectedId, null)
  assert.equal(r.source, null)
})

test('持久化值优先于旧 key', () => {
  const r = decideOperationalLabSelection({
    activeLabs: [lab('a'), lab('b')],
    persistedId: 'a',
    legacyIds: ['b'],
  })
  assert.equal(r.selectedId, 'a')
  assert.equal(r.source, 'persisted')
})
