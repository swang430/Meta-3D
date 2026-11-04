import { getDraftModeConnectionIds } from './topologyDraft'
import type { SwitchTopology, TopologyNode } from '../../api/switchTopologyService'
import type { HALReadinessResponse, InstrumentCategory } from '../../types/api'

export const calibrationNodeTypes = new Set(['reference_antenna', 'signal_analyzer', 'sa_port', 'vna', 'signal_generator', 'receive_cable', 'air_path'])

/** 显示原图的校准声明，不创建连接，也不把声明变成可执行路线。 */
export function calibrationCanvasConnections(graph: SwitchTopology, normal: string[], visible: boolean) {
  if (!visible) return normal
  return [...new Set([...normal, ...getDraftModeConnectionIds(graph, 'calibration')])]
}

export function calibrationNodeVisible(node: TopologyNode, visible: boolean) {
  return visible && (calibrationNodeTypes.has(node.type) || node.params.connection_scope === 'calibration')
}

export function instrumentPresentation(node: TopologyNode, categories: InstrumentCategory[], report: HALReadinessResponse | undefined, labId: string) {
  const category = categories.find(row => row.categoryId === node.params.instrument_category_id)
  if (!category) return { resource: '未关联仪器资源', snapshot: '运行状态未知', binding: '执行绑定未核对' }
  const model = category.models.find(row => row.id === category.selectedModelId)
  const resource = `${category.label} · ${model?.model ?? '未选型号'} · ${category.isActive === false ? '已停用' : '已配置'} · 配置模式 ${category.driverMode}`
  if (!report || report.lab_profile.profile_id !== labId) return { resource, snapshot: '运行状态未知', binding: '执行绑定未核对' }
  const row = report.drivers.find(driver => driver.category === category.key)
  const binding = category.key === 'channelEmulator' ? report.channel_emulator_binding
    : category.key === 'baseStation' ? report.base_station_binding : null
  // 分类快照不是实时探测；不得按名字或配置模式推断实际模拟驱动。
  return { resource, snapshot: row ? `HAL快照：${row.status} · ${row.model} · ${row.detail}` : '未返回该类别运行快照',
    binding: binding?.lab_profile_id === labId && binding.category_id === category.categoryId
      ? `本实验室绑定：${binding.status} · ${binding.execution_mode === 'simulated' ? '模拟' : binding.execution_mode === 'real' ? '真实模式声明' : '模式未知'} · ${binding.detail}`
      : '未提供本仪器的实验室绑定核验；启动仍由服务器检查' }
}
