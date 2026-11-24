// 用已有的 Playwright 环境运行；全部接口响应由浏览器夹具提供。
import { verifyConductedStopRecovery } from "./vrtConductedStopRecovery.browser.js"
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import { verifyCalibrationRegistration, verifyConductedStart } from './vrtConductedHardware.browser.js'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const root = fileURLToPath(new URL('../', import.meta.url))
const bundle = await build({
  stdin: {
    resolveDir: root, loader: 'tsx',
    contents: `
      import React from 'react'
      import { createRoot } from 'react-dom/client'
      import { MantineProvider } from '@mantine/core'
      import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
      import { ConductedExecutionModal } from './src/components/VirtualRoadTest/ConductedExecutionModal'
      createRoot(document.getElementById('root')).render(
        <MantineProvider><QueryClientProvider client={new QueryClient()}>
          <ConductedExecutionModal opened onClose={() => {}} scenario={{ id: 'scenario', name: '测试' }}
            initialId={location.hash === '#new' ? undefined : 'sample'} />
        </QueryClientProvider></MantineProvider>
      )
    `,
  },
  jsx: 'automatic', bundle: true, write: false, define: { 'process.env.NODE_ENV': '"production"' },
})
const browser = await chromium.launch({ channel: process.env.CHROMIUM_CHANNEL })
try {
  for (const [check, hash] of [[verifyConductedStopRecovery, ''], [verifyConductedStart, ''], [verifyCalibrationRegistration, '#new']]) {
    const page = await browser.newPage()
    await page.route('**/*', route => route.abort())
    await page.route('http://fixture.test/', route => route.fulfill({
      contentType: 'text/html', body: '<div id="root"></div><script src="/fixture.js"></script>',
    }))
    await page.route('http://fixture.test/fixture.js', route => route.fulfill({
      contentType: 'text/javascript', body: bundle.outputFiles[0].text,
    }))
    await check(page, async () => {
      await page.goto('about:blank')
      await page.goto('http://fixture.test/' + hash)
    })
    console.log('通过', check.name)
    await page.close()
  }
} finally {
  await browser.close()
}
