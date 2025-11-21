/**
 * TanStack Query hooks for Sequence Library
 */

import { useQuery } from '@tanstack/react-query'
import type { SequenceLibraryItem, SequenceLibraryFilters } from '../types'
import * as api from '../api/testManagementAPI'

// Query Keys
export const sequenceLibraryKeys = {
  all: ['test-management', 'sequence-library'] as const,
  lists: () => [...sequenceLibraryKeys.all, 'list'] as const,
  list: (filters?: SequenceLibraryFilters) => [...sequenceLibraryKeys.lists(), filters] as const,
  details: () => [...sequenceLibraryKeys.all, 'detail'] as const,
  detail: (id: string) => [...sequenceLibraryKeys.details(), id] as const,
  categories: () => [...sequenceLibraryKeys.all, 'categories'] as const,
  popular: (limit?: number) => [...sequenceLibraryKeys.all, 'popular', limit] as const,
}

// ==================== Queries ====================

/**
 * Hook to fetch sequence library items with filters
 */
export function useSequenceLibrary(filters?: SequenceLibraryFilters) {
  return useQuery({
    queryKey: sequenceLibraryKeys.list(filters),
    queryFn: () => api.getSequenceLibrary(filters),
    staleTime: 300000, // 5 minutes (library rarely changes)
  })
}

/**
 * Hook to fetch a single sequence library item
 */
export function useSequenceLibraryItem(itemId: string | undefined) {
  return useQuery({
    queryKey: sequenceLibraryKeys.detail(itemId!),
    queryFn: () => api.getSequenceLibraryItem(itemId!),
    enabled: !!itemId,
    staleTime: 300000, // 5 minutes
  })
}

/**
 * Hook to fetch sequence library categories
 */
export function useSequenceCategories() {
  return useQuery({
    queryKey: sequenceLibraryKeys.categories(),
    queryFn: api.getSequenceCategories,
    staleTime: 600000, // 10 minutes
  })
}

/**
 * Hook to fetch popular sequence library items
 */
export function usePopularSequences(limit: number = 10) {
  return useQuery({
    queryKey: sequenceLibraryKeys.popular(limit),
    queryFn: () => api.getPopularSequences(limit),
    staleTime: 300000, // 5 minutes
  })
}
