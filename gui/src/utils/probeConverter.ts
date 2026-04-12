/**
 * Probe Coordinate Converter
 *
 * 在 API Service 的探头坐标系 (azimuth/elevation) 和
 * Channel Engine 的坐标系 (theta/phi) 之间进行转换。
 *
 * API Service:  azimuth (0-360°), elevation (-90°~90°), radius (m)
 * Channel Engine: theta (0-180° 天顶角), phi (0-360° 方位角), r (m)
 *
 * 转换关系:
 *   theta = 90 - elevation
 *   phi = azimuth
 *   elevation = 90 - theta
 *   azimuth = phi
 */

import type { Probe } from '../types/api'
import type { ProbeArrayConfig, ProbePosition as CEProbePosition } from '../types/channelEngine'

/**
 * 将 API Service 的探头坐标转换为 Channel Engine 的 ProbePosition
 */
export function dbProbeToChannelEnginePosition(
  probe: Probe,
  probeId: number
): CEProbePosition {
  const { azimuth, elevation, radius } = probe.position

  return {
    probe_id: probeId,
    theta: 90 - elevation,  // elevation → 天顶角
    phi: azimuth,            // azimuth 保持不变
    r: radius,
    polarization: probe.polarization as 'V' | 'H' | 'LHCP' | 'RHCP' | 'VH',
  }
}

/**
 * 将数据库中的探头列表批量转换为 Channel Engine 的 ProbeArrayConfig
 *
 * @param probes - 从 DB 获取的探头列表
 * @param chamberRadius - 暗室半径 (m)，用作 ProbeArrayConfig 的 radius 字段
 * @returns ProbeArrayConfig 可直接传给 Channel Engine
 */
export function dbProbesToProbeArrayConfig(
  probes: Probe[],
  chamberRadius: number
): ProbeArrayConfig {
  const probePositions = probes
    .filter((p) => p.is_active) // 只使用启用的探头
    .map((probe, index) => dbProbeToChannelEnginePosition(probe, index + 1))

  return {
    num_probes: probePositions.length,
    radius: chamberRadius,
    probe_positions: probePositions,
  }
}

/**
 * 将 Channel Engine 的天顶角转换回 API Service 的仰角
 */
export function thetaToElevation(theta: number): number {
  return 90 - theta
}

/**
 * 将 API Service 的仰角转换为 Channel Engine 的天顶角
 */
export function elevationToTheta(elevation: number): number {
  return 90 - elevation
}

/**
 * 验证探头位置是否在暗室范围内
 */
export function validateProbeInChamber(
  probe: Probe,
  chamberRadius: number
): { valid: boolean; message?: string } {
  const { radius } = probe.position
  const tolerance = 0.01 // 1cm 容差

  if (Math.abs(radius - chamberRadius) > tolerance) {
    return {
      valid: false,
      message: `探头 ${probe.probe_number} 的半径 (${radius}m) 与暗室半径 (${chamberRadius}m) 不一致`,
    }
  }

  return { valid: true }
}
