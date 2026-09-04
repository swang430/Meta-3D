import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (relative: string) => readFileSync(new URL(relative, import.meta.url), 'utf8')

test('all API mirrors expose server-owned channel-emulator certification', () => {
  const generated = read('./api.generated.ts')
  const handwritten = read('./api.ts')
  const service = read('../api/service.ts')

  for (const source of [generated, handwritten]) {
    assert.match(source, /ChannelEmulatorSiteCertification/)
    assert.match(source, /ChannelEmulatorCertificationPreview/)
    assert.match(source, /channel_emulator_site_certification/)
    assert.match(source, /channel_emulator_site_certification_preview/)
  }
  assert.match(service, /certifyChannelEmulatorSite/)
  assert.match(service, /revokeChannelEmulatorSiteCertification/)
  assert.match(service, /channel-emulator-site-certification/)
})

test('GUI consumes only the server certification projection and dedicated writes', () => {
  const app = read('../App.tsx')
  const readiness = read('../features/Dashboard/ZoneReadiness.tsx')
  const testCase = read('../components/TestCaseConfig/MIMOOTAConfigForm.tsx')
  const mocks = read('../api/mockDatabase.ts')

  assert.match(app, /channel_emulator_site_certification/)
  assert.match(app, /fetchReadiness\(selectedLabProfileId/)
  assert.match(app, /channelEmulatorCertificationPreview\?\.status === 'formal_ready'/)
  assert.match(app, /certifyChannelEmulatorSite/)
  assert.match(app, /revokeChannelEmulatorSiteCertification/)
  assert.match(readiness, /channel_emulator_site_certification_preview/)
  assert.match(readiness, /仅诊断/)
  assert.match(readiness, /UNKNOWN\/N\/A/)
  assert.match(testCase, /channel_emulator_site_certification_preview/)
  assert.match(testCase, /信道仿真器现场认证/)
  assert.match(mocks, /channel_emulator_site_certification_preview/)
})
