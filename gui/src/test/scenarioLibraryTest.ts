/**
 * 场景库数据测试
 *
 * 验证10个场景的数据完整性和辅助函数功能
 */

import { scenarioList, getScenarioById, filterScenarios, getScenarioStatistics } from '../data/scenarioLibrary'

console.log('========== 场景库数据测试 ==========\n')

// 测试1: 场景列表长度
console.log('测试1: 场景列表长度')
console.log(`场景总数: ${scenarioList.length}`)
console.log(`预期: 10`)
console.log(`结果: ${scenarioList.length === 10 ? '✅ 通过' : '❌ 失败'}\n`)

// 测试2: 场景ID唯一性
console.log('测试2: 场景ID唯一性')
const ids = scenarioList.map(s => s.id)
const uniqueIds = new Set(ids)
console.log(`唯一ID数量: ${uniqueIds.size}`)
console.log(`结果: ${uniqueIds.size === 10 ? '✅ 通过' : '❌ 失败'}\n`)

// 测试3: 数据完整性检查
console.log('测试3: 数据完整性检查')
let allComplete = true
scenarioList.forEach(scenario => {
  if (!scenario.isComplete) {
    console.log(`❌ 场景 ${scenario.id} 数据不完整`)
    allComplete = false
  }
})
console.log(`结果: ${allComplete ? '✅ 所有场景数据完整' : '❌ 部分场景数据不完整'}\n`)

// 测试4: getScenarioById 函数
console.log('测试4: getScenarioById 函数')
const scenario001 = getScenarioById('scenario-001')
console.log(`获取 scenario-001: ${scenario001 ? scenario001.name : '未找到'}`)
console.log(`结果: ${scenario001 && scenario001.name === '北京CBD早高峰通勤' ? '✅ 通过' : '❌ 失败'}\n`)

// 测试5: 场景详情结构
console.log('测试5: 场景详情结构完整性')
if (scenario001) {
  const hasNetwork = !!scenario001.networkConfig
  const hasTrajectory = !!scenario001.trajectory
  const hasEnvironment = !!scenario001.environment
  const hasTraffic = !!scenario001.traffic
  const hasKPI = scenario001.kpiTargets && scenario001.kpiTargets.length > 0

  console.log(`网络配置: ${hasNetwork ? '✅' : '❌'}`)
  console.log(`轨迹定义: ${hasTrajectory ? '✅' : '❌'}`)
  console.log(`环境条件: ${hasEnvironment ? '✅' : '❌'}`)
  console.log(`流量模型: ${hasTraffic ? '✅' : '❌'}`)
  console.log(`KPI目标: ${hasKPI ? '✅' : '❌'}`)

  const allPresent = hasNetwork && hasTrajectory && hasEnvironment && hasTraffic && hasKPI
  console.log(`结果: ${allPresent ? '✅ 通过' : '❌ 失败'}\n`)
}

// 测试6: filterScenarios 函数
console.log('测试6: filterScenarios 函数')
const urbanScenarios = filterScenarios({ geographyType: 'urban' })
console.log(`城市场景数量: ${urbanScenarios.length}`)
console.log(`预期: 4`)
console.log(`结果: ${urbanScenarios.length === 4 ? '✅ 通过' : '❌ 失败'}\n`)

const realWorldScenarios = filterScenarios({ source: 'real-world' })
console.log(`真实场景数量: ${realWorldScenarios.length}`)
console.log(`预期: 4-5`)
console.log(`结果: ${realWorldScenarios.length >= 4 && realWorldScenarios.length <= 5 ? '✅ 通过' : '❌ 失败'}\n`)

// 测试7: 统计信息
console.log('测试7: getScenarioStatistics 函数')
const stats = getScenarioStatistics()
console.log(`统计信息:`)
console.log(`  总数: ${stats.total}`)
console.log(`  真实场景: ${stats.bySource.realWorld}`)
console.log(`  合成场景: ${stats.bySource.synthetic}`)
console.log(`  城市场景: ${stats.byGeography.urban}`)
console.log(`  高速场景: ${stats.byGeography.highway}`)
console.log(`  基础复杂度: ${stats.byComplexity.basic}`)
console.log(`  中等复杂度: ${stats.byComplexity.intermediate}`)
console.log(`  高级复杂度: ${stats.byComplexity.advanced}`)
console.log(`  极限复杂度: ${stats.byComplexity.extreme}`)
console.log(`结果: ${stats.total === 10 ? '✅ 通过' : '❌ 失败'}\n`)

// 测试8: 射线跟踪数据
console.log('测试8: 射线跟踪数据检查')
let rayTracingCount = 0
scenarioList.forEach((scenario, index) => {
  const detail = getScenarioById(scenario.id)
  if (detail?.rayTracingOutput) {
    console.log(`  ✅ ${scenario.id}: ${scenario.name} - ${detail.rayTracingOutput.tool}`)
    rayTracingCount++
  }
})
console.log(`射线跟踪场景数量: ${rayTracingCount}`)
console.log(`预期: 2-3`)
console.log(`结果: ${rayTracingCount >= 2 && rayTracingCount <= 3 ? '✅ 通过' : '❌ 失败'}\n`)

// 测试9: 场景分类标签
console.log('测试9: 场景分类标签完整性')
let allHaveTaxonomy = true
scenarioList.forEach(scenario => {
  if (!scenario.taxonomy ||
      !scenario.taxonomy.source ||
      !scenario.taxonomy.geographyType ||
      !scenario.taxonomy.network) {
    console.log(`❌ 场景 ${scenario.id} 缺少分类标签`)
    allHaveTaxonomy = false
  }
})
console.log(`结果: ${allHaveTaxonomy ? '✅ 通过' : '❌ 失败'}\n`)

// 测试10: 可执行性标记
console.log('测试10: 可执行性标记')
let otaCount = 0
let conductedCount = 0
let digitalTwinCount = 0
scenarioList.forEach(scenario => {
  if (scenario.canExecute.ota) otaCount++
  if (scenario.canExecute.conducted) conductedCount++
  if (scenario.canExecute.digitalTwin) digitalTwinCount++
})
console.log(`OTA可执行: ${otaCount}/10`)
console.log(`传导可执行: ${conductedCount}/10`)
console.log(`数字孪生可执行: ${digitalTwinCount}/10`)
console.log(`结果: ${otaCount >= 9 && digitalTwinCount >= 9 ? '✅ 通过' : '❌ 失败'}\n`)

console.log('========== 测试完成 ==========')
