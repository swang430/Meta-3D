// 临时fallback处理 - 对未实现的端点返回空数据而不是404错误

/**
 * Get all steps for a test plan - 临时返回空数组（后端未实现）
 */
export const getTestSteps = async (planId: string): Promise<TestStep[]> => {
  try {
    const response = await client.get<{ steps: TestStep[] }>(
      `/v1/test-plans/${planId}/steps`,
    )
    return response.data.steps
  } catch (error) {
    console.warn('Steps endpoint not implemented, returning empty array')
    return []
  }
}

/**
 * Get execution history - 临时返回空数组（后端未实现）
 */
export const getExecutionHistory = async (
  filters?: HistoryFilters,
): Promise<TestExecutionRecord[]> => {
  try {
    const response = await client.get<{ items: TestExecutionRecord[] }>(
      '/v1/test-executions',
      { params: filters },
    )
    return response.data.items
  } catch (error) {
    console.warn('Execution history endpoint not implemented, returning empty array')
    return []
  }
}

/**
 * Get sequence library - 临时返回空数组（后端未实现）
 */
export const getSequenceLibrary = async (
  filters?: SequenceLibraryFilters,
): Promise<SequenceLibraryItem[]> => {
  try {
    const response = await client.get<{ items: SequenceLibraryItem[] }>(
      '/v1/test-sequences',
      { params: filters },
    )
    return response.data.items
  } catch (error) {
    console.warn('Sequence library endpoint not implemented, returning empty array')
    return []
  }
}

/**
 * Get sequence categories - 临时返回空数组（后端未实现）
 */
export const getSequenceCategories = async (): Promise<string[]> => {
  try {
    const response = await client.get<{ categories: string[] }>(
      '/v1/test-sequences/categories',
    )
    return response.data.categories
  } catch (error) {
    console.warn('Sequence categories endpoint not implemented, returning empty array')
    return []
  }
}
