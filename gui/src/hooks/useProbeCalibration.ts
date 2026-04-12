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
  amplitude: (probeId: number) => [...probeCalibrationKeys.all, 'amplitude', probeId] as const,
  amplitudeHistory: (probeId: number) =>
    [...probeCalibrationKeys.all, 'amplitude', 'history', probeId] as const,
  // Phase
  phase: (probeId: number) => [...probeCalibrationKeys.all, 'phase', probeId] as const,
  phaseHistory: (probeId: number) =>
    [...probeCalibrationKeys.all, 'phase', 'history', probeId] as const,
  // Polarization
  polarization: (probeId: number) =>
    [...probeCalibrationKeys.all, 'polarization', probeId] as const,
  polarizationHistory: (probeId: number) =>
    [...probeCalibrationKeys.all, 'polarization', 'history', probeId] as const,
  // Pattern
  pattern: (probeId: number, frequencyMhz?: number) =>
    [...probeCalibrationKeys.all, 'pattern', probeId, frequencyMhz] as const,
  // Link
  linkLatest: (calibrationType?: string) =>
    [...probeCalibrationKeys.all, 'link', 'latest', calibrationType] as const,
  linkHistory: (calibrationType?: string) =>
    [...probeCalibrationKeys.all, 'link', 'history', calibrationType] as const,
  linkValidity: () => [...probeCalibrationKeys.all, 'link', 'validity'] as const,
  // Validity
  validityReport: (probeIds?: string) =>
    [...probeCalibrationKeys.all, 'validity', 'report', probeIds] as const,
  expiring: (days: number, calibrationType?: CalibrationType) =>
    [...probeCalibrationKeys.all, 'validity', 'expiring', days, calibrationType] as const,
  expired: (calibrationType?: CalibrationType) =>
    [...probeCalibrationKeys.all, 'validity', 'expired', calibrationType] as const,
  probeValidity: (probeId: number) =>
    [...probeCalibrationKeys.all, 'validity', 'probe', probeId] as const,
  // Comprehensive data
  probeData: (probeId: number) => [...probeCalibrationKeys.all, 'data', probeId] as const,
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
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.amplitude(probeId) })
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.probeData(probeId) })
      })
      queryClient.invalidateQueries({ queryKey: [...probeCalibrationKeys.all, 'validity'] })
    },
  })
}

/**
 * Hook to get amplitude calibration for a probe
 */
export function useAmplitudeCalibration(
  probeId: number,
  enabled: boolean = true
): UseQueryResult<AmplitudeCalibrationResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.amplitude(probeId),
    queryFn: () => probeCalibrationService.getAmplitudeCalibration(probeId),
    enabled,
  })
}

/**
 * Hook to get amplitude calibration history
 */
export function useAmplitudeCalibrationHistory(
  probeId: number,
  limit: number = 20,
  enabled: boolean = true
): UseQueryResult<CalibrationHistoryResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.amplitudeHistory(probeId),
    queryFn: () => probeCalibrationService.getAmplitudeCalibrationHistory(probeId, limit),
    enabled,
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
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.phase(probeId) })
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.probeData(probeId) })
      })
      queryClient.invalidateQueries({ queryKey: [...probeCalibrationKeys.all, 'validity'] })
    },
  })
}

/**
 * Hook to get phase calibration for a probe
 */
export function usePhaseCalibration(
  probeId: number,
  enabled: boolean = true
): UseQueryResult<PhaseCalibrationResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.phase(probeId),
    queryFn: () => probeCalibrationService.getPhaseCalibration(probeId),
    enabled,
  })
}

/**
 * Hook to get phase calibration history
 */
export function usePhaseCalibrationHistory(
  probeId: number,
  limit: number = 20,
  enabled: boolean = true
): UseQueryResult<CalibrationHistoryResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.phaseHistory(probeId),
    queryFn: () => probeCalibrationService.getPhaseCalibrationHistory(probeId, limit),
    enabled,
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
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.polarization(probeId) })
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.probeData(probeId) })
      })
      queryClient.invalidateQueries({ queryKey: [...probeCalibrationKeys.all, 'validity'] })
    },
  })
}

/**
 * Hook to get polarization calibration for a probe
 */
export function usePolarizationCalibration(
  probeId: number,
  enabled: boolean = true
): UseQueryResult<PolarizationCalibrationResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.polarization(probeId),
    queryFn: () => probeCalibrationService.getPolarizationCalibration(probeId),
    enabled,
  })
}

/**
 * Hook to get polarization calibration history
 */
export function usePolarizationCalibrationHistory(
  probeId: number,
  limit: number = 20,
  enabled: boolean = true
): UseQueryResult<CalibrationHistoryResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.polarizationHistory(probeId),
    queryFn: () => probeCalibrationService.getPolarizationCalibrationHistory(probeId, limit),
    enabled,
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
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.pattern(probeId) })
        queryClient.invalidateQueries({ queryKey: probeCalibrationKeys.probeData(probeId) })
      })
      queryClient.invalidateQueries({ queryKey: [...probeCalibrationKeys.all, 'validity'] })
    },
  })
}

/**
 * Hook to get pattern calibration for a probe
 */
export function usePatternCalibration(
  probeId: number,
  frequencyMhz?: number,
  enabled: boolean = true
): UseQueryResult<PatternCalibrationResponse[], Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.pattern(probeId, frequencyMhz),
    queryFn: () => probeCalibrationService.getPatternCalibration(probeId, frequencyMhz),
    enabled,
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
  probeIds?: string,
  enabled: boolean = true
): UseQueryResult<CalibrationValidityReport, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.validityReport(probeIds),
    queryFn: () => probeCalibrationService.getValidityReport(probeIds),
    enabled,
  })
}

/**
 * Hook to get expiring calibrations
 */
export function useExpiringCalibrations(
  days: number = 7,
  calibrationType?: CalibrationType,
  enabled: boolean = true
): UseQueryResult<ExpiringCalibrationsResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.expiring(days, calibrationType),
    queryFn: () => probeCalibrationService.getExpiringCalibrations(days, calibrationType),
    enabled,
  })
}

/**
 * Hook to get expired calibrations
 */
export function useExpiredCalibrations(
  calibrationType?: CalibrationType,
  enabled: boolean = true
): UseQueryResult<ExpiredCalibrationsResponse, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.expired(calibrationType),
    queryFn: () => probeCalibrationService.getExpiredCalibrations(calibrationType),
    enabled,
  })
}

/**
 * Hook to get validity status for a single probe
 */
export function useProbeValidity(
  probeId: number,
  enabled: boolean = true
): UseQueryResult<ProbeCalibrationStatus, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.probeValidity(probeId),
    queryFn: () => probeCalibrationService.getProbeValidity(probeId),
    enabled,
  })
}

/**
 * Hook to invalidate a calibration
 */
export function useInvalidateCalibration(): UseMutationResult<
  InvalidateCalibrationResponse,
  Error,
  { calibrationType: CalibrationType; calibrationId: string; request: InvalidateCalibrationRequest }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ calibrationType, calibrationId, request }) =>
      probeCalibrationService.invalidateCalibration(calibrationType, calibrationId, request),
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
  probeId: number,
  enabled: boolean = true
): UseQueryResult<ProbeCalibrationData, Error> {
  return useQuery({
    queryKey: probeCalibrationKeys.probeData(probeId),
    queryFn: () => probeCalibrationService.getProbeCalibrationData(probeId),
    enabled,
  })
}
