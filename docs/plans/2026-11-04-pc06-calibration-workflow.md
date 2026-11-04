# PC-06 完整校准接线与分步操作

用户已批准连续实施；状态只维护在 roadmap 的 PC 专项队列，本文件定义验收范围。

## PC-06A-3：接线与仪器

生产入口 TopologyEditor → 原保存图及服务端 RouteSelection → 画布与仪器详情。
显示当前模式加校准支路；孤立校准仪器也显示为接线未完整，绝不自动生成实物连接。
F64 内部单音源配分析仪是现有采集方法；VNA及独立信号源可声明接线，不因此开放自动采集。
仪器资源目录、当前 Lab 绑定、HAL 快照分别展示；读取失败、刷新中、身份不符不展示旧状态为当前事实。
点击仪器资源入口复用原页面。物理接线仍由本次操作员确认。
不新增 SCPI；NotebookLM 仪器语义查询不适用，方法边界直接引用现有 fixed_route_jobs。

## PC-06A-4：三步入口

准备、采集、审阅与采用三个操作阶段，复用 RouteCalibrationPanel / RouteBatchPanel。
单项与批量使用一个选择入口；表单只显示所选方式，活动作业、取消、未知回执恢复不因切换步骤消失或卸载。
单项与逐项候选语义保持区别，不能把 individual 候选交给同时通路接口。
复用服务端采用预览，不本地重算资格、差值或证书期限。

## PC-06A-5：结果与证据

结果摘要显示路径/频点、采集结论、损耗、重复性、清理与采用状态。
原始回复、冻结配置和标识放入证据详情；历史独立展开，撤销在采用记录详情。
失败原因、清理未知、人工等待始终可见；模拟不能标为实测或正式可用。

## 验证与交付

逐片独立内审、相关行为测试、构建和浏览器；变异验证关键行为，避免仅查文本存在。
重点覆盖：缺仪器/缺边、刷新失败或错 Lab、模拟、运行中切换视图、未知回执恢复、取消、人工等待、不可采用。
GUI 投影不改后端采集；若必须修改共享后端契约，先明确范围并运行相应回归。
各片 R1/R2；R2 有 P1 则修复后继续到最新 HEAD 无 P1，之后合并并同步本地主仓库。

## PC-06A-3 本片验证

- `npx --yes tsx --test test/calibrationChainView.test.ts test/topologyDraft.test.ts test/pc04a2RouteCalibration.test.ts test/pc06a1Batch.test.ts`（gui目录）：52 tests，52 pass，0 fail。
- `npm run build`：TypeScript与Vite构建通过。
- `playwright-cli -s=pc06 run-code --filename gui/test/pc06CalibrationChain.browser.js`：真实App、HTTP隔离夹具，完整参考支路（含普通pad）、孤立矢网/信号源、错Lab/失败未知、展示只读、草稿阻断快捷导航四组通过。不是真机验证。
- 逆变异将 `calibrationCanvasConnections` 的显示条件反转，`node --experimental-strip-types --test gui/test/calibrationChainView.test.ts` 非零退出；finally双向核对并恢复原文。未修改设备与实测数据。
- 内审F1导航保护、F2普通校准中间节点及同源器件列表均已修正；原启动/停发/采用后端未变。
