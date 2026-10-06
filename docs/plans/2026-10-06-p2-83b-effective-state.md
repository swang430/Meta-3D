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

- [x] RED：执行器记录`save → committed → activate`；保存异常没有后续事件，激活异常保留committed结果。
  ```ts
  assert.deepEqual(events, ['save', 'committed', 'activate'])
  ```
- [x] 最小GREEN：`commitThenActivateCategory(category,commit,activate,onCommitted?)`在commit返回后同步onCommitted；App onMutate记录处理中，回调记录已保存/激活中，最终回调存回执或错误。展示清晰阶段、当前保存endpoint/型号/驱动模式、草稿dirty、BS/CE同labbinding；无对应投影保持未知。
  ```ts
  const committed = await commit()
  onCommitted?.(committed)
  // 仍只在原try内消费activate异常
  ```
- [ ] 浏览器RED→GREEN：草稿改endpoint仍展示旧保存值；PUT失败不POST；PUT成功POST409为已保存但激活失败；inactive不能显示已加载；binding错误/模拟/无选择不绿，切类别不串回执。
- [x] 定点契约与build；Task1/2共同状态消费端在同一实现提交收口，设计/计划已先独立提交。

## Task2：总览保存资源与最终验证

- [x] 目录读取RED：总览显示全局保存配置并明确不是Lab绑定；503/paused/刷新不展示旧保存成功。无Lab不额外读取总览。
- [x] GREEN：enabled绑定Lab与context，复用catalog query key、fetchInstrumentCatalog；只GET，刷新同时refetch目录/readiness/RF。失败优先于cache。
- [ ] 真实App两Lab切换、四子视图、故障/恢复；核心变异：去掉onCommitted阶段、总览目录错误沿用缓存，实跑RED并恢复。
- [x] GUI相关契约、完整GUI基准对照、build、rule gates、diff-check。B为局部GUI档不机械跑后端全量。
- [ ] 独立内审/修复复审，推送Ready PR，R1处理本片P1/P2→R2，最新HEAD无P1且条件通过合并同步清理，再启动C。

C在B合并后的最新main独立工作树按已批准设计写精确端点/锁内版本比较与确认流程计划，不在B混入同步写行为。

## 本地验证与审查记录（2026-10-06）

基准`9878c87a`，设计/计划HEAD `e2e7c992`加本片受控代码、测试增量；只复用未提交依赖链接，不改依赖。最终提交SHA与外审请求/实际审查HEAD见PR台账；下面是软件验证，不是现场验收。

- `npx --yes tsx --test gui/src/features/Equipment/categoryHalActivation.test.ts`：旧实现12 tests/11 pass/1 fail，回调顺序缺committed；最小实现12 pass。
- Playwright真实App `p2_83bEffectiveState.browser.js`：最终8场景通过，含草稿与保存值分列、PUT拒绝无POST、保存后激活等待、激活409、inactive回执、全局模式切换刷新、总览目录503拒绝缓存及恢复。只替HTTP/WS，不接硬件。
- 内审两条功能P2已收口：commit成功边界立即刷新目录（保存与driver-mode对称）；全局switch/reload/force共用路径刷新readiness。两条各用真实App旧实现RED→修复GREEN，独立复审CLEAN。
- 原工作台两Lab/身份冲突/模拟/未知/离线/四子视图回归14组通过、配置写请求0。阶段回调的核心RED与总览失败继续展示缓存变异exit 1均已检出；总览代码精确恢复后8场景和build再通过。
- 完整GUI命令：`npx --yes tsx --test $(rg --files gui/src gui/test | rg '\.test\.(ts|tsx)$')`。本片286 tests/277 pass/9 fail；当前main同命令284/275/9，相同9项既有失败，未宣称全绿。
- `npm --prefix gui run build`恢复后exit 0；`.venv/bin/python -m pytest tests/test_rule_gates.py -q --color=no`为70 passed；`git diff --check`通过。B不改后端共享契约，不重复全后端。
- NotebookLM不适用：本片无新增/修改仪器命令、参数域、单位或前置条件。C锁内确认版本及独立重试未实现。

实跑输出保存在`/tmp/p283b-*`；旧源码形状断言失败按AGENTS最高P2规则披露，不为测试扩大本片功能范围。尚未完整穷举每个类别的新面板浏览器状态；按类别索引隔离及BS/CE身份判据已独立读码核实，不把未实跑场景写成实跑通过。
