/**
 * Probe Calibration React Query Hooks
 *
 * Custom hooks for managing probe calibration data with TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query'

import * as probeCalibrationService from '../api/probeCalibrationService'
import type {
  // Common
  CalibrationJobResponse,
  CalibrationType,
  // Amplitude
  StartAmplitudeCalibrationRequest,
  AmplitudeCalibrationResponse,
  // Phase
  StartPhaseCalibrationRequest,
  PhaseCalibrationResponse,
  // Polarization
  StartPolarizationCalibrationRequest,
  PolarizationCalibrationResponse,
  // Pattern
  StartPatternCalibrationRequest,
  PatternCalibrationResponse,
  // Link
  StartLinkCalibrationRequest,
  LinkCalibrationResponse,
  LinkValidityStatus,
  // Validity
  ProbeCalibrationStatus,
  CalibrationValidityReport,
  InvalidateCalibrationRequest,
  InvalidateCalibrationResponse,
  ExpiringCalibrationsResponse,
  ExpiredCalibrationsResponse,
  // History
  CalibrationHistoryResponse,
  // Comprehensive
  ProbeCalibrationData,
} from '../types/probeCalibration'

// ==================== Query Keys ====================

export const probeCalibrationKeys = {
  all: ['probeCalibration'] as const,
  // Amplitude
  amplitude: (chamberId: string, probeId: number) => [...probeCalibrationKeys.all, chamberId, 'amplitude', probeId] as const,
  amplitudeHistory: (chamberId: string, probeId: number) =>
    [...probeCalibrationKeys.all, chamberId, 'amplitude', 'history', probeId] as const,
  // Phase
  phase: (chamberId: string, probeId: number) => [...probeCalibrationKeys.all, chamberId, 'phase', probeId] as const,
  phaseHistory: (chamberId: string, probeId: number) =>
    [...probeCalibrationKeys.all, chamberId, 'phase', 'history', probeId] as const,
  // Polarization
  polarization: (chamberId: string, probeId: number) =>
    [...probeCalibrationKeys.all, chamberId, 'polarization', probeId] as const,
  polarizationHistory: (chamberId: string, probeId: number) =>
    [...probeCalibrationKeys.all, chamberId, 'polarization', 'history', probeId] as const,
  // Pattern
  pattern: (chamberId: string, probeId: number, frequencyMhz?: number) =>
    [...probeCalibrationKeys.all, chamberId, 'pattern', probeId, frequencyMhz] as const,
  // Link
  linkLatest: (calibrationType?: string) =>
    [...probeCalibrationKeys.all, 'link', 'latest', calibrationType] as const,
  linkHistory: (calibrationType?: string) =>
    [...probeCalibrationKeys.all, 'link', 'history', calibrationType] as const,
  linkValidity: () => [...probeCalibrationKeys.all, 'link', 'validity'] as const,
  // Validity
  validityReport: (chamberId: string, probeIds?: string) =>
    [...probeCalibrationKeys.all, chamberId, 'validity', 'report', probeIds] as const,
  expiring: (chamberId: string, days: number, calibrationType?: CalibrationType) =>
    [...probeCalibrationKeys.all, chamberId, 'validity', 'expiring', days, calibrationType] as const,
  expired: (chamberId: string, calibrationType?: CalibrationType) =>
    [...probeCalibrationKeys.all, chamberId, 'validity', 'expired', calibrationType] as const,
  probeValidity: (chamberId: string, probeId: number) =>
    [...probeCalibrationKeys.all, chamberId, 'validity', 'probe', probeId] as const,
  // Comprehensive data
  probeData: (chamberId: string, probeId: number) => [...probeCalibrationKeys.all, chamberId, 'data', probeId] as const,
}

// ==================== Amplitude Calibration Hooks ====================

/**
 * Hook to start amplitude calibration
 */
export function useStartAmplitudeCalibration(): UseMutationResult<
  CalibrationJobResponse,
  Error,
  StartAmplitudeCalibrationRequest
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: probeCalibrationService.startAmplitudeCalibration,
    onSuccess: (_, variables) => {
      // Invalidate relevant queries
      variables.probe_ids.forEach((probeId) => {
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.amplitude(variables.chamber_id, probeId) })
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.probeData(variables.chamber_id, probeId) })
      })
      queryClient.invalidateQueries({ queryKey: [...probeCalibrationKeys.all, 'validity'] })
    },
  })
}

/**
 * Hook to get amplitude calibration for a probe
 */
export function useAmplitudeCalibration(
  chamberId: string,
  probeId: number,
  enabled: boolean = true
): UseQueryResult<AmplitudeCalibrationResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.amplitude(chamberId, probeId),
    queryFn: () => probeCalibrationService.getAmplitudeCalibration(chamberId, probeId),
    enabled: enabled && Boolean(chamberId),
  })
}

/**
 * Hook to get amplitude calibration history
 */
export function useAmplitudeCalibrationHistory(
  chamberId: string,
  probeId: number,
  limit: number = 20,
  enabled: boolean = true
): UseQueryResult<CalibrationHistoryResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.amplitudeHistory(chamberId, probeId),
    queryFn: () => probeCalibrationService.getAmplitudeCalibrationHistory(chamberId, probeId, limit),
    enabled: enabled && Boolean(chamberId),
  })
}

// ==================== Phase Calibration Hooks ====================

/**
 * Hook to start phase calibration
 */
export function useStartPhaseCalibration(): UseMutationResult<
  CalibrationJobResponse,
  Error,
  StartPhaseCalibrationRequest
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: probeCalibrationService.startPhaseCalibration,
    onSuccess: (_, variables) => {
      variables.probe_ids.forEach((probeId) => {
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.phase(variables.chamber_id, probeId) })
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.probeData(variables.chamber_id, probeId) })
      })
      queryClient.invalidateQueries({ queryKey: [...probeCalibrationKeys.all, 'validity'] })
    },
  })
}

/**
 * Hook to get phase calibration for a probe
 */
export function usePhaseCalibration(
  chamberId: string,
  probeId: number,
  enabled: boolean = true
): UseQueryResult<PhaseCalibrationResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.phase(chamberId, probeId),
    queryFn: () => probeCalibrationService.getPhaseCalibration(chamberId, probeId),
    enabled: enabled && Boolean(chamberId),
  })
}

/**
 * Hook to get phase calibration history
 */
export function usePhaseCalibrationHistory(
  chamberId: string,
  probeId: number,
  limit: number = 20,
  enabled: boolean = true
): UseQueryResult<CalibrationHistoryResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.phaseHistory(chamberId, probeId),
    queryFn: () => probeCalibrationService.getPhaseCalibrationHistory(chamberId, probeId, limit),
    enabled: enabled && Boolean(chamberId),
  })
}

// ==================== Polarization Calibration Hooks ====================

/**
 * Hook to start polarization calibration
 */
export function useStartPolarizationCalibration(): UseMutationResult<
  CalibrationJobResponse,
  Error,
  StartPolarizationCalibrationRequest
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: probeCalibrationService.startPolarizationCalibration,
    onSuccess: (_, variables) => {
      variables.probe_ids.forEach((probeId) => {
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.polarization(variables.chamber_id, probeId) })
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.probeData(variables.chamber_id, probeId) })
      })
      queryClient.invalidateQueries({ queryKey: [...probeCalibrationKeys.all, 'validity'] })
    },
  })
}

/**
 * Hook to get polarization calibration for a probe
 */
export function usePolarizationCalibration(
  chamberId: string,
  probeId: number,
  enabled: boolean = true
): UseQueryResult<PolarizationCalibrationResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.polarization(chamberId, probeId),
    queryFn: () => probeCalibrationService.getPolarizationCalibration(chamberId, probeId),
    enabled: enabled && Boolean(chamberId),
  })
}

/**
 * Hook to get polarization calibration history
 */
export function usePolarizationCalibrationHistory(
  chamberId: string,
  probeId: number,
  limit: number = 20,
  enabled: boolean = true
): UseQueryResult<CalibrationHistoryResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.polarizationHistory(chamberId, probeId),
    queryFn: () => probeCalibrationService.getPolarizationCalibrationHistory(chamberId, probeId, limit),
    enabled: enabled && Boolean(chamberId),
  })
}

// ==================== Pattern Calibration Hooks ====================

/**
 * Hook to start pattern calibration
 */
export function useStartPatternCalibration(): UseMutationResult<
  CalibrationJobResponse,
  Error,
  StartPatternCalibrationRequest
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: probeCalibrationService.startPatternCalibration,
    onSuccess: (_, variables) => {
      variables.probe_ids.forEach((probeId) => {
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.pattern(variables.chamber_id, probeId) })
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.probeData(variables.chamber_id, probeId) })
      })
      queryClient.invalidateQueries({ queryKey: [...probeCalibrationKeys.all, 'validity'] })
    },
  })
}

/**
 * Hook to get pattern calibration for a probe
 */
export function usePatternCalibration(
  chamberId: string,
  probeId: number,
  frequencyMhz?: number,
  enabled: boolean = true
): UseQueryResult<PatternCalibrationResponse[], Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.pattern(chamberId, probeId, frequencyMhz),
    queryFn: () => probeCalibrationService.getPatternCalibration(chamberId, probeId, frequencyMhz),
    enabled: enabled && Boolean(chamberId),
  })
}

// ==================== Link Calibration Hooks ====================

/**
 * Hook to start link calibration
 */
export function useStartLinkCalibration(): UseMutationResult<
  CalibrationJobResponse,
  Error,
  StartLinkCalibrationRequest
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: probeCalibrationService.startLinkCalibration,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.linkLatest() })
      queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.linkHistory() })
      queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.linkValidity() })
      queryClient.invalidateQueries({ queryKey: [...probeCalibrationKeys.all, 'validity'] })
    },
  })
}

/**
 * Hook to get latest link calibration
 */
export function useLatestLinkCalibration(
  calibrationType?: string,
  enabled: boolean = true
): UseQueryResult<LinkCalibrationResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.linkLatest(calibrationType),
    queryFn: () => probeCalibrationService.getLatestLinkCalibration(calibrationType),
    enabled,
  })
}

/**
 * Hook to get link calibration history
 */
export function useLinkCalibrationHistory(
  calibrationType?: string,
  limit: number = 20,
  enabled: boolean = true
): UseQueryResult<LinkCalibrationResponse[], Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.linkHistory(calibrationType),
    queryFn: () => probeCalibrationService.getLinkCalibrationHistory(calibrationType, limit),
    enabled,
  })
}

/**
 * Hook to check link calibration validity
 */
export function useLinkValidity(
  enabled: boolean = true
): UseQueryResult<LinkValidityStatus, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.linkValidity(),
    queryFn: probeCalibrationService.checkLinkValidity,
    enabled,
  })
}

// ==================== Validity Management Hooks ====================

/**
 * Hook to get validity report
 */
export function useValidityReport(
  chamberId: string,
  probeIds?: string,
  enabled: boolean = true
): UseQueryResult<CalibrationValidityReport, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.validityReport(chamberId, probeIds),
    queryFn: () => probeCalibrationService.getValidityReport(chamberId, probeIds),
    enabled: enabled && Boolean(chamberId),
  })
}

/**
 * Hook to get expiring calibrations
 */
export function useExpiringCalibrations(
  chamberId: string,
  days: number = 7,
  calibrationType?: CalibrationType,
  enabled: boolean = true
): UseQueryResult<ExpiringCalibrationsResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.expiring(chamberId, days, calibrationType),
    queryFn: () => probeCalibrationService.getExpiringCalibrations(chamberId, days, calibrationType),
    enabled: enabled && Boolean(chamberId),
  })
}

/**
 * Hook to get expired calibrations
 */
export function useExpiredCalibrations(
  chamberId: string,
  calibrationType?: CalibrationType,
  enabled: boolean = true
): UseQueryResult<ExpiredCalibrationsResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.expired(chamberId, calibrationType),
    queryFn: () => probeCalibrationService.getExpiredCalibrations(chamberId, calibrationType),
    enabled: enabled && Boolean(chamberId),
  })
}

/**
 * Hook to get validity status for a single probe
 */
export function useProbeValidity(
  chamberId: string,
  probeId: number,
  enabled: boolean = true
): UseQueryResult<ProbeCalibrationStatus, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.probeValidity(chamberId, probeId),
    queryFn: () => probeCalibrationService.getProbeValidity(chamberId, probeId),
    enabled: enabled && Boolean(chamberId),
  })
}

/**
 * Hook to invalidate a calibration
 */
export function useInvalidateCalibration(): UseMutationResult<
  InvalidateCalibrationResponse,
  Error,
  { calibrationType: CalibrationType; calibrationId: string; chamberId: string; request: InvalidateCalibrationRequest }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ calibrationType, calibrationId, chamberId, request }) =>
      probeCalibrationService.invalidateCalibration(calibrationType, calibrationId, chamberId, request),
    onSuccess: () => {
      // Invalidate all calibration-related queries
      queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.all })
    },
  })
}

// ==================== Comprehensive Data Hooks ====================

/**
 * Hook to get comprehensive calibration data for a probe
 */
export function useProbeCalibrationData(
  chamberId: string,
  probeId: number,
  enabled: boolean = true
): UseQueryResult<ProbeCalibrationData, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.probeData(chamberId, probeId),
    queryFn: () => probeCalibrationService.getProbeCalibrationData(chamberId, probeId),
    enabled: enabled && Boolean(chamberId),
  })
}
