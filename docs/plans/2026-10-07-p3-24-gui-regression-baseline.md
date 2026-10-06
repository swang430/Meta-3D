# P3-24 实施计划与验证记录

> 执行方式：主代理顺序实施，使用 executing-plans；提交前按 requesting-code-review 做只读独立内审。用户已批准连续完成，不重复征求开工批准。

**目标**：修复已复现的九项 GUI 基线噪音，不降低原核心保护。
**架构**：仅现有 node:test、assert 与 Playwright CLI；不新增测试平台/依赖/产品机制。
**技术栈**：TypeScript、tsx、Node test runner、Vite、现有 App 浏览器载体。
**设计**：[范围与逐项裁决](../design/2026-10-07-p3-24-gui-regression-baseline.md)。

## 全局约束

不删除、skip 或放宽断言凑绿；真实产品缺陷独立 triage；不改变 SCPI、HAL、冻结、KPI 和 provenance。测试/门意见等级不高于 P2。

## Task 1：加载与预期的最小维护

- [x] 基准完整命令先跑，退出1，292/283/9；日志 `/tmp/p324-gui-baseline.log`。
- [x] 对设计表八个测试文件逐项修复；保留断言语义，不改生产。
- [x] `channelHal` 使用 `import test from 'node:test'` 与 `assert.deepEqual(await hal.connect(...), {ok:true})`，transport 记录命令参数并提供明确 status；HAL 的失败映射由 transport 拒绝实证，原 MockDriver 生命周期断言亦保留。
- [x] LTE fixture 补 `lte_transmission_mode: 'TM3'`，期待同值；缺省删除时断言 `primaryCarrierIdentity(...) === null`。
- [x] 不依赖 cwd 的源码读取为 `readFileSync(new URL('../src/api/service.ts', import.meta.url), 'utf8')`。
- [x] 全 GUI 命令 GREEN，给出实际总数、退出码与耗时。

## Task 2：保护与真实交互

- [x] 原功能定点回退：GCM→ASC、readiness 错加 Lab 非空门、HAL start 下发误成 stop，各只跑对应文件；均失败，apply_patch 还原后生产文件 diff 为空。HAL 变异直接证明新增边界断言，替代原拟定 positioner 变异。
- [x] 在5198启动独立Vite，使用已存浏览器脚本验证真实 App 保存失败/分类激活/显式同步及实验室工作单元；HTTP/WS替换，不是硬件证据。
- [x] `cd gui && npm run build`；更新 roadmap 当前条目与 P2-85 合并镜像；`git diff --check`。

## Task 3：交付

- [x] 只读独立内审 CLEAN，覆盖基准至63d71fef；验证档位为测试维护/GUI构建，不重复后端全量。后续文档增量不改变测试输入。
- [ ] 提交、推送、Ready PR；核远端/PR HEAD一致，读三通道后触发R1→R2。
- [ ] 最新HEAD R2无P1且可合并/checks满足后merge commit；fetch、main ff-only同步，仅清理本片工作树/本地分支及依赖链接。

## 记录

验证环境：Node v26.5.1、npm11.17.0、tsx4.23.15，沿用本机现有 gui/node_modules；无依赖文件变更。基准已记录，当前版本为基准加本片八个测试文件，只有文档增量不参与测试。

| 命令与输出 | 退出码 / 实际结尾 |
|---|---|
| 根目录完整命令（设计中列原文），原始 baseline | 1；292 tests / 283 pass / 9 fail，1135.938166 ms |
| 同命令修复后最终、变异还原后 | 0；295 tests /295 pass /0 fail /0 skip，680.19925 ms；`/tmp/p324-gui-restored.log` |
| `npx --yes tsx --test gui/test/lteOperatingPointTruth.test.ts`，GCM变异 | 1；4 tests /3 pass /1 fail，78.595167 ms |
| `npx --yes tsx --test gui/test/baseStationCompatibilityReadiness.test.ts`，readiness变异 | 1；5 tests /4 pass /1 fail，57.003833 ms |
| `npx --yes tsx --test gui/test/channelHal.test.ts`，HAL变异 | 1；2 tests /1 pass /1 fail，79.586542 ms |
| `cd gui && npm run build` | 0；built in13.70s；已有大chunk警告未消除 |
| `playwright_cli.sh -s=p324 run-code --filename gui/test/p2_83bEffectiveState.browser.js` | 0；Result passed14 /activations4，真实App |
| 同载体 `gui/test/labWorkspace.browser.js` | 0；Result passed14 /writes[]，真实App |

运行位置均为本片隔离工作树。新增总数解释：positioner加载错误原只计一个文件失败，现在3个内部测试；channelHal文件失败原计1个，现在2个可执行测试。全部原保护保留，因此292→295，不是删失败。
中间一次 channelHal 转换引入语法错误（`Unexpected ')'`），已最小修复；没有把中间失败当最终通过。浏览器的预期503/422/409/offline场景可输出console error，不等于未捕获产品异常。

验证责任人主代理；后端全量不适用：无后端/共享行为/依赖/生成契约输入变化。不用前片后端结果冒充本片实跑。独立内审 CLEAN；GitHub外审与合并的请求、覆盖SHA和消费时刻以[PR #511](https://github.com/swang430/Meta-3D/pull/511)台账为唯一交付入口，不为填写合并时间制造新待审提交。根目录与gui目录完整GUI均295/295、零skip；gui目录耗时718.909792ms。变异完全还原后复跑实验室工作单元浏览器载体，仍14场景通过且writes为空。
