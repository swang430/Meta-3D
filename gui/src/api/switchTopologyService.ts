import apiClient from './client';

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
  cable_loss_db?: number;
  pa_gain_db?: number;
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

  async getTopologies(labProfileId: string, categoryId?: string) {
    const params = new URLSearchParams({ lab_profile_id: labProfileId });
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

  async updateTopology(id: string, labProfileId: string, data: Partial<SwitchTopology>) {
    const response = await apiClient.patch(`/switch-topologies/${id}`, data, {
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
    // replace_existing=true 时由服务端先完整解析 lab/暗室/模板、成功后才
    // 删除同 (switch, 派生暗室) 的旧行 —— 取代原来 GUI 的先删后导。
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
