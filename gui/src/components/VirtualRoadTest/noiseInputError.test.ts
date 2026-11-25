import assert from 'node:assert/strict'
import test from 'node:test'
import { noiseInputError } from './noiseInputError.ts'

const rejected = (detail: unknown) => ({
  isAxiosError: true,
  message: 'Request failed with status code 422',
  response: { data: { detail } },
})

test('波形拒绝时显示仪器输入的具体原因', () => {
  assert.equal(noiseInputError(rejected('噪声相关矩阵必须半正定')), '噪声相关矩阵必须半正定')
})

test('预览拒绝时逐项指出窗口编号和字段', () => {
  const fields = [{loc:['body',0,'scope'], msg:'缺少参考面'}, {loc:['body',1,'method'], msg:'缺少生成方式'}]
  assert.equal(noiseInputError(rejected(fields)), '0.scope：缺少参考面；1.method：缺少生成方式')
})

test('本地文件读取失败时保留原始原因', () => {
  assert.equal(noiseInputError(new Error('文件超过大小限制')), '文件超过大小限制')
})
