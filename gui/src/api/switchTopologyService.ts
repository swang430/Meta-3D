import apiClient from './client';

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
// 应用层接线声明，不代表已核验硬件能力；缺键保持缺失，unknown不等于双向。
export type TopologyPortDirection = 'input' | 'output' | 'bidirectional' | 'unknown';
export type TopologyPortDirections = Record<string, TopologyPortDirection>;
// 有向白名单；缺键与[]不同，不携带增益/损耗或开关位置，不证明物理导通。
export type TopologyInternalPath = { from_port: string; to_port: string };
export type ConnectionNumericField = 'cable_loss_db' | 'cable_length_m' | 'calibrated_loss_db' | 'calibrated_phase_deg';
export type ConnectionNumericDeclarations = Record<string, ConnectionNumericField[]>;
export type TopologyUpdatePayload = Partial<SwitchTopology> & {
  connection_numeric_declarations?: ConnectionNumericDeclarations;
  conversion?: { source_digest: string; changes: TopologyConversionRequest };
};

export interface ConversionNodeEdit {
  node_id: string;
  target_type?: 'ce_port' | 'channel_emulator' | 'bse_port' | 'communication_tester' | 'sa_port' | 'signal_analyzer';
  ports?: string[];
  port_directions?: TopologyPortDirections;
  port_roles?: Record<string, 'dl' | 'ul'>;
  internal_paths?: TopologyInternalPath[];
  ce_port?: string;
}
export interface ConversionConnectionEdit {
  connection_id: string;
  source_pin?: string;
  target_pin?: string;
  cable_loss_db?: number | null;
  loss_owner_connection_id?: string | null;
  same_physical_cable_confirmed?: boolean;
}
export interface TopologyConversionRequest {
  nodes?: ConversionNodeEdit[];
  connections?: ConversionConnectionEdit[];
}
export interface TopologyConversionPreview {
  source_digest: string;
  changes: TopologyConversionRequest;
  // 原保存JSON，可能缺position/pin或保留旧数值字符串，不能冒充GET默认化模型。
  candidate: { nodes: Record<string, JsonValue>[]; connections: Record<string, JsonValue>[];
    operating_modes: Record<string, JsonValue>[] };
  differences: { object_kind: string; object_id: string; field: string; before_present: boolean;
    before?: JsonValue; after: JsonValue }[];
  warnings: string[];
}

export function mergeConnectionDeclarations(current: ConnectionNumericDeclarations, id: string,
  fields: ConnectionNumericField[]): ConnectionNumericDeclarations {
  return fields.length ? {...current,[id]:[...new Set([...(current[id]??[]),...fields])]} : current;
}

export function topologyUpdatePayload(draft: SwitchTopology,
  declarations: ConnectionNumericDeclarations): TopologyUpdatePayload {
  const live=new Set(draft.connections.map(edge=>edge.id));
  const kept=Object.fromEntries(Object.entries(declarations).filter(([id,fields])=>live.has(id)&&fields.length));
  return {nodes:draft.nodes, connections:draft.connections, operating_modes:draft.operating_modes,
    ...(Object.keys(kept).length?{connection_numeric_declarations:kept}:{})};
}

export interface TopologyNode {
  id: string;
  type: string;
  label: string;
  position: { x: number; y: number };
  params: Record<string, any>;
}

export interface TopologyConnection {
  id: string;
  source: string;
  source_pin?: string;
  target: string;
  target_pin?: string;
  cable_type?: string;
  cable_loss_db?: number | null;
  loss_owner_connection_id?: string;
  pa_gain_db?: JsonValue;
  nominal_metadata?: JsonValue;
  ce_port?: string;
  switch_port?: string;
  cable_length_m?: number;
  calibrated_loss_db?: number | null;
  calibrated_phase_deg?: number | null;
  direction?: 'DL' | 'UL' | 'Bi-Di';
  modes?: string[];
}

export interface OperatingMode {
  id: string;
  name: string;
  description?: string;
  active_connections?: string[];
  required_instruments?: string[];
  color?: string;
}

export interface SwitchTopology {
  id?: string;
  switch_category_id: string;
  chamber_id?: string | null;
  name: string;
  description?: string;
  version?: string;
  site_name?: string;
  system_model?: string;
  installed_date?: string;
  installed_by?: string;
  is_active: boolean;
  is_default: boolean;
  nodes: TopologyNode[];
  connections: TopologyConnection[];
  operating_modes: OperatingMode[];
  
  // Computed fields from backend
  total_nodes?: number;
  total_connections?: number;
  total_probes?: number;
  total_channels?: number;
  created_at?: string;
}

export const switchTopologyService = {
  // P1-57：每个数据方法都携带 lab_profile_id —— 后端由它派生暗室，
  // 不再相信客户端自由提交的 chamber_id（那正是"拓扑写进错暗室"的口子）。

  async getTopologies(labProfileId: string, categoryId?: string, skip = 0, limit = 100): Promise<{items: SwitchTopology[]; total: number}> {
    const params = new URLSearchParams({ lab_profile_id: labProfileId, skip: String(skip), limit: String(limit) });
    if (categoryId) params.append('switch_category_id', categoryId);
    const response = await apiClient.get(`/switch-topologies?${params.toString()}`);
    return response.data;
  },

  async getTopology(id: string, labProfileId: string) {
    const response = await apiClient.get(`/switch-topologies/${id}`, {
      params: { lab_profile_id: labProfileId },
    });
    return response.data;
  },

  async copyTopology(id: string, labProfileId: string, name: string): Promise<SwitchTopology> {
    const response = await apiClient.post(`/switch-topologies/${id}/copy`, {name}, {
      params: {lab_profile_id: labProfileId},
    });
    return response.data;
  },

  async updateTopology(id: string, labProfileId: string, data: TopologyUpdatePayload) {
    const response = await apiClient.patch(`/switch-topologies/${id}`, data, {
      params: { lab_profile_id: labProfileId },
    });
    return response.data;
  },

  async previewConversion(id: string, labProfileId: string, changes: TopologyConversionRequest): Promise<TopologyConversionPreview> {
    const response = await apiClient.post(`/switch-topologies/${id}/conversion-preview`, changes, {
      params: { lab_profile_id: labProfileId },
    });
    return response.data;
  },

  async listTemplates(): Promise<string[]> {
    const response = await apiClient.get('/switch-topologies/templates');
    return response.data;
  },

  async importFromTemplate(
    switchCategoryId: string,
    labProfileId: string,
    templateId: string,
    replaceExisting = false,
  ) {
    // 仅显式追加inactive副本；已有行时服务端拒绝replace_existing=true。
    const params = new URLSearchParams({
      switch_category_id: switchCategoryId,
      lab_profile_id: labProfileId,
      template_id: templateId,
      replace_existing: String(replaceExisting),
    });
    const response = await apiClient.post(
      `/switch-topologies/import/from-template?${params.toString()}`
    );
    return response.data;
  },

  async validateTopology(id: string, labProfileId: string) {
    const response = await apiClient.get(`/switch-topologies/${id}/validate`, {
      params: { lab_profile_id: labProfileId },
    });
    return response.data;
  }
};
