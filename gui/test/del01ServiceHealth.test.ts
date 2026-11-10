import assert from 'node:assert/strict'
import test from 'node:test'

// 浏览器入口只需 location；HTTP 请求均由测试替换。
Object.defineProperty(globalThis, 'window', {
  configurable: true, value: { location: { origin: 'http://api.invalid' } },
})
const { ChannelEngineClient } = await import('../src/services/channelEngine.ts')
delete (globalThis as Record<string, unknown>).window

for (const [status, value, expected] of [
  ['healthy', true, true], ['degraded', true, true],
  ['healthy', false, false], ['degraded', false, false],
  ['healthy', undefined, false], ['healthy', 'true', false], ['healthy', 1, false],
] as const) {
  test(`计算服务独立状态：${status}/${value} => ${expected}`, async (t) => {
    t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
      assert.equal(url, 'http://api.invalid/api/v1/health')
      assert.equal(init.method, 'GET')
      return new Response(JSON.stringify({ status, channel_engine_available: value }))
    })
    assert.equal(await new ChannelEngineClient().isAvailable(), expected)
  })
}

test('请求失败时不确认计算服务可用', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('网络不可用') })
  assert.equal(await new ChannelEngineClient().isAvailable(), false)
})

test('HTTP错误时不确认计算服务可用', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('{}', { status: 503 }))
  assert.equal(await new ChannelEngineClient().isAvailable(), false)
})
