/**
 * Test Plan Management API Service
 *
 * Provides API functions for test plan, test case, and queue management.
 */
import axios from 'axios';

// Create axios instance for test plan API
// Use relative path to leverage Vite proxy instead of hardcoded address
const testPlanClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ==================== Type Definitions ====================

export type TestPlanStatus = 'draft' | 'ready' | 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
// ARCH-1 S1: 补齐后端 TestCaseType 枚举缺的两个值 (models/test_plan.py L34-44
// 有 9 个, 此前这里只有 7 — MIMO_OTA 种子模板在运行时真实存在, 类型是 stale 的)
export type TestCaseType = 'TRP' | 'TIS' | 'Throughput' | 'Handover' | 'MIMO' | 'MIMO_OTA' | 'ChannelModel' | 'VirtualRoadTest' | 'Custom';

export interface TestPlan {
  id: string;
  name: string;
  description?: string;
  version: string;
  status: TestPlanStatus;
  dut_info?: Record<string, any>;
  test_environment?: Record<string, any>;
  test_case_ids?: string[];
  total_test_cases: number;
  current_test_case_index: number;
  completed_test_cases: number;
  failed_test_cases: number;
  estimated_duration_minutes?: number;
  actual_duration_minutes?: number;
  started_at?: string;
  completed_at?: string;
  queue_position?: number;
  priority: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  notes?: string;
  tags?: string[];
}

export interface TestPlanSummary {
  id: string;
  name: string;
  status: TestPlanStatus;
  total_test_cases: number;
  completed_test_cases: number;
  failed_test_cases: number;
  priority: number;
  created_by: string;
  created_at: string;
}

export interface TestCase {
  id: string;
  name: string;
  description?: string;
  test_type: TestCaseType;
  configuration: Record<string, any>;
  pass_criteria?: Record<string, any>;
  expected_results?: Record<string, any>;
  probe_selection?: Record<string, any>;
  instrument_config?: Record<string, any>;
  channel_model?: string;
  channel_parameters?: Record<string, any>;
  frequency_mhz?: number;
  tx_power_dbm?: number;
  bandwidth_mhz?: number;
  test_duration_sec?: number;
  is_template: boolean;
  template_category?: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  version: string;
  parent_id?: string;
  tags?: string[];
}

export interface TestCaseSummary {
  id: string;
  name: string;
  description?: string;
  test_type: TestCaseType;
  template_category?: string;
  channel_model?: string;
  frequency_mhz?: number;
  bandwidth_mhz?: number;
  test_duration_sec?: number;
  is_template: boolean;
  pass_criteria?: Record<string, any>;
  tags?: string[];
  usage_count?: number;
  created_by: string;
  created_at: string;
}

export interface TestQueueItem {
  id: string;
  test_plan_id: string;
  position: number;
  priority: number;
  status: string;
  scheduled_start_time?: string;
  estimated_start_time?: string;
  dependencies?: string[];
  blocked_by?: string[];
  queued_by: string;
  queued_at: string;
  notes?: string;
}

export interface TestQueueSummary {
  queue_item: TestQueueItem;
  test_plan: TestPlanSummary;
}

// Request types
export interface CreateTestPlanRequest {
  name: string;
  description?: string;
  version?: string;
  dut_info?: Record<string, any>;
  test_environment?: Record<string, any>;
  test_case_ids?: string[];
  priority?: number;
  created_by: string;
  notes?: string;
  tags?: string[];
}

export interface UpdateTestPlanRequest {
  name?: string;
  description?: string;
  dut_info?: Record<string, any>;
  test_environment?: Record<string, any>;
  test_case_ids?: string[];
  priority?: number;
  notes?: string;
  tags?: string[];
}

export interface CreateTestCaseRequest {
  name: string;
  description?: string;
  test_type: TestCaseType;
  configuration: Record<string, any>;
  pass_criteria?: Record<string, any>;
  expected_results?: Record<string, any>;
  probe_selection?: Record<string, any>;
  instrument_config?: Record<string, any>;
  channel_model?: string;
  channel_parameters?: Record<string, any>;
  frequency_mhz?: number;
  tx_power_dbm?: number;
  bandwidth_mhz?: number;
  test_duration_sec?: number;
  is_template?: boolean;
  template_category?: string;
  created_by: string;
  tags?: string[];
}

export interface QueueTestPlanRequest {
  test_plan_id: string;
  priority?: number;
  scheduled_start_time?: string;
  dependencies?: string[];
  queued_by: string;
  notes?: string;
}

// ==================== API Functions ====================

// Test Plan CRUD
export async function createTestPlan(request: CreateTestPlanRequest): Promise<TestPlan> {
  const response = await testPlanClient.post<TestPlan>('/test-plans', request);
  return response.data;
}

export async function listTestPlans(
  skip = 0,
  limit = 100,
  status?: TestPlanStatus,
  created_by?: string
): Promise<{ total: number; items: TestPlanSummary[] }> {
  const params = new URLSearchParams();
  params.append('skip', skip.toString());
  params.append('limit', limit.toString());
  if (status) params.append('status', status);
  if (created_by) params.append('created_by', created_by);

  const response = await testPlanClient.get(`/test-plans?${params.toString()}`);
  return response.data;
}

export async function getTestPlan(id: string): Promise<TestPlan> {
  const response = await testPlanClient.get<TestPlan>(`/test-plans/${id}`);
  return response.data;
}

export async function updateTestPlan(id: string, request: UpdateTestPlanRequest): Promise<TestPlan> {
  const response = await testPlanClient.patch<TestPlan>(`/test-plans/${id}`, request);
  return response.data;
}

export async function deleteTestPlan(id: string): Promise<void> {
  await testPlanClient.delete(`/test-plans/${id}`);
}

export async function markTestPlanReady(id: string): Promise<TestPlan> {
  const response = await testPlanClient.post<TestPlan>(`/test-plans/${id}/mark-ready`);
  return response.data;
}

// Test Case CRUD
export async function createTestCase(request: CreateTestCaseRequest): Promise<TestCase> {
  const response = await testPlanClient.post<TestCase>('/test-plans/cases', request);
  return response.data;
}

export async function listTestCases(
  skip = 0,
  limit = 100,
  test_type?: TestCaseType,
  is_template?: boolean
): Promise<{ total: number; items: TestCaseSummary[] }> {
  const params = new URLSearchParams();
  params.append('skip', skip.toString());
  params.append('limit', limit.toString());
  if (test_type) params.append('test_type', test_type);
  if (is_template !== undefined) params.append('is_template', is_template.toString());

  const response = await testPlanClient.get(`/test-plans/cases?${params.toString()}`);
  return response.data;
}

export async function getTestCase(id: string): Promise<TestCase> {
  const response = await testPlanClient.get<TestCase>(`/test-plans/cases/${id}`);
  return response.data;
}

export async function deleteTestCase(id: string): Promise<void> {
  await testPlanClient.delete(`/test-plans/cases/${id}`);
}

export async function updateTestCase(
  id: string,
  payload: Partial<{
    name: string;
    description: string | null;
    configuration: Record<string, unknown>;
    pass_criteria: Record<string, unknown>;
    tags: string[];
  }>
): Promise<TestCase> {
  const response = await testPlanClient.patch<TestCase>(`/test-plans/cases/${id}`, payload);
  return response.data;
}

// Queue Management
export async function queueTestPlan(request: QueueTestPlanRequest): Promise<TestQueueItem> {
  const response = await testPlanClient.post<TestQueueItem>('/test-plans/queue', request);
  return response.data;
}

export async function getTestQueue(
  skip = 0,
  limit = 100
): Promise<{ total: number; items: TestQueueSummary[] }> {
  const params = new URLSearchParams();
  params.append('skip', skip.toString());
  params.append('limit', limit.toString());

  const response = await testPlanClient.get(`/test-plans/queue?${params.toString()}`);
  return response.data;
}

export async function removeFromQueue(test_plan_id: string): Promise<void> {
  await testPlanClient.delete(`/test-plans/queue/${test_plan_id}`);
}

export async function reorderQueue(test_plan_id: string, new_position: number): Promise<TestQueueItem> {
  const response = await testPlanClient.patch<TestQueueItem>(`/test-plans/queue/${test_plan_id}/reorder`, {
    new_position,
  });
  return response.data;
}

// Execution Control
export async function startTestPlan(test_plan_id: string, started_by: string): Promise<TestPlan> {
  const response = await testPlanClient.post<TestPlan>(`/test-plans/${test_plan_id}/start`, {
    test_plan_id,
    started_by,
  });
  return response.data;
}

export async function pauseTestPlan(test_plan_id: string, paused_by: string, reason?: string): Promise<TestPlan> {
  const response = await testPlanClient.post<TestPlan>(`/test-plans/${test_plan_id}/pause`, {
    test_plan_id,
    paused_by,
    reason,
  });
  return response.data;
}

export async function resumeTestPlan(test_plan_id: string, resumed_by: string): Promise<TestPlan> {
  const response = await testPlanClient.post<TestPlan>(`/test-plans/${test_plan_id}/resume`, {
    test_plan_id,
    resumed_by,
  });
  return response.data;
}

export async function cancelTestPlan(test_plan_id: string, cancelled_by: string, reason?: string): Promise<TestPlan> {
  const response = await testPlanClient.post<TestPlan>(`/test-plans/${test_plan_id}/cancel`, {
    test_plan_id,
    cancelled_by,
    reason,
  });
  return response.data;
}

export async function completeTestPlan(test_plan_id: string): Promise<TestPlan> {
  const response = await testPlanClient.post<TestPlan>(`/test-plans/${test_plan_id}/complete`);
  return response.data;
}

// ==================== Utility Functions ====================

export function getStatusColor(status: TestPlanStatus): string {
  const colors: Record<TestPlanStatus, string> = {
    draft: 'gray',
    ready: 'blue',
    queued: 'cyan',
    running: 'yellow',
    paused: 'orange',
    completed: 'green',
    failed: 'red',
    cancelled: 'gray',
  };
  return colors[status] || 'gray';
}

export function getStatusLabel(status: TestPlanStatus): string {
  const labels: Record<TestPlanStatus, string> = {
    draft: '草稿',
    ready: '就绪',
    queued: '已排队',
    running: '执行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  };
  return labels[status] || status;
}

export function getTestTypeLabel(type: TestCaseType): string {
  const labels: Record<TestCaseType, string> = {
    TRP: 'TRP - 总辐射功率',
    TIS: 'TIS - 总全向灵敏度',
    Throughput: '吞吐量测试',
    Handover: '切换测试',
    MIMO: 'MIMO 性能',
    MIMO_OTA: 'MIMO OTA 吞吐',
    ChannelModel: '信道模型',
    VirtualRoadTest: '虚拟路测',
    Custom: '自定义测试',
  };
  return labels[type] || type;
}

export function formatDuration(minutes?: number): string {
  if (!minutes) return '-';
  const hours = Math.floor(minutes / 60);
  const mins = Math.floor(minutes % 60);
  return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
}

export function calculateProgress(plan: TestPlan): number {
  if (plan.total_test_cases === 0) return 0;
  return Math.round((plan.completed_test_cases / plan.total_test_cases) * 100);
}

// ==================== ARCH-1 S1: TestCase 直接执行 ====================
// 正式测试执行正门 (设计稿 arch-1-testcase-first-simplification.md §2.3):
// 用例库点执行 → 后端 case-runner 5 相位链 (与暗室首测同一套 executors)。

export interface CaseExecuteResponse {
  execution_id: string
  snapshot_test_case_id: string
  source_test_case_id: string
  status: string
}

export interface CaseExecutionStatus {
  execution_id: string
  status: string
  source_test_case_id?: string | null
  phase_progress: { type: string; status: string }[]
  failed_phase?: string | null
  error_message?: string | null
  started_at?: string | null
  completed_at?: string | null
}

export async function executeTestCase(caseId: string): Promise<CaseExecuteResponse> {
  const response = await testPlanClient.post(`/test-plans/cases/${caseId}/execute`)
  return response.data
}

export async function getCaseExecutionStatus(
  executionId: string
): Promise<CaseExecutionStatus> {
  const response = await testPlanClient.get(
    `/test-plans/cases/executions/${executionId}`
  )
  return response.data
}

export async function cancelCaseExecution(executionId: string): Promise<void> {
  await testPlanClient.post(`/test-executions/${executionId}/cancel`)
}

// ARCH-1 S2 (Codex #237 C3): 查"在跑的执行"用于导航后恢复 activeRun。
// 走执行历史的现成 status=running 参数, 零新增端点。
export interface RunningExecutionRow {
  id: string
  source_test_case_id: string | null
  status: string
  phases_done: number | null
}

export async function fetchRunningExecution(): Promise<RunningExecutionRow | null> {
  const response = await testPlanClient.get<{ items: RunningExecutionRow[] }>(
    '/test-executions',
    { params: { status: 'running', limit: 1 } }
  )
  return response.data.items[0] ?? null
}
