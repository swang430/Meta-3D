/**
 * Unified Test Management Types
 *
 * This file contains all type definitions for the unified test management system,
 * integrating concepts from both TestConfig and TestPlanManagement modules.
 *
 * @version 2.0.0
 * @date 2025-11-18
 */

// ==================== Core Status Types ====================

/**
 * Test Plan Status - 8 distinct states
 */
export type TestPlanStatus =
  | 'draft'         // 草稿 - 正在编辑
  | 'ready'         // 就绪 - 可以入队
  | 'queued'        // 已入队 - 等待执行
  | 'running'       // 执行中
  | 'paused'        // 已暂停
  | 'completed'     // 已完成
  | 'failed'        // 失败
  | 'cancelled'     // 已取消

/**
 * Test Step Status
 */
export type TestStepStatus =
  | 'pending'       // 待执行
  | 'running'       // 执行中
  | 'completed'     // 已完成
  | 'failed'        // 失败
  | 'skipped'       // 已跳过

/**
 * Parameter Type - Defines the UI input type
 */
export type ParameterType =
  | 'text'          // 文本输入
  | 'number'        // 数字输入
  | 'select'        // 下拉选择
  | 'textarea'      // 多行文本
  | 'boolean'       // 布尔开关
  | 'json'          // JSON 编辑器

// ==================== Parameter Definitions ====================

/**
 * Parameter Validation Rules
 */
export interface ParameterValidation {
  min?: number              // 最小值 (for number)
  max?: number              // 最大值 (for number)
  pattern?: string          // 正则表达式 (for text)
  options?: string[]        // 选项列表 (for select)
  required?: boolean        // 是否必填
}

/**
 * Step Parameter Definition
 */
export interface StepParameter {
  // 参数元数据
  type: ParameterType
  label: string
  description?: string

  // 参数值
  value: any
  defaultValue?: any

  // 验证规则
  required: boolean
  validation?: ParameterValidation

  // UI 配置
  placeholder?: string
  unit?: string             // 单位 (如 MHz, dBm, %)
  groupId?: string          // 参数分组ID
  helpText?: string         // 帮助文本
}

/**
 * Parameters Map - Key-value pairs of parameter definitions
 */
export type ParametersMap = Record<string, StepParameter>

// ==================== Test Step ====================

/**
 * Test Step - Individual execution unit within a test plan
 */
export interface TestStep {
  id: string
  order: number                        // 执行顺序 (0-based index)

  // 序列库关联
  sequence_library_id: string          // 关联的序列库模板ID

  // 步骤元数据
  title: string
  description: string
  category: string                     // 步骤分类 (如 'calibration', 'measurement')

  // 参数配置
  parameters: ParametersMap            // 动态参数配置

  // 执行配置
  timeout_seconds?: number             // 超时时间 (默认 300)
  retry_count?: number                 // 重试次数 (默认 0)
  continue_on_failure: boolean         // 失败是否继续 (默认 false)

  // 执行状态 (运行时填充)
  status?: TestStepStatus
  result?: string                      // 执行结果描述
  error_message?: string               // 错误信息
  started_at?: string                  // 开始时间 (ISO 8601)
  completed_at?: string                // 完成时间 (ISO 8601)
}

// ==================== DUT Information ====================

/**
 * Device Under Test Information
 */
export interface DUTInfo {
  model: string                        // 设备型号 (如 'iPhone 15 Pro')
  serial: string                       // 序列号
  imei?: string                        // IMEI (可选)
  manufacturer?: string                // 制造商
  firmware_version?: string            // 固件版本
}

// ==================== Test Environment ====================

/**
 * Test Environment Configuration
 */
export interface TestEnvironment {
  chamber_id: string                   // 暗室ID (如 'MPAC-01')
  temperature: number                  // 温度 (°C)
  humidity: number                     // 湿度 (%)
  atmospheric_pressure?: number        // 大气压 (kPa)
  notes?: string                       // 环境备注
}

// ==================== Test Plan ====================

/**
 * Unified Test Plan - Core entity combining TestConfig and TestPlanManagement
 */
export interface UnifiedTestPlan {
  // ===== 基础信息 =====
  id: string
  name: string
  description: string
  version: string                      // 版本号 (如 '1.0.0')
  status: TestPlanStatus

  // ===== DUT 信息 =====
  dut_info: DUTInfo

  // ===== 测试环境 =====
  test_environment: TestEnvironment

  // ===== 步骤配置 ⭐ KEY INTEGRATION POINT =====
  steps: TestStep[]                    // 步骤数组 (from TestConfig)

  // ===== 测试例关联 =====
  test_case_ids: string[]              // 关联的测试例ID数组

  // ===== 执行统计 =====
  total_test_cases: number             // 总测试例数
  completed_test_cases: number         // 已完成数
  failed_test_cases: number            // 失败数

  // ===== 队列信息 =====
  queue_position?: number              // 队列位置 (1-based)
  priority: number                     // 优先级 (1-10, 10最高)

  // ===== 时间追踪 =====
  estimated_duration_minutes?: number  // 预估时长 (分钟)
  actual_duration_minutes?: number     // 实际时长 (分钟)
  started_at?: string                  // 开始时间 (ISO 8601)
  completed_at?: string                // 完成时间 (ISO 8601)

  // ===== 元数据 =====
  created_by: string                   // 创建者
  created_at: string                   // 创建时间 (ISO 8601)
  updated_at: string                   // 更新时间 (ISO 8601)
  notes?: string                       // 备注
  tags?: string[]                      // 标签数组
}

/**
 * Test Plan Summary - Lightweight version for list views
 */
export interface TestPlanSummary {
  id: string
  name: string
  status: TestPlanStatus
  priority: number
  total_test_cases: number
  completed_test_cases: number
  failed_test_cases: number
  queue_position?: number
  created_by: string
  created_at: string
  updated_at: string
  tags?: string[]
}

// ==================== Sequence Library ====================

/**
 * Sequence Library Item - Reusable step template
 */
export interface SequenceLibraryItem {
  id: string
  name: string                         // 序列名称
  description: string | null
  category: string | null              // 分类 (如 'Calibration', 'Measurement')
  steps: Array<Record<string, any>>    // 步骤数组
  parameters: Record<string, any> | null  // 参数定义
  default_values: Record<string, any> | null  // 默认值
  validation_rules: Record<string, any> | null  // 验证规则
  is_public: boolean                   // 是否公开
  usage_count: number                  // 使用次数
  created_by: string                   // 创建者
  created_at: string                   // 创建时间
  updated_at: string                   // 更新时间
  tags: string[] | null                // 标签数组
}

// ==================== Queue Management ====================

/**
 * Test Queue Item - Represents a test plan in the execution queue
 */
export interface TestQueueItem {
  id: string
  test_plan_id: string
  position: number                     // 队列位置 (1-based)
  priority: number                     // 优先级 (1-10)
  status: 'waiting' | 'ready' | 'blocked'

  // 调度信息
  scheduled_start_time?: string        // 预定开始时间 (ISO 8601)
  estimated_start_time?: string        // 预计开始时间 (ISO 8601)

  // 依赖关系
  dependencies?: string[]              // 依赖的测试计划ID数组
  blocked_by?: string[]                // 阻塞当前计划的ID数组

  // 元数据
  queued_by: string                    // 入队操作者
  queued_at: string                    // 入队时间 (ISO 8601)
  notes?: string                       // 队列备注
}

/**
 * Test Queue Summary - Queue item with plan details
 */
export interface TestQueueSummary {
  queue_item: TestQueueItem
  test_plan: TestPlanSummary
}

// ==================== Execution History ====================

/**
 * Test Execution Record - Historical execution data
 */
export interface TestExecutionRecord {
  id: string
  test_plan_id: string
  test_plan_name: string
  test_plan_version: string

  status: 'completed' | 'failed' | 'cancelled'

  // 执行统计
  total_steps: number
  completed_steps: number
  failed_steps: number
  skipped_steps: number

  // 时间统计
  started_at: string
  completed_at: string
  duration_minutes: number

  // 执行者
  started_by: string

  // 结果
  success_rate: number                 // 成功率 (0-1)
  error_summary?: string               // 错误摘要
  artifacts?: string[]                 // 产出物URL数组 (报告、日志等)

  // 元数据
  notes?: string
  tags?: string[]
}

// ==================== API Request/Response Types ====================

/**
 * Plans List Request Parameters
 */
export interface PlansListParams {
  skip?: number
  limit?: number
  status?: TestPlanStatus
  search?: string
  created_by?: string
  tags?: string[]
  sort_by?: 'created_at' | 'updated_at' | 'priority' | 'name'
  sort_order?: 'asc' | 'desc'
}

/**
 * Plans List Response
 */
export interface PlansListResponse {
  total: number
  items: TestPlanSummary[]
}

/**
 * Create Test Plan Request
 */
export interface CreateTestPlanRequest {
  name: string
  description?: string
  dut_info: DUTInfo
  test_environment: TestEnvironment
  priority?: number
  notes?: string
  tags?: string[]
  created_by: string
}

/**
 * Update Test Plan Request
 */
export interface UpdateTestPlanRequest {
  name?: string
  description?: string
  status?: string  // Test plan status (draft, ready, queued, running, paused, completed, failed, cancelled)
  dut_info?: Partial<DUTInfo>
  test_environment?: Partial<TestEnvironment>
  priority?: number
  notes?: string
  tags?: string[]
}

/**
 * Add Step Request
 */
export interface AddStepRequest {
  sequence_library_id: string
  order: number
  parameters?: ParametersMap
  timeout_seconds?: number
  retry_count?: number
  continue_on_failure?: boolean
}

/**
 * Update Step Request
 */
export interface UpdateStepRequest {
  title?: string
  description?: string
  parameters?: ParametersMap
  timeout_seconds?: number
  retry_count?: number
  continue_on_failure?: boolean
}

/**
 * Reorder Steps Request
 */
export interface ReorderStepsRequest {
  step_orders: Array<{
    step_id: string
    order: number
  }>
}

/**
 * Queue Test Plan Request
 */
export interface QueueTestPlanRequest {
  test_plan_id: string
  priority?: number
  scheduled_start_time?: string
  dependencies?: string[]
  queued_by: string  // Required field
  notes?: string
}

/**
 * Start Execution Request
 */
export interface StartExecutionRequest {
  started_by: string
}

/**
 * Pause Execution Request
 */
export interface PauseExecutionRequest {
  paused_by: string
  reason?: string
}

/**
 * Resume Execution Request
 */
export interface ResumeExecutionRequest {
  resumed_by: string
}

/**
 * Cancel Execution Request
 */
export interface CancelExecutionRequest {
  cancelled_by: string
  reason?: string
}

// ==================== Query Filters ====================

/**
 * History Filters
 */
export interface HistoryFilters {
  skip?: number
  limit?: number
  status?: 'completed' | 'failed' | 'cancelled'
  start_date?: string
  end_date?: string
  test_plan_id?: string
  started_by?: string
}

/**
 * Sequence Library Filters
 */
export interface SequenceLibraryFilters {
  category?: string
  search?: string
  tags?: string[]
  sort_by?: 'popularity' | 'usage_count' | 'created_at' | 'title'
}

// ==================== UI State Types ====================

/**
 * Plan Editor State
 */
export interface PlanEditorState {
  mode: 'create' | 'edit'
  planId?: string
  currentStep: number
  formData: Partial<CreateTestPlanRequest>
  isDirty: boolean
}

/**
 * Steps Editor State
 */
export interface StepsEditorState {
  selectedPlanId?: string
  selectedStepId?: string
  editingParameters: ParametersMap | null
  isDirty: boolean
}

/**
 * Pagination State
 */
export interface PaginationState {
  page: number
  pageSize: number
  total: number
}

// ==================== Error Types ====================

/**
 * API Error Response
 */
export interface APIError {
  message: string
  detail?: string
  status: number
  errors?: Record<string, string[]>
}

// ==================== Utility Types ====================

/**
 * Sort Order
 */
export type SortOrder = 'asc' | 'desc'

/**
 * Loading State
 */
export interface LoadingState {
  isLoading: boolean
  error?: APIError
}

/**
 * Action Result
 */
export interface ActionResult<T = void> {
  success: boolean
  data?: T
  error?: APIError
}

// ==================== Type Guards ====================

/**
 * Check if a status is terminal (completed, failed, or cancelled)
 */
export function isTerminalStatus(status: TestPlanStatus): boolean {
  return ['completed', 'failed', 'cancelled'].includes(status)
}

/**
 * Check if a plan can be queued
 */
export function canQueuePlan(status: TestPlanStatus): boolean {
  return status === 'ready'
}

/**
 * Check if a plan can be started
 */
export function canStartPlan(status: TestPlanStatus): boolean {
  return status === 'queued'
}

/**
 * Check if a plan is in execution
 */
export function isExecuting(status: TestPlanStatus): boolean {
  return ['queued', 'running', 'paused'].includes(status)
}
