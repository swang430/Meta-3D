import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { buildSync } from 'esbuild'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const { MantineProvider } = require('@mantine/core')
const compiled = buildSync({ entryPoints: ['src/components/Report/ReportViewer.tsx'], bundle: true,
  write: false, platform: 'node', format: 'cjs', packages: 'external', jsx: 'automatic',
  plugins: undefined }).outputFiles[0].text
// 仅图表依赖需要浏览器；本次渲染概览不使用它们。
const module = { exports: {} }
const load = name => name.startsWith('react-plotly') || name.includes('plotly.js') ? (() => null) : require(name)
new Function('require', 'module', 'exports', compiled)(load, module, module.exports)
const { QueryClient, QueryClientProvider } = require('@tanstack/react-query')
const render = (trace, fields = {}) => renderToStaticMarkup(React.createElement(MantineProvider, {},
  React.createElement(QueryClientProvider, { client: new QueryClient() }, React.createElement(module.exports.ReportViewer,
    { contentData: { source: 'test_plan', title: '合成历史', execution_id: 'e', execution: { status: 'completed' },
      overall_result: 'undetermined', pass_rate: null, phases: [], kpi_summary: [], events: [], calibration_traceability: trace, ...fields } }))))
const trace = { schema_version: 1, status: 'applied', provenance: 'real', execution_frequency_mhz: 2595,
  raw_readings_embedded: false, routes: [
    { chain_id: 'v', source_kind: 'confirmed_route', source_id: 'old-confirmed', application_state: 'selected', certification_status: 'unknown',
      source_snapshot: { frequency_mhz: 2595, acquisition_run_id: 'original-run', predecessor_id: 'previous-source', reference_plane: '原参考面' } },
    { chain_id: 'h', source_kind: 'legacy_certificate', source_id: 'old-cert', application_state: 'applied', certification_status: 'unknown', source_snapshot: { frequency_mhz: 2500 } },
    { chain_id: 'u', source_kind: 'confirmed_route', source_id: 'lost', application_state: 'unknown', source_snapshot: null },
  ] }
test('混合来源逐链显示选择/应用/未知，不从顶层 applied 提升未知链', () => {
  const html = render(trace)
  for (const value of ['old-confirmed', 'old-cert', 'original-run', 'previous-source', '原参考面', '2595', '2500', '仅选择，未应用', '已应用', '应用未知', '原始读数未内嵌']) assert.ok(html.includes(value), value)
  assert.ok(!html.includes('认证通过'))
  assert.ok(!html.includes('附件可用'))
})
test('历史无投影不拼当前配置，也不承诺认证/附件', () => {
  const html = render(undefined)
  assert.ok(html.includes('历史追溯未生成'))
  assert.ok(!html.includes('认证通过'))
  assert.ok(!html.includes('附件可用'))
})
test('报告列表入口接通只读报告详情', () => {
  // 接线必须存在；实际点击由隔离真实API浏览器验收覆盖。
  const source = readFileSync('src/features/Reports/pages/ReportsPage.tsx', 'utf8')
  assert.match(source, /<ReportList onView=/)
  assert.match(source, /<ReportViewer reportId=/)
})
test('真实MIMO报告不带虚拟路测数组仍能展示追溯', () => {
  const html = render(trace, { phases: undefined, events: undefined, kpi_summary: undefined })
  assert.ok(html.includes('old-confirmed'))
})
