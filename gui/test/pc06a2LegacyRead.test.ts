import test from 'node:test';
import assert from 'node:assert/strict';
import MockAdapter from 'axios-mock-adapter';
import calibrationClient from '../src/api/calibrationClient';
import { listLegacyCalibrations, listLegacyCertificates, getLegacyCertificate,
  legacyNumber, legacyVerdict } from '../src/api/systemCalibrationReadService';

// 错用固定数组、吞掉读取失败、接受伪envelope或把null当0均应失败。
test('真实数组契约、skip分页与失败不fallback', async () => {
  const mock = new MockAdapter(calibrationClient);
  try {
    mock.onGet('/calibration/trp', { params: { skip: 20, limit: 20 } }).reply(200, []);
    assert.deepEqual(await listLegacyCalibrations('trp', 20, 20), []);
    mock.onGet('/calibration/certificate', { params: { skip: 0, limit: 20 } }).reply(200, []);
    assert.deepEqual(await listLegacyCertificates(), []);
    mock.onGet('/calibration/tis').reply(503, { detail: '不可用' });
    await assert.rejects(listLegacyCalibrations('tis'));
    mock.onGet('/calibration/repeatability').reply(200, { items: [] });
    await assert.rejects(listLegacyCalibrations('repeatability'), /数组/);
    mock.onGet('/calibration/certificate/requested').reply(200, { id: 'another' });
    await assert.rejects(getLegacyCertificate('requested'), /不一致/);
    assert.equal(mock.history.post.length, 0);
    assert.equal(legacyNumber(null, 'dBm'), '未知');
    assert.equal(legacyNumber(undefined, 'dBm'), '未知');
    assert.equal(legacyNumber(Number.NaN, 'dBm'), '未知');
    assert.equal(legacyNumber(0, 'dBm'), '0.00 dBm');
    assert.equal(legacyVerdict(null), '原记录：未知');
    assert.equal(legacyVerdict(false), '原记录：未通过');
    assert.equal(legacyVerdict(true), '原记录：通过');
  } finally { mock.restore(); }
});

test('原字段和编码后的所选证书ID不改写', async () => {
  const mock = new MockAdapter(calibrationClient);
  try {
    const row = { id: 'legacy-r', tested_at: '2026-10-26', validation_pass: null,
      test_type: 'execution_metrics', mean_dbm: null, metric_deltas: {} };
    mock.onGet('/calibration/repeatability', { params: { skip: 0, limit: 20 } }).reply(200, [row]);
    assert.deepEqual(await listLegacyCalibrations('repeatability'), [row]);
    const certificate = { id: 'a/b', certificate_number: 'original', overall_pass: false };
    mock.onGet('/calibration/certificate/a%2Fb').reply(200, certificate);
    assert.deepEqual(await getLegacyCertificate('a/b'), certificate);
    mock.onGet('/calibration/certificate/missing').reply(404);
    await assert.rejects(getLegacyCertificate('missing'));
    mock.onGet('/calibration/certificate').reply(200, { items: [] });
    await assert.rejects(listLegacyCertificates(), /数组/);
  } finally { mock.restore(); }
});
