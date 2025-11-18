/**
 * Test Plan Management API Service
 *
 * Provides API functions for test plan, test case, and queue management.
 */
import axios from 'axios';

// Create axios instance for test plan API
const testPlanClient = axios.create({
  baseURL: 'http://localhost:8001/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ==================== Type Definitions ====================

export type TestPlanStatus = 'draft' | 'ready' | 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
export type TestCaseType = 'TRP' | 'TIS' | 'Throughput' | 'Handover' | 'MIMO' | 'ChannelModel' | 'Custom';

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
  test_type: TestCaseType;
  frequency_mhz?: number;
  test_duration_sec?: number;
  is_template: boolean;
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
    ChannelModel: '信道模型',
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
