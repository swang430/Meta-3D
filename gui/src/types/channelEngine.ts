/**
 * ChannelEngine API Types
 * TypeScript definitions for the ChannelEngine OTA probe weight calculation service
 * Corresponds to Python Pydantic models in channel-engine-service/app/models/ota_models.py
 */

// ============================================================================
// Request Types
// ============================================================================

/**
 * 探头物理位置（球坐标系）
 */
export interface ProbePosition {
  probe_id: number            // 探头ID (1-based)
  theta: number               // 天顶角 (degrees, 0-180)
  phi: number                 // 方位角 (degrees, 0-360)
  r: number                   // 半径 (meters)
  polarization: 'V' | 'H' | 'LHCP' | 'RHCP' | 'VH'  // 极化方式
}

/**
 * 探头阵列配置
 */
export interface ProbeArrayConfig {
  num_probes: number          // 探头数量 (8-64)
  radius: number              // 暗室半径 (meters)
  probe_positions: ProbePosition[]  // 所有探头位置
}

/**
 * 3GPP 场景类型
 */
export type ScenarioType = 'UMa' | 'UMi' | 'RMa' | 'InH'

/**
 * 簇模型类型
 */
export type ClusterModel =
  | 'CDL-A' | 'CDL-B' | 'CDL-C' | 'CDL-D' | 'CDL-E'  // CDL models
  | 'TDL-A' | 'TDL-B' | 'TDL-C'                      // TDL models

/**
 * 测试场景配置
 */
export interface ScenarioConfig {
  scenario_type: ScenarioType     // 3GPP环境类型
  cluster_model?: ClusterModel    // 簇模型（可选，用于混合模型）
  frequency_mhz: number           // 中心频率 (MHz)
  use_median_lsps?: boolean       // 是否使用中值LSP（确定性测试）
}

/**
 * MIMO配置
 */
export interface MIMOConfig {
  num_tx_antennas: number         // 发射天线数 (1-8)
  num_rx_antennas: number         // 接收天线数 (1-8)
  tx_antenna_spacing?: number     // 发射天线间距（波长，默认0.5）
  rx_antenna_spacing?: number     // 接收天线间距（波长，默认0.5）
}

/**
 * 探头权重计算请求
 */
export interface ProbeWeightRequest {
  scenario: ScenarioConfig
  probe_array: ProbeArrayConfig
  mimo_config: MIMOConfig
}

// ============================================================================
// Response Types
// ============================================================================

/**
 * 复数权重（幅度 + 相位）
 */
export interface ComplexWeight {
  magnitude: number    // 幅度 (0-1)
  phase_deg: number    // 相位 (degrees, 0-360)
}

/**
 * 单个探头的权重
 */
export interface ProbeWeight {
  probe_id: number
  polarization: string
  weight: ComplexWeight
  enabled: boolean
}

/**
 * 信道统计信息
 */
export interface ChannelStatistics {
  pathloss_db: number                 // 路径损耗 (dB)
  rms_delay_spread_ns?: number        // RMS时延扩展 (ns)
  angular_spread_deg?: number         // 角度扩展 (degrees)
  condition?: string                  // 信道条件 (LOS/NLOS)
  num_clusters: number                // 簇数量
}

/**
 * 探头权重计算响应
 */
export interface ProbeWeightResponse {
  probe_weights: ProbeWeight[]
  channel_statistics: ChannelStatistics
  success: boolean
  message?: string
}

/**
 * 健康检查响应
 */
export interface HealthCheckResponse {
  status: string                      // 服务状态
  version: string                     // 服务版本
  channel_engine_available: boolean   // ChannelEngine是否可用
}

// ============================================================================
// Helper Types for UI
// ============================================================================

/**
 * 探头配置模板（用于UI快速选择）
 */
export interface ProbeArrayTemplate {
  id: string
  name: string
  description: string
  num_probes: number
  radius: number
  layout: 'ring' | 'multi-ring' | 'custom'
}

/**
 * 预定义探头阵列模板
 */
export const PROBE_ARRAY_TEMPLATES: ProbeArrayTemplate[] = [
  {
    id: '8-probe-ring',
    name: '8探头单环',
    description: '8个探头均匀分布在水平环上（双极化）',
    num_probes: 8,
    radius: 3.0,
    layout: 'ring'
  },
  {
    id: '16-probe-ring',
    name: '16探头单环',
    description: '16个探头均匀分布在水平环上（双极化）',
    num_probes: 16,
    radius: 3.0,
    layout: 'ring'
  },
  {
    id: '32-probe-3ring',
    name: '32探头三环',
    description: '32个探头分布在3层环上（上8+中16+下8）',
    num_probes: 32,
    radius: 2.5,
    layout: 'multi-ring'
  }
]

/**
 * 场景配置预设
 */
export interface ScenarioPreset {
  id: string
  name: string
  description: string
  config: ScenarioConfig
}

/**
 * 预定义场景配置
 */
export const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    id: 'uma-cdl-c',
    name: 'UMa + CDL-C',
    description: '城市宏蜂窝 + CDL-C簇模型（NLOS）',
    config: {
      scenario_type: 'UMa',
      cluster_model: 'CDL-C',
      frequency_mhz: 3500,
      use_median_lsps: false
    }
  },
  {
    id: 'umi-cdl-a',
    name: 'UMi + CDL-A',
    description: '城市微蜂窝 + CDL-A簇模型（LOS）',
    config: {
      scenario_type: 'UMi',
      cluster_model: 'CDL-A',
      frequency_mhz: 3500,
      use_median_lsps: false
    }
  },
  {
    id: 'inh-tdl-a',
    name: 'InH + TDL-A',
    description: '室内热点 + TDL-A簇模型',
    config: {
      scenario_type: 'InH',
      cluster_model: 'TDL-A',
      frequency_mhz: 3500,
      use_median_lsps: false
    }
  }
]
