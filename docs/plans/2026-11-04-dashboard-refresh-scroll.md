# 主控台刷新导致整页滚动跳动修复

来源：用户实测报告，明确是整个页面而非日志框。memory已查当前工作流；NotebookLM不适用（不涉仪器语义）。
范围：只修ZoneReadiness后台刷新移除内容引发页面高度塌缩；同一Lab保留已确认布局高度，不保留旧就绪结论。
不做：不改日志自动滚动、轮询频率、后端与就绪判据；不保存/强行恢复整个页面scrollTop。
验收：慢刷新、失败/恢复、离线时旧结论仍隐藏；页面阅读位置不因临时高度塌缩跳动，窗口尺寸变化后仍有效。

## 根因与方案

基线4f574fac。真实DashboardCockpit+OperationalLabProvider隔离HTTP，1280×720浏览器、600px主滚动区，readiness第二次响应延迟700ms：主内容高度853→611，scrollTop253→11；每10秒的fetchStatus变化使readiness暂为undefined，移除整组卡片和子网。独立日志测试只使日志内部450→0，外页650不动，故不修改那条行为。

修法：只记录同Lab已发布就绪卡片的实际像素高度，未确认新快照时保留min-height。ResizeObserver跟随响应式布局记录高度；不缓存或发布业务判词，切Lab不继承高度。只改一个显示组件，不新增滚动恢复或业务状态机制。保留高度无法用固定常量可靠替代（卡片列数、子网数量可变），也不能通过放行旧就绪数据避免塌缩。

验证档位：局部GUI布局，浏览器可观察RED/GREEN、相关GUI测试及production build；无后端/契约变化，不跑后端全量。独立计划/实现审查及GitHub R1/R2。此片为用户直接报告的运行故障修复，明确申报roadmap外，不另起功能编号。

## 实跑结果

- 生产改动限定ZoneReadiness，原readiness判据不变；临时复现入口已移出仓库。
- 完整App隔离HTTP浏览器（实际AppShell与Query）普通窗口start/pending/end均383；checked-in `gui/test/dashboardRefreshScroll.browser.js` 五场景通过：周期刷新、失败恢复、离线恢复、响应式高度、切Lab。普通窗口383、窄窗口758，10次readiness请求。命令：`/Users/Simon/.codex/skills/playwright/scripts/playwright_cli.sh -s=scrollverified run-code --filename gui/test/dashboardRefreshScroll.browser.js`，exit0，/tmp/dashboard-scroll-browser4.log。仅HTTP被替换，不称真机或用户服务实测。
- 首次脚本受前一轮在途路由影响报already handled；两轮双Lab fixture缺chamber绑定导致未选择上下文，未计通过。依据实际选择器契约补fixture绑定后，干净会话完成上述五场景。
- gui目录 `node --experimental-strip-types --test src/features/Dashboard/*.test.ts`：17 passed/0 failed，186.70ms，/tmp/dashboard-scroll-tests.log；`npm run build` exit0，19.69s，/tmp/dashboard-scroll-build.log，原chunk警告保留。
- 此修复仅消除刷新撤下内容造成的临时高度塌缩；实际新快照内容变化或用户改变窗口尺寸本身可能改变布局，不承诺固定所有情况下的绝对滚动坐标。
- 核心逆变异：仅移除Card的mih，真实浏览器在周期刷新断言报「周期刷新使整页阅读位置跳动」，CLI exit1，/tmp/dashboard-scroll-mutation.log；finally双向assert逐字恢复源码。原生产build输入未改。
