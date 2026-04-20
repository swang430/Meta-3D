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
  cable_length_m?: number;
  calibrated_loss_db?: number | null;
  calibrated_phase_deg?: number | null;
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
  async getTopologies(categoryId?: string) {
    let url = '/switch-topologies';
    if (categoryId) {
      url += `?switch_category_id=${categoryId}`;
    }
    const response = await apiClient.get(url);
    return response.data;
  },

  async getTopology(id: string) {
    const response = await apiClient.get(`/switch-topologies/${id}`);
    return response.data;
  },

  async updateTopology(id: string, data: Partial<SwitchTopology>) {
    const response = await apiClient.patch(`/switch-topologies/${id}`, data);
    return response.data;
  },

  async importCaictDefault(switchCategoryId: string) {
    const response = await apiClient.post(`/switch-topologies/import/caict-default?switch_category_id=${switchCategoryId}`);
    return response.data;
  },
  
  async validateTopology(id: string) {
    const response = await apiClient.get(`/switch-topologies/${id}/validate`);
    return response.data;
  }
};
