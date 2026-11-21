import test from 'node:test'
import assert from 'node:assert/strict'
import { isRtScene } from '../src/features/ChannelWorkbench/rtScenes.ts'

test('场景是原记录的视图，只接纳显式标记的 SMU 或原生 RT 轨迹', () => {
  const vendor = { source_type: 'vendor_file', payload: {}, associated_file_path: 'D:\\RT-IMT-2030.smu' }
  assert.equal(isRtScene(vendor), false)
  const scene = { ...vendor, payload: { rt_scene: true } }
  assert.equal(isRtScene(scene), true)
  assert.equal(isRtScene({ ...scene, associated_file_path: 'offline.zip' }), false)
  assert.equal(isRtScene({ ...scene, payload: { rt_scene: 'false' } }), false)
  assert.equal(isRtScene({ ...vendor, source_type: 'rt_dynamic' }), true)
})
