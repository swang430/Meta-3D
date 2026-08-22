import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const service = readFileSync(new URL('../src/api/channelAssetService.ts', import.meta.url), 'utf8')
const workbench = readFileSync(
  new URL('../src/features/ChannelWorkbench/ChannelWorkbench.tsx', import.meta.url),
  'utf8',
)

test('SMU scan and sync clients never accept client-supplied truth', () => {
  assert.match(service, /scanSMUProjects\(\):\s*Promise<SMUProjectSyncPreview>/)
  assert.match(service, /post<SMUProjectSyncPreview>\('\/channel-assets\/vendor-files\/smu-scan'\)/)
  assert.match(service, /syncSMUProjects\(\):\s*Promise<SMUProjectSyncResult>/)
  assert.match(service, /post<SMUProjectSyncResult>\('\/channel-assets\/vendor-files\/smu-sync'\)/)
  assert.doesNotMatch(service, /syncSMUProjects\([^)]*payload/)
})

test('workbench previews before explicit sync and refreshes both truth consumers', () => {
  assert.match(workbench, /扫描 F64 工程/)
  assert.match(workbench, /scanSMUProjects/)
  assert.match(workbench, /syncSMUProjects/)
  assert.match(workbench, /可同步/)
  assert.match(workbench, /受保护/)
  assert.match(workbench, /确认同步/)
  assert.match(workbench, /queryKey:\s*\['channel-assets'\]/)
  assert.match(workbench, /queryKey:\s*\['instruments',\s*'channelModels'\]/)
  assert.match(workbench, /queryKey:\s*\['channelModels'\]/)
})
