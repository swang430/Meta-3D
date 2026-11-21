import assert from 'node:assert/strict'
import test from 'node:test'
import { readBundle } from '../src/features/ChannelWorkbench/imtBundle.ts'

test('离线包不能冒充真机验收', () => {
  assert.throws(
    () => readBundle({ mode: 'ota', hardware_verified: true }, 'ota'),
    /离线/,
  )
})

const conducted = {
  hardware_verified: false,
  smu_built: false,
  mode: 'conducted',
  direction: 'downlink',
  evidence: 'offline_asc_validation',
  header: { cir_count: 6188, taps: 24, rate_hz: 171, carrier_hz: 2565000000 },
  links: Array.from({ length: 8 }, (_, i) => ({
    tx: i >> 1,
    rx: i % 2,
    file: `R0B0S0D_TX${i >> 1}_RX${i % 2}_H.asc`,
    sha256: '0'.repeat(64),
  })),
}
test('四发两收逐条保留逻辑端口，缺路或重复时拒绝交接', () => {
  assert.equal(readBundle(conducted, 'conducted').links[7].destination, 'RX1')
  assert.throws(() =>
    readBundle({ ...conducted, links: conducted.links.slice(1) }, 'conducted'),
  )
  assert.throws(() =>
    readBundle(
      { ...conducted, links: conducted.links.map(() => conducted.links[0]) },
      'conducted',
    ),
  )
})

test('文件名能区分阵元，禁止互换接收端口', () => {
  assert.throws(
    () =>
      readBundle(
        {
          ...conducted,
          links: conducted.links.map((l) => ({ ...l, rx: 1 - l.rx })),
        },
        'conducted',
      ),
    /端口/,
  )
})
