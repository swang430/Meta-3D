import assert from 'node:assert/strict'
import test from 'node:test'
import { readBudget, budgetLink } from './budget.ts'
import fs from 'node:fs'
const raw = JSON.parse(fs.readFileSync(process.env.BUDGET_FIXTURE || '/private/tmp/p2109-api-real/response.json','utf8'))
test('六组真实离线结果保留稀疏实际使用和局部变差', () => {
 const r = readBudget(raw)
 assert.equal(r.summary['shared-26'].used_taps_min,24)
 assert.equal(r.summary['independent-31'].used_taps_min,28)
 assert.equal(r.summary['shared-26'].worse,9223)
 assert.equal(r.source_frame_count,38)
})
test('拒绝正式通过、错组、缺失数值、异常计数及跨源下载', () => {
 for(const change of [{formal_verdict:'pass'},{simulated:true},{frame_ids:[0]},{tap_budgets:[24,26]},{summary:{...raw.summary,'shared-26':{...raw.summary['shared-26'],worse:-1}}},{summary:{...raw.summary,'shared-26':{...raw.summary['shared-26'],matrix_nmse_median:undefined}}}]) assert.throws(()=>readBudget({...raw,...change}))
 assert.throws(()=>budgetLink('https://example.com/report.zip'))
 assert.equal(budgetLink(raw.points_url),raw.points_url)
 const r=readBudget({...raw,summary:{...raw.summary,'shared-26':{...raw.summary['shared-26'],matrix_nmse_median:null}}})
 assert.equal(r.summary['shared-26'].matrix_nmse_median,null)
})
