/**
 * Report Management Types
 *
 * TypeScript interfaces for the report generation and template management system
 *
 * @version 1.0.0
 * @date 2025-11-26
 */

// ==================== Report Types ====================

export type ReportStatus = 'pending' | 'generating' | 'completed' | 'failed'
export type ReportFormat = 'pdf' | 'html' | 'excel'
export type ReportType =
  | 'single_execution'
  | 'multi_execution'
  | 'comparison'
  | 'summary'
  | 'regulatory'

export interface TestReport {
  id: string
  title: string
  description?: string
  report_type: ReportType
  format: ReportFormat
  status: ReportStatus
  progress_percent: number

  // Associated data
  test_plan_id?: string
  test_execution_ids?: string[]
  comparison_plan_ids?: string[]
  template_id?: string

  // File info
  file_path?: string
  file_size_bytes?: number
  page_count?: number
  section_count?: number
  chart_count?: number
  table_count?: number

  // Generation options
  include_raw_data: boolean
  include_charts: boolean
  include_statistics: boolean
  include_recommendations: boolean
  config?: Record<string, any>
  custom_sections?: any[]

  // Timestamps
  generation_started_at?: string
  generation_completed_at?: string
  generation_duration_sec?: number
  generated_by: string
  generated_at: string

  // Error handling
  error_message?: string
  error_details?: Record<string, any>

  // Metadata
  version?: string
  tags?: string[]
  category?: string
  notes?: string
}

export interface ReportSummary {
  id: string
  title: string
  report_type: ReportType
  format: ReportFormat
  status: ReportStatus
  generated_by: string
  generated_at: string
  file_size_bytes?: number
}

export interface ReportListResponse {
  reports: ReportSummary[]
  total: number
  page: number
  page_size: number
}

export interface CreateReportRequest {
  title: string
  report_type: ReportType
  format: ReportFormat
  generated_by: string
  description?: string
  test_plan_id?: string
  test_execution_ids?: string[]
  comparison_plan_ids?: string[]
  road_test_execution_id?: string  // VRT execution ID
  template_id?: string
  include_raw_data?: boolean
  include_charts?: boolean
  include_statistics?: boolean
  include_recommendations?: boolean
  config?: Record<string, any>
  custom_sections?: any[]
  tags?: string[]
  category?: string
  notes?: string
  // VRT report content data (passed directly to backend for immediate generation)
  content_data?: Record<string, any>
}

export interface UpdateReportRequest {
  title?: string
  description?: string
  tags?: string[]
  category?: string
  notes?: string
}

export interface ReportListFilters {
  report_type?: ReportType
  status?: ReportStatus
  generated_by?: string
  skip?: number
  limit?: number
}

// ==================== Template Types ====================

export type TemplateType = 'standard' | 'regulatory' | 'performance' | 'comparison' | 'executive' | 'custom'

export interface SectionConfig {
  id: string
  title: string
  order: number
  type:
    | 'cover'
    | 'text'
    | 'table'
    | 'mixed'
    | 'charts'
    | 'execution_summary'
    | 'statistics'
    | 'time_series'
    | 'logs'
    | 'step_details'
    // VRT specific section types
    | 'vrt_scenario'
    | 'vrt_kpi_summary'
    | 'vrt_phases'
    | 'vrt_trajectory'
    | 'vrt_network_config'
    | 'vrt_events'
  required: boolean
  fields?: string[]
  content_template?: string
  include_charts?: boolean
  include_tables?: boolean
  page_break_after?: boolean
  max_entries?: number
}

export interface ChartConfig {
  type: 'line' | 'bar' | 'scatter' | 'heatmap' | 'grouped_bar'
  title?: string
  x_axis?: { label: string }
  y_axis?: { label: string }
  colors?: string[]
  series_labels?: string[]
  [key: string]: any
}

export interface TableConfig {
  columns: string[]
  style?: 'striped' | 'bordered' | 'plain'
  border?: boolean
}

export interface ReportTemplate {
  id: string
  name: string
  description?: string
  template_type: TemplateType
  applicable_test_types: string[]

  // Template structure
  sections: SectionConfig[]
  chart_configs?: Record<string, ChartConfig>
  table_configs?: Record<string, TableConfig>

  // Styling
  page_size?: 'A4' | 'LETTER'
  page_orientation?: 'portrait' | 'landscape'
  margins?: {
    left?: number
    right?: number
    top?: number
    bottom?: number
  }
  logo_path?: string
  color_scheme?: Record<string, string>

  // Metadata
  version?: string
  is_active: boolean
  is_default: boolean
  is_public: boolean
  created_by: string
  created_at: string
  updated_at: string
  usage_count: number
  last_used_at?: string
  tags?: string[]
  category?: string
}

export interface ReportTemplateSummary {
  id: string
  name: string
  template_type: TemplateType
  is_active: boolean
  is_default: boolean
  usage_count: number
  created_by: string
  created_at: string
}

export interface TemplateListResponse {
  templates: ReportTemplateSummary[]
  total: number
  page: number
  page_size: number
}

export interface CreateTemplateRequest {
  name: string
  template_type: TemplateType
  sections: SectionConfig[]
  created_by: string
  description?: string
  applicable_test_types?: string[]
  chart_configs?: Record<string, ChartConfig>
  table_configs?: Record<string, TableConfig>
  page_size?: 'A4' | 'LETTER'
  page_orientation?: 'portrait' | 'landscape'
  margins?: {
    left?: number
    right?: number
    top?: number
    bottom?: number
  }
  logo_path?: string
  color_scheme?: Record<string, string>
  is_active?: boolean
  is_default?: boolean
  is_public?: boolean
  tags?: string[]
  category?: string
}

export interface UpdateTemplateRequest {
  name?: string
  description?: string
  sections?: SectionConfig[]
  chart_configs?: Record<string, ChartConfig>
  table_configs?: Record<string, TableConfig>
  is_active?: boolean
  is_default?: boolean
  tags?: string[]
  category?: string
}

export interface TemplateListFilters {
  template_type?: TemplateType
  is_active?: boolean
  skip?: number
  limit?: number
}

// ==================== 执行来源链白名单 (ARCH-1 S2/S4a) ====================

/**
 * 可归档 / 可进报告的"正式执行"来源链。
 *
 * 单相位诊断 (`commissioning_adhoc`) **不在其中**: 它没有相位进度, 出的报告
 * 近乎空 (与 commissioning 列表隐藏 diagnostic_ad_hoc 同源约定)。
 *
 * ⚠️ 这是**白名单 = 默认隐藏**: 不在表里的链 (含 executed_by 为空的老行) 在
 * 待归档 / 报告选择器里都不出现。后端写 executed_by 的点新增时必须同步这里。
 *
 * `test_plan_runner` 保留: ARCH-1 S4 拆掉计划链后它不再产生新行, 但**历史行
 * 留在库里**(表原地封存), 去掉会让老执行在报告里选不到。
 */
export const FORMAL_EXECUTION_CHAINS = [
  'test_case_runner',
  'test_plan_runner',
  'commissioning_api',
] as const
