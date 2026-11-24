import assert from 'node:assert/strict'
import test from 'node:test'
import { comparisonParameters, metric, downloadLink } from './comparison.ts'
test('拒绝非奇数点数和非有限或非正参数', () => {
  for (const v of [[100,40,1e-8],[0,41,1e-8],[100,41,NaN],[100,259,1e-8]])
    assert.throws(() => comparisonParameters(...v as [number,number,number]))
  assert.deepEqual(comparisonParameters(100,41,1e-8), {bandwidth_mhz:100,points:41,amplitude_floor:1e-8})
})
test('无有效数值不可显示为零，下载地址不得重加前缀或跨源', () => {
  assert.equal(metric(null), '无有效点')
  assert.equal(metric(0), '0')
  assert.equal(downloadLink('/api/v1/channel-assets/mpdb-projects/comparisons/abc/points.csv'), '/api/v1/channel-assets/mpdb-projects/comparisons/abc/points.csv')
  assert.throws(() => downloadLink('https://evil.example/points.csv'))
})

test('保留38帧中末帧37未配对且拒绝正式通过或缺失证据', async () => {
  const { readComparison } = await import('./comparison.ts')
  const raw = {
    schema:'mpdb-comparison/1', status:'partial', formal_verdict:null,
    alignment_status:'unverified', simulated:false, hardware_verified:false,
    source_frame_count:38, unmatched_source_frames:[37],
    coverage:{phase_valid:37,phase_total:38,phase_fraction:37/38,matrix_valid:37,matrix_total:38,matrix_fraction:37/38},
    summary:{Lauraycs:{matrix_nmse_median:null,matrix_nmse_p95:null,phase_error_p95_deg:null},'Meta-3D':{matrix_nmse_median:0,matrix_nmse_p95:0,phase_error_p95_deg:0}},
    source:{},message:'未核验',member_row_order:'源行序',polarization_basis:{},
    download_url:'/api/v1/channel-assets/mpdb-projects/comparisons/abc/report.zip',points_url:'/api/v1/channel-assets/mpdb-projects/comparisons/abc/points.csv',
  }
  const result = readComparison(raw as Parameters<typeof readComparison>[0])
  assert.equal(result.source_frame_count-result.unmatched_source_frames.length,37)
  assert.deepEqual(result.unmatched_source_frames,[37])
  for (const change of [{formal_verdict:'pass'},{hardware_verified:true},{coverage:null},{alignment_status:'verified'}])
    assert.throws(() => readComparison({...raw,...change} as Parameters<typeof readComparison>[0]))
})
