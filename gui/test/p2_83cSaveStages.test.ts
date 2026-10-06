import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('probe editor labels its existing draft and server save stages', () => {
  const source = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8').split('function ProbeManager(')[1]
  assert.match(source, /探头草稿未保存/)
  assert.match(source, /探头配置已保存到服务器/)
  const stage = source.split('data-testid="probe-save-stage"')[1].split('</Text>')[0]
  assert.doesNotMatch(stage, /updateMutation|replaceMutation/)
})
test('chamber current stage does not reuse another Lab operation receipt', () => {
  const source = readFileSync(new URL('../src/components/ChamberConfigCard.tsx', import.meta.url), 'utf8')
  const stage = source.split('data-testid="chamber-save-stage"')[1].split('</Text>')[0]
  assert.doesNotMatch(stage, /createFromTemplateMutation|activateMutation/)
  assert.match(stage, /服务器LabProfile绑定/)
})
test('topology keeps the draft after save refusal and exposes persistent save stage', () => {
  const source = readFileSync(new URL('../src/features/TopologyEditor/TopologyEditor.tsx', import.meta.url), 'utf8')
  assert.match(source, /拓扑保存失败；草稿未保存/)
  assert.match(source, /setSaveResult\('failed'\)/)
  assert.match(source, /setSaveResult\('saved'\)/)
})
test('chamber form explicitly describes unsaved creation separately from Lab binding', () => {
  const source = readFileSync(new URL('../src/components/CreateChamberForm.tsx', import.meta.url), 'utf8')
  assert.match(source, /暗室草稿尚未创建/)
  assert.match(source, /isLoading \? '正在创建暗室配置'/)
})
