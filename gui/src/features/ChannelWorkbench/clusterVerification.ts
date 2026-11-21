// 两份文件共享 MPDB、成员表指纹和帧/端口/簇坐标。只核对明确声明的共同分簇规则。
type Id = { frame: number; tx: number; rx: number; cluster: number }
type Row = Record<string, unknown>
function record(value: unknown): Row {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw Error('文件结构无效')
  return value as Row
}
function finite(n: unknown): n is number {
  return typeof n === 'number' && Number.isFinite(n)
}
function sourceKey(doc: Row) {
  const s = doc.source
  if (!s || typeof s !== 'object') return null
  const { mpdb, members } = s as Row
  return [mpdb, members].every(
    (h) => typeof h === 'string' && /^[0-9a-f]{64}$/.test(h),
  )
    ? mpdb + '/' + String(members)
    : null
}
function rows(doc: Row) {
  if (!Array.isArray(doc.rows) || !doc.rows.length) throw Error('缺少簇记录')
  const mapped = new Map<string, { id: Id; row: Row }>()
  for (const value of doc.rows) {
    const row = record(value)
    const { frame, tx, rx, cluster } = row
    if (
      ![frame, tx, rx, cluster].every(
        (n) => Number.isSafeInteger(n) && Number(n) >= 0,
      )
    )
      throw Error('帧、端口或簇编号无效')
    const id = { frame, tx, rx, cluster } as Id
    const key = [frame, tx, rx, cluster].join('/')
    if (mapped.has(key)) throw Error('簇坐标重复：' + key)
    mapped.set(key, { id, row })
  }
  return mapped
}
export function verifyClusters(resultInput: unknown, evidenceInput: unknown) {
  const results = record(resultInput)
  if (results.schema !== 'joint-results/1')
    throw Error('请选择共同分簇结果文件')
  const actual = rows(results)
  const evidence = evidenceInput == null ? null : record(evidenceInput)
  if (evidence && evidence.schema !== 'joint-evidence/1')
    throw Error('成员证据文件格式不符')
  const match =
    !!evidence &&
    sourceKey(results) !== null &&
    sourceKey(results) === sourceKey(evidence)
  const expected = match ? rows(evidence!) : null
  const warnings: { id: Id; message: string }[] = []
  const unverified: { id: Id; reason: string }[] = []
  let checked = 0
  for (const [key, { id, row }] of actual) {
    const e = expected?.get(key)?.row
    if (!e) {
      unverified.push({
        id,
        reason: !evidence
          ? '缺少成员证据'
          : !match
            ? '输入数据或成员表来源未匹配'
            : '缺少该簇的成员记录',
      })
      continue
    }
    const { real, imag, doppler } = row
    const { sumReal, sumImag, sumAbs, count, minHz, maxHz } = e
    const missing = []
    if (
      finite(real) &&
      finite(imag) &&
      finite(sumReal) &&
      finite(sumImag) &&
      finite(sumAbs) &&
      sumAbs >= 0 &&
      finite(count) &&
      Number.isSafeInteger(count) &&
      count > 0
    ) {
      // 浮点累加绝对误差随成员数和成员幅度之和增大；保留相干相消。
      const tol = 8 * Number.EPSILON * count * sumAbs
      if (Math.hypot(sumReal, sumImag) > sumAbs + tol)
        missing.push('成员复数和超过成员幅度总和，证据矛盾')
      else if (Math.hypot(real - sumReal, imag - sumImag) > tol)
        warnings.push({
          id,
          message: `复系数为 (${real}, ${imag})，成员相加为 (${sumReal}, ${sumImag})，允许的舍入差为 ${tol}。`,
        })
    } else missing.push('复系数或成员幅度统计不全')
    if (
      finite(doppler) &&
      finite(minHz) &&
      finite(maxHz) &&
      minHz <= maxHz &&
      finite(count) &&
      Number.isSafeInteger(count) &&
      count > 0
    ) {
      const tol =
        8 * Number.EPSILON * count * Math.max(Math.abs(minHz), Math.abs(maxHz))
      if (doppler < minHz - tol || doppler > maxHz + tol)
        warnings.push({
          id,
          message: `代表多普勒为 ${doppler} Hz，成员范围为 ${minHz} 至 ${maxHz} Hz。`,
        })
    } else missing.push('代表多普勒或成员频移范围不全')
    if (missing.length) unverified.push({ id, reason: missing.join('；') })
    else checked++
  }
  if (expected)
    for (const [key, { id }] of expected)
      if (!actual.has(key))
        warnings.push({ id, message: '对应成员记录存在，结果文件缺少该簇。' })
  return { checked, unknown: unverified.length, unverified, warnings }
}
