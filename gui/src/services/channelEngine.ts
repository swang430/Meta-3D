/**
 * ChannelEngine Service Client
 * TypeScript client for the ChannelEngine OTA probe weight calculation service
 */

import type {
  HealthCheckResponse,
  ProbeWeightRequest,
  ProbeWeightResponse,
  ProbePosition,
  ProbeArrayConfig,
  ScenarioConfig,
  MIMOConfig
} from '../types/channelEngine'

/**
 * ChannelEngine服务配置
 */
interface ChannelEngineConfig {
  baseUrl: string
  timeout?: number  // milliseconds
}

/**
 * 默认配置
 */
const DEFAULT_CONFIG: ChannelEngineConfig = {
  baseUrl: 'http://localhost:8000',
  timeout: 30000  // 30 seconds
}

/**
 * ChannelEngine服务客户端类
 */
export class ChannelEngineClient {
  private config: ChannelEngineConfig

  constructor(config?: Partial<ChannelEngineConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config }
  }

  /**
   * 健康检查
   * 检查ChannelEngine服务是否可用
   */
  async healthCheck(): Promise<HealthCheckResponse> {
    const response = await fetch(`${this.config.baseUrl}/api/v1/health`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      },
      signal: AbortSignal.timeout(this.config.timeout || 5000)
    })

    if (!response.ok) {
      throw new Error(`Health check failed: ${response.statusText}`)
    }

    return response.json()
  }

  /**
   * 生成探头权重
   * 基于场景配置和探头阵列，计算OTA测试所需的探头权重
   */
  async generateProbeWeights(
    request: ProbeWeightRequest
  ): Promise<ProbeWeightResponse> {
    const response = await fetch(
      `${this.config.baseUrl}/api/v1/ota/generate-probe-weights`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(request),
        signal: AbortSignal.timeout(this.config.timeout || 30000)
      }
    )

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(
        errorData.detail || `Weight generation failed: ${response.statusText}`
      )
    }

    return response.json()
  }

  /**
   * 检查服务是否可用（简化版）
   * 返回布尔值表示服务是否正常
   */
  async isAvailable(): Promise<boolean> {
    try {
      const health = await this.healthCheck()
      return health.status === 'healthy' && health.channel_engine_available
    } catch {
      return false
    }
  }
}

// ============================================================================
// Helper Functions - 探头阵列生成器
// ============================================================================

/**
 * 生成单环探头阵列（均匀分布）
 * @param numProbes 探头数量
 * @param radius 暗室半径 (meters)
 * @param theta 天顶角 (degrees, 默认90度为水平环)
 * @param polarization 极化方式
 */
export function generateRingProbeArray(
  numProbes: number,
  radius: number,
  theta: number = 90,
  polarization: 'V' | 'H' | 'LHCP' | 'RHCP' = 'V'
): ProbeArrayConfig {
  const positions: ProbePosition[] = []

  for (let i = 0; i < numProbes; i++) {
    const phi = (360 / numProbes) * i
    positions.push({
      probe_id: i + 1,
      theta,
      phi,
      r: radius,
      polarization
    })
  }

  return {
    num_probes: numProbes,
    radius,
    probe_positions: positions
  }
}

/**
 * 生成三环探头阵列（上-中-下三层）
 * @param radius 暗室半径 (meters)
 * @param polarization 极化方式
 */
export function generateThreeRingProbeArray(
  radius: number = 2.5,
  polarization: 'V' | 'H' | 'LHCP' | 'RHCP' = 'V'
): ProbeArrayConfig {
  const positions: ProbePosition[] = []
  let probeId = 1

  // 上层: 8个探头，theta=45度
  const upperTheta = 45
  const upperCount = 8
  for (let i = 0; i < upperCount; i++) {
    positions.push({
      probe_id: probeId++,
      theta: upperTheta,
      phi: (360 / upperCount) * i,
      r: radius,
      polarization
    })
  }

  // 中层: 16个探头，theta=90度（水平）
  const middleTheta = 90
  const middleCount = 16
  for (let i = 0; i < middleCount; i++) {
    positions.push({
      probe_id: probeId++,
      theta: middleTheta,
      phi: (360 / middleCount) * i,
      r: radius,
      polarization
    })
  }

  // 下层: 8个探头，theta=135度
  const lowerTheta = 135
  const lowerCount = 8
  for (let i = 0; i < lowerCount; i++) {
    positions.push({
      probe_id: probeId++,
      theta: lowerTheta,
      phi: (360 / lowerCount) * i,
      r: radius,
      polarization
    })
  }

  return {
    num_probes: 32,
    radius,
    probe_positions: positions
  }
}

/**
 * 将探头位置从球坐标转换为笛卡尔坐标
 * @param probe 探头位置（球坐标）
 * @returns 笛卡尔坐标 {x, y, z}
 */
export function sphericalToCartesian(probe: ProbePosition): {
  x: number
  y: number
  z: number
} {
  const thetaRad = (probe.theta * Math.PI) / 180
  const phiRad = (probe.phi * Math.PI) / 180

  return {
    x: probe.r * Math.sin(thetaRad) * Math.cos(phiRad),
    y: probe.r * Math.sin(thetaRad) * Math.sin(phiRad),
    z: probe.r * Math.cos(thetaRad)
  }
}

/**
 * 将笛卡尔坐标转换为球坐标
 * @param x X坐标
 * @param y Y坐标
 * @param z Z坐标
 * @returns 球坐标 {theta, phi, r}
 */
export function cartesianToSpherical(
  x: number,
  y: number,
  z: number
): {
  theta: number
  phi: number
  r: number
} {
  const r = Math.sqrt(x * x + y * y + z * z)
  const theta = (Math.acos(z / r) * 180) / Math.PI
  let phi = (Math.atan2(y, x) * 180) / Math.PI

  // 确保phi在0-360范围内
  if (phi < 0) phi += 360

  return { theta, phi, r }
}

// ============================================================================
// Singleton Instance
// ============================================================================

/**
 * 默认ChannelEngine客户端实例
 * 可直接导入使用
 */
export const channelEngineClient = new ChannelEngineClient()

// ============================================================================
// Convenience Functions
// ============================================================================

/**
 * 快速生成探头权重（使用默认客户端）
 */
export async function generateProbeWeights(
  scenario: ScenarioConfig,
  probeArray: ProbeArrayConfig,
  mimoConfig: MIMOConfig
): Promise<ProbeWeightResponse> {
  return channelEngineClient.generateProbeWeights({
    scenario,
    probe_array: probeArray,
    mimo_config: mimoConfig
  })
}

/**
 * 快速健康检查（使用默认客户端）
 */
export async function checkChannelEngineHealth(): Promise<HealthCheckResponse> {
  return channelEngineClient.healthCheck()
}

/**
 * 快速可用性检查（使用默认客户端）
 */
export async function isChannelEngineAvailable(): Promise<boolean> {
  return channelEngineClient.isAvailable()
}
