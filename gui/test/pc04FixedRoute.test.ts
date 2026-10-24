import assert from 'node:assert/strict'
import test from 'node:test'
import { fixedRouteDisplay } from '../src/features/LabWorkspace/fixedRouteDisplay.ts'

test('模拟和失败记录不因夹带数值显示成实测损耗', () => {
  for (const status of ['simulated', 'failed', 'cancelled', 'cleanup_unconfirmed', 'interrupted', 'incomplete', 'running']) {
    const shown = fixedRouteDisplay({ status, result: { status, net_loss_db: 28, sample_std_db: 0, samples: [
      { source_before_dbm: -20, source_after_dbm: -20, received_dbm: -50 }], cleanup_confirmed: true } } as never)
    assert.equal(shown.loss, '未计算')
    assert.equal(shown.source, '无实测读数')
  }
})

test('已完成只展示服务器计算结果，保留负增益和未知', () => {
  const result = { status: 'completed', cleanup_confirmed: true, net_loss_db: -12,
    sample_std_db: 0.1, samples: [{ source_before_dbm: -20, source_after_dbm: -20, received_dbm: -10 }] }
  const shown = fixedRouteDisplay({ status: 'completed', result } as never)
  assert.equal(shown.loss, '-12.00 dB（增益）')
  assert.equal(shown.source, '-20.00 dBm')
  assert.equal(fixedRouteDisplay({ status: 'completed', result: { ...result, net_loss_db: null } } as never).loss, '未计算')
})

test('清理未确认或结果与外层状态不同不能展示成功读数', () => {
  for (const result of [{ status: 'simulated', cleanup_confirmed: true, net_loss_db: 28 },
    { status: 'completed', cleanup_confirmed: false, net_loss_db: 28 }]) {
    assert.equal(fixedRouteDisplay({ status: 'completed', result } as never).loss, '未计算')
  }
})
