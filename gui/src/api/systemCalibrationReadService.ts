import calibrationClient from './calibrationClient';

export type LegacyKind = 'trp' | 'tis' | 'repeatability';
export interface LegacyRow {
  id: string; tested_at: string; validation_pass: boolean | null;
  measured_trp_dbm?: number; trp_error_db?: number;
  measured_tis_dbm?: number; tis_error_db?: number;
  absolute_error_db?: number; threshold_db?: number | null; num_probes_used?: number;
  test_type?: string; num_runs?: number; mean_dbm?: number | null;
  std_dev_db?: number | null; coefficient_of_variation?: number | null;
  min_dbm?: number | null; max_dbm?: number | null; range_db?: number | null;
  measurements?: Record<string, unknown>[]; test_case_id?: string | null;
  execution_ids?: string[] | null; metric_deltas?: Record<string, unknown> | null;
}
export interface LegacyCertificateSummary {
  id: string; certificate_number: string; overall_pass: boolean;
  trp_pass: boolean; tis_pass: boolean; repeatability_pass: boolean;
  calibration_date: string; valid_until: string; issued_at: string;
}
export interface LegacyCertificateDetail {
  id: string; certificate_number: string; system_name: string;
  system_serial_number: string | null; system_configuration: Record<string, unknown> | null;
  lab_name: string | null; lab_address: string | null; lab_accreditation: string | null;
  calibration_date: string; valid_until: string; standards: string[] | null;
  trp_error_db: number | null; trp_pass: boolean | null;
  tis_error_db: number | null; tis_pass: boolean | null;
  repeatability_std_dev_db: number | null; repeatability_pass: boolean | null;
  overall_pass: boolean; calibrated_by: string | null; reviewed_by: string | null;
  digital_signature: string | null; issued_at: string;
}

async function readArray<T>(path: string, skip: number, limit: number): Promise<T[]> {
  const { data } = await calibrationClient.get<unknown>(path, { params: { skip, limit } });
  if (!Array.isArray(data)) throw new Error('旧记录响应应为数组');
  return data as T[];
}
export async function listLegacyCalibrations(kind: LegacyKind, skip = 0, limit = 20): Promise<LegacyRow[]> {
  return readArray<LegacyRow>(`/calibration/${kind}`, skip, limit);
}
export async function listLegacyCertificates(skip = 0, limit = 20): Promise<LegacyCertificateSummary[]> {
  return readArray<LegacyCertificateSummary>('/calibration/certificate', skip, limit);
}
export async function getLegacyCertificate(id: string): Promise<LegacyCertificateDetail> {
  const { data } = await calibrationClient.get<LegacyCertificateDetail>(
    `/calibration/certificate/${encodeURIComponent(id)}`);
  if (!data || data.id !== id) throw new Error('证书响应与所选记录不一致');
  return data;
}
export const legacyNumber = (value: number | null | undefined, unit: string): string =>
  typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)} ${unit}` : '未知';
export const legacyVerdict = (value: boolean | null | undefined): string =>
  value === true ? '原记录：通过' : value === false ? '原记录：未通过' : '原记录：未知';
