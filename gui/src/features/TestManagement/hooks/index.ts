/**
 * Unified Test Management Hooks
 *
 * ARCH-1 S4a: 计划链拆除后这里只剩执行历史一个 hook。
 * 原有的 useTestPlans / useTestSteps / useTestQueue / useTestExecution /
 * useSequenceLibrary / useStatistics 六组随计划链一并删除 —— 它们只服务于
 * PlansTab / StepsTab / QueueTab, 那三个 Tab 已不存在。
 * (其中后三组在删除前就已经只被本文件引用, 是既有死代码。)
 *
 * 用例的执行入口在 TestCaseLibrary (ARCH-1 S1), 不走这里。
 *
 * @example
 * import { useTestHistory } from '@/features/TestManagement/hooks'
 */

// Test History (ARCH-1 S2 换源到 test_executions 本表)
export {
  useTestHistory,
  testHistoryKeys,
} from './useTestHistory'
