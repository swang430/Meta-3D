# P2-83B 实施计划

> 主代理使用executing-plans顺序实施；独立审查只读，不并行开发。

目标：将草稿、已保存资源、HAL最近操作结果与当前运行/执行绑定明确分列。
设计：[B/C批准设计](../design/2026-10-06-p2-83bc-effective-workflow.md)。React/Mantine/TanStack Query，无新增依赖。

## 约束与文件职责

不改后端、API四镜像、SCPI、正式provenance或历史freeze。原编辑器仍卸载，不新增草稿持久化。最近操作回执仅本页、本类别，并标明是回执，不等于当前运行真值。

- App.tsx（修）：EquipmentManager保存/激活各阶段回调及抽屉状态面板，不复制resolver。
- categoryHalActivation.ts（修）：可选onCommitted回调在PUT成功后、POST激活前触发，不吞保存异常。
- EquipmentEffectiveState.tsx（新，修）：展示单类别草稿/服务器保存值/最近回执/当前binding；只消费props，不发写请求。
- LabOverview.tsx（修）：目录GET当前保存资源分列；沿用既有readiness/RF链路。
- categoryHalActivation.test.ts、p2_83bEffectiveState.browser.js（修）：真实执行顺序与真实App故障状态；仅替换HTTP。
- roadmap与设计/计划（修）：同步A交付、B进度；C未实现。

## Task1：阶段回执与仪器状态

- [ ] RED：执行器记录`save → committed → activate`；保存异常没有后续事件，激活异常保留committed结果。
  ```ts
  assert.deepEqual(events, ['save', 'committed', 'activate'])
  ```
- [ ] 最小GREEN：`commitThenActivateCategory(category,commit,activate,onCommitted?)`在commit返回后同步onCommitted；App onMutate记录处理中，回调记录已保存/激活中，最终回调存回执或错误。展示清晰阶段、当前保存endpoint/型号/驱动模式、草稿dirty、BS/CE同labbinding；无对应投影保持未知。
  ```ts
  const committed = await commit()
  onCommitted?.(committed)
  // 仍只在原try内消费activate异常
  ```
- [ ] 浏览器RED→GREEN：草稿改endpoint仍展示旧保存值；PUT失败不POST；PUT成功POST409为已保存但激活失败；inactive不能显示已加载；binding错误/模拟/无选择不绿，切类别不串回执。
- [ ] 定点契约与build后提交Task。

## Task2：总览保存资源与最终验证

- [ ] 目录读取RED：总览显示全局保存配置并明确不是Lab绑定；503/paused/刷新不展示旧保存成功。无Lab不额外读取总览。
- [ ] GREEN：enabled绑定Lab与context，复用catalog query key、fetchInstrumentCatalog；只GET，刷新同时refetch目录/readiness/RF。失败优先于cache。
- [ ] 真实App两Lab切换、四子视图、故障/恢复；核心变异：去掉onCommitted阶段、总览目录错误沿用缓存，实跑RED并恢复。
- [ ] GUI相关契约、完整GUI基准对照、build、rule gates、diff-check。B为局部GUI档不机械跑后端全量。
- [ ] 独立内审/修复复审，推送Ready PR，R1处理本片P1/P2→R2，最新HEAD无P1且条件通过合并同步清理，再启动C。

C在B合并后的最新main独立工作树按已批准设计写精确端点/锁内版本比较与确认流程计划，不在B混入同步写行为。
