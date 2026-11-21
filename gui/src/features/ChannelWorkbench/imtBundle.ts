export type Mode = 'conducted' | 'ota'
export type Metric = {
  frame: number
  tx: number
  offset_hz: number
  field_nmse: number | null
  power_ratio: number | null
}
type Link = { tx: number; destination: string; file: string; sha256: string }

function record(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v))
    throw Error('工程清单格式不正确')
  return v as Record<string, unknown>
}
function positive(v: unknown): number {
  if (typeof v !== 'number' || !Number.isFinite(v) || v <= 0)
    throw Error('文件头中的数量、载频或更新率无效')
  return v
}
function integer(v: unknown, max: number): number {
  if (typeof v !== 'number' || !Number.isSafeInteger(v) || v < 0 || v >= max)
    throw Error('端口或帧编号超出范围')
  return v
}
function measurement(v: unknown): number | null {
  if (v === null) return null
  if (typeof v !== 'number' || !Number.isFinite(v) || v < 0)
    throw Error('离线误差数据无效')
  return v
}
export function readBundle(input: unknown, mode: Mode) {
  const m = record(input)
  if (m.hardware_verified !== false || m.smu_built !== false)
    throw Error('此处仅支持离线生成的输入包')
  if (m.mode !== mode || m.direction !== 'downlink')
    throw Error('清单的测试方式或上下行方向与所选方式不符')
  const ota = mode === 'ota'
  if (
    m.evidence !== (ota ? 'offline_ideal_plane_wave' : 'offline_asc_validation')
  )
    throw Error('无法识别工程来源')
  const h = record(m.header),
    frames = positive(h.cir_count),
    taps = positive(h.taps)
  if (!Number.isSafeInteger(frames) || !Number.isSafeInteger(taps))
    throw Error('行数和抽头数必须为整数')
  const rate = positive(h.rate_hz),
    carrier = positive(h.carrier_hz)
  const probes = ota ? record(m.geometry).probe_azimuth_zenith_deg : null
  if (
    ota &&
    (!Array.isArray(probes) ||
      !probes.length ||
      probes.length > 16 ||
      m.source_frames_only !== true)
  )
    throw Error('探头配置或源帧说明缺失')
  const n = Array.isArray(probes) ? probes.length : 0
  if (!Array.isArray(m.links) || m.links.length !== (ota ? 8 * n : 8))
    throw Error('清单的端口数量不完整')
  const links: Link[] = m.links.map((item) => {
    const e = record(item),
      tx = integer(e.tx, 4)
    if (
      typeof e.file !== 'string' ||
      !/^[-\w.]+\.asc$/.test(e.file) ||
      typeof e.sha256 !== 'string' ||
      !/^[a-f0-9]{64}$/.test(e.sha256)
    )
      throw Error('文件名或文件校验值无效')
    let destination: string
    if (ota) {
      if (e.polarization !== 'theta' && e.polarization !== 'phi')
        throw Error('探头极化无效')
      destination = '探头 ' + integer(e.probe, n) + ' · ' + e.polarization
    } else destination = 'RX' + integer(e.rx, 2)
    const expected = ota
      ? `TX${tx}_PROBE${String(e.probe).padStart(2, '0')}_${e.polarization}.asc`
      : `R0B0S0D_TX${tx}_RX${e.rx}_H.asc`
    if (e.file !== expected) throw Error('清单端口与实际文件名不符：' + e.file)
    return { tx, destination, file: e.file, sha256: e.sha256 }
  })
  if (
    new Set(links.map((l) => l.file)).size !== links.length ||
    new Set(links.map((l) => l.tx + '/' + l.destination)).size !== links.length
  )
    throw Error('端口或文件重复')
  const metrics: Metric[] = []
  if (ota) {
    if (!Array.isArray(m.metrics) || m.metrics.length !== frames * 4 * 3)
      throw Error('逐帧场误差或功率对照缺失')
    for (const item of m.metrics) {
      const r = record(item),
        offset = r.offset_hz
      if (typeof offset !== 'number' || ![-50e6, 0, 50e6].includes(offset))
        throw Error('频偏无效')
      metrics.push({
        frame: integer(r.frame, frames),
        tx: integer(r.tx, 4),
        offset_hz: offset,
        field_nmse: measurement(r.field_nmse),
        power_ratio: measurement(r.power_ratio),
      })
    }
    if (
      new Set(metrics.map((r) => [r.tx, r.frame, r.offset_hz].join('/')))
        .size !== metrics.length
    )
      throw Error('逐帧误差记录重复')
  }
  return {
    links,
    metrics,
    frames,
    taps,
    rate,
    carrier,
    txMode: typeof m.tx_mode === 'string' ? m.tx_mode : '未记录',
    referenceRx: Number.isSafeInteger(m.reference_rx)
      ? String(m.reference_rx)
      : '未记录',
    rateSource:
      m.rate_source === 'operator_supplied' ? '操作人员指定' : '未记录',
  }
}

export function verifyHeader(
  text: string,
  expected: ReturnType<typeof readBundle>,
  file: string,
) {
  const lines = text.split(/\r?\n/),
    end = lines.indexOf('***** Tap data *****')
  if (lines[0] !== '***** Header *****' || end < 1)
    throw Error('无法识别文件头：' + file)
  for (const [key, value] of Object.entries({
    CIRs: expected.frames,
    'Taps/CIR': expected.taps,
    Carrier_Frequency: expected.carrier,
    CIR_Update_Rate: expected.rate,
  })) {
    const hits = lines
      .slice(1, end)
      .map((l) => l.trim().split(/\s+/))
      .filter((parts) => parts.length === 2 && parts[1] === key)
    if (hits.length !== 1 || Number(hits[0][0]) !== value)
      throw Error('文件头与清单不符：' + file + ' · ' + key)
  }
}
