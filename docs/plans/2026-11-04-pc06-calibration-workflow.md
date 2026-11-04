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

R1指出两套校准声明不能无条件并集，已换源为原 `getDraftModeConnectionIds`，显式清单优先，旧边标签只在空清单时回退；新增排除边回归。

R1修复后相关53/53通过；复活排除边的逆变异失败并恢复。浏览器四组重跑通过（允许应用自身错误日志上报，不允许仪器/校准写操作）。最终构建在变异恢复后独立执行。

## PC-06A-4 实现边界补充

固定接线单项可在缺线缆资料时仅留原始证据；清单采集要求完整参考量且可能执行已核验开关切换。因此保留一个采集方式选择，默认MIMO清单（支持1×1），固定接线方式显式保留；不把二者伪装成相同硬件动作。
两个组件始终挂载，只隐藏非当前准备表单；所有活动、取消、人工确认和未知回执恢复保持可达。固定接线历史、批子项进入审阅时保留原run和chain身份，采用仍消费原服务器预览。

## PC-06A-4 验证

- `npx --yes tsx --test gui/test/pc04a2RouteCalibration.test.ts gui/test/pc06a1Batch.test.ts gui/test/pc04a8MockCalibration.test.ts`：37/37通过；原资格、恢复与模拟边界未变。
- `playwright-cli -s=pc06 run-code --filename gui/test/pc06CalibrationSteps.browser.js`：真实App、隔离HTTP，六组通过：步骤保持输入，1×1清单预览/启动，人工及取消常驻，取消后审阅，固定接线保留，采用未知回执跨步骤可见。不是后端／真机验证。
- 逆变异强制固定接线准备表单常显，浏览器报“两套准备表单同时显示”，非零退出；finally核对并恢复，构建在恢复后独立执行。
- 内审修正：采用写入回执与核对常驻；去掉批列表刷新后的迟到步骤切换；未选择run时不主动刷新无身份的采用接口。

## PC-06A-5 实现边界补充

重复性只显示原结果的样本标准差，不表示完整不确定度。批结果要求同Lab/run/批项/父批，子记录刷新失败或未读不取旧缓存补数。
只折叠只读历史、原始证据与模拟明细；撤销组件的状态、在途／失败和核对入口留在外面，表单沿原组件自己的详情折叠。

## PC-06A-5 验证

- `npx --yes tsx --test gui/test/calibrationResultView.test.ts gui/test/pc04FixedRoute.test.ts gui/test/pc04a8MockCalibration.test.ts gui/test/pc04a2RouteCalibration.test.ts gui/test/pc06a1Batch.test.ts`：45/45通过。
- `playwright-cli -s=pc06 run-code --filename gui/test/pc06CalibrationSteps.browser.js`：真实App/隔离HTTP八组通过，延续三步六组并覆盖标准差摘要、证据折叠、模拟数值不进入正式摘要与采用禁用。无硬件访问。
- 去掉重复性显示的 `measured` 条件，`npx --yes tsx --test gui/test/calibrationResultView.test.ts` 失败；finally双向核对恢复。恢复后独立构建通过。
- 独立累计内审及模拟详情增量复审无功能缺陷。撤销警示没有被历史折叠隐藏。

三片只完成软件交付，未执行真实校准或现场验收；PC-06B及其他未验证范围继续保留。
