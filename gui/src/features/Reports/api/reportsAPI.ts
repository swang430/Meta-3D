/**
 * Report Management API Client
 *
 * This module provides API functions for report generation and template management
 *
 * @version 1.0.0
 * @date 2025-11-26
 */

import client from '../../../api/client'
import type {
  TestReport,
  ReportListResponse,
  ReportListFilters,
  CreateReportRequest,
  UpdateReportRequest,
  ReportTemplate,
  TemplateListResponse,
  TemplateListFilters,
  CreateTemplateRequest,
  UpdateTemplateRequest,
} from '../types'

// ==================== Report Management ====================

/**
 * List reports with filters and pagination
 */
export const listReports = async (
  filters?: ReportListFilters,
): Promise<ReportListResponse> => {
  const response = await client.get<ReportListResponse>('/reports', {
    params: filters,
  })
  return response.data
}

/**
 * Get a single report by ID
 */
export const getReport = async (reportId: string): Promise<TestReport> => {
  const response = await client.get<TestReport>(`/reports/${reportId}`)
  return response.data
}

/**
 * Create a new report
 */
export const createReport = async (
  payload: CreateReportRequest,
): Promise<TestReport> => {
  const response = await client.post<TestReport>('/reports', payload)
  return response.data
}

/**
 * Update an existing report's metadata
 */
export const updateReport = async (
  reportId: string,
  payload: UpdateReportRequest,
): Promise<TestReport> => {
  const response = await client.patch<TestReport>(
    `/reports/${reportId}`,
    payload,
  )
  return response.data
}

/**
 * Delete a report
 */
export const deleteReport = async (reportId: string): Promise<void> => {
  await client.delete(`/reports/${reportId}`)
}

/**
 * Trigger report generation (PDF/HTML/Excel)
 * This starts the async report generation process
 */
export const generateReport = async (reportId: string): Promise<TestReport> => {
  const response = await client.post<TestReport>(
    `/reports/${reportId}/generate`,
  )
  return response.data
}

/**
 * Download a generated report file
 * Returns the file blob for download
 */
export const downloadReport = async (reportId: string): Promise<Blob> => {
  const response = await client.get(`/reports/${reportId}/download`, {
    responseType: 'blob',
  })
  return response.data
}

// ==================== Template Management ====================

/**
 * List report templates with filters and pagination
 */
export const listTemplates = async (
  filters?: TemplateListFilters,
): Promise<TemplateListResponse> => {
  const response = await client.get<TemplateListResponse>('/reports/templates', {
    params: filters,
  })
  return response.data
}

/**
 * Get a single template by ID
 */
export const getTemplate = async (
  templateId: string,
): Promise<ReportTemplate> => {
  const response = await client.get<ReportTemplate>(
    `/reports/templates/${templateId}`,
  )
  return response.data
}

/**
 * Create a new report template
 */
export const createTemplate = async (
  payload: CreateTemplateRequest,
): Promise<ReportTemplate> => {
  const response = await client.post<ReportTemplate>(
    '/reports/templates',
    payload,
  )
  return response.data
}

/**
 * Update an existing template
 */
export const updateTemplate = async (
  templateId: string,
  payload: UpdateTemplateRequest,
): Promise<ReportTemplate> => {
  const response = await client.patch<ReportTemplate>(
    `/reports/templates/${templateId}`,
    payload,
  )
  return response.data
}

/**
 * Delete a template
 */
export const deleteTemplate = async (templateId: string): Promise<void> => {
  await client.delete(`/reports/templates/${templateId}`)
}

/**
 * Clone an existing template
 */
export const cloneTemplate = async (
  templateId: string,
  newName: string,
): Promise<ReportTemplate> => {
  const response = await client.post<ReportTemplate>(
    `/reports/templates/${templateId}/clone`,
    { name: newName },
  )
  return response.data
}
