# PC-04A-9 编辑空间软件验证摘要

基线 `5ec92e78a87760494620f2e02d6ecde7a680bd85`；分支 `codex/pc04a9-expanded-calibration-workspace`。仅修改 `TopologyEditor.tsx` 的布局、对应真实浏览器行为测试、现有指南与本摘要/roadmap。无后端、契约、依赖或图数据变更；按局部GUI档验证，不跑后端全量。仪器语义/NotebookLM不适用。实施者自查不等于独立内审，独立审查及单PR外审仍待主控接续。

## 行为与尺寸

普通编辑框为原窗口可用框高的3倍；测量补回滚动祖先的 scrollTop，仅观察上方配置卡及窗口，不观察自身撑大的父容器。专注仍使用窗口内可用空间，不作3倍承诺。专注不改变辅助区选择；校准单独展开只改同一 aside 的CSS，不更换组件、key、图或请求身份。

相同窗口和顶部位置下的真实DOM尺寸（px）：

| viewport | 原普通编辑框 | 新普通编辑框 | 原ReactFlow画布 | 新ReactFlow画布/校准栏 |
|---|---:|---:|---:|---:|
| 1800×1200 | 710.422 | 2131.266 | 396.234 | 1817.078 / 1817.078 |
| 1100×800 | 280（原最小框高） | 840 | 2（原工具栏挤压） | 405.016 / 405.016 |

宽屏实际画布约4.59倍；窄屏不只验证倍数，也实际滚到画布、定位全图，确认约388px宽×405px高的可操作区域。普通长页面允许整页滚动。专注宽屏画布约1358×854，窄屏约658×385；校准独立展开内容区分别约1768×1112、1068×712。顶部返回入口固定在内容滚动区外；返回后可退出专注。专注中既有修订历史弹窗能打开并关闭。

## 验证结果

- 新增 `gui/test/pc04a9Workspace.browser.js` 在真实页面先RED：3项失败，分别抓到未增高、专注隐藏校准栏、缺少展开入口；实现后及最终复核均3项通过。调用方式为持久Playwright会话导入该函数，对已选中synthetic通路的真实页面执行 `verifyWorkspace(page,{baselineHeight:396.234375,red:true})` / 去掉 `red`。不伪造响应、不调用React handler。
- 真实浏览器覆盖：普通/专注/独立展开/返回、宽窄窗口、同一panel DOM实例与频率2595保留；辅助区隐藏后专注仍隐藏、展开后返回仍隐藏；滚动600px再往返调整窗口后编辑框与画布高度无漂移。观察期间无pageerror或ResizeObserver循环。
- 真实历史GET仅增加6000ms网络延迟，不替换响应：切换布局前后均 `data-loading=true`、同一panel、仅1次请求，最终真实200/空历史；输入仍为2595。这是**历史请求在途**，不是硬件采集在途证明。
- 自动排版产生的真实本地草稿在切换后位置及dirty状态保留，未触发任何写请求；最终GET与初始GET逐值相同。另以真实离线保存演练验证结果未知锁，布局切换后排版及校准输入仍禁用；重新加载沿既有边界回到服务器基线，不宣称跨SPA保留未知锁。
- 相关GUI回归命令（cwd `gui`）：`npx --no-install tsx --test test/topologyLayout.test.ts test/topologyDraft.test.ts test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyPortContract.test.ts test/topologyInternalPaths.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts src/features/TopologyEditor/*.test.ts`。**83 tests / 83 pass / 0 fail / 0 skipped，1373.68975ms，exit 0**。
- `npm run build`：**exit 0，11.84s**；保留axios与service动态/静态混用导入提示及大chunk警告，不宣称无警告。最终生产文件SHA256 `455cf3f8706d717d306e97a43eeb5394dfa511ba91f31283058de5865e77c67d`，浏览器测试 `17033595970f805d51c1a6a443f13a6f4e5a1fd4ab35eb64874f696eaf90ff03`；后续仅补文档，不改变验证输入。

## 隔离与原始证据

本机证据索引（未嵌入临时PNG，换机不可直接读取）：`/tmp/pc04a9-ya0sbH/`。新SQLite `browser.sqlite`，env在任何app导入前设置。`bootstrap.py`仅复用既有5d的Mock配置/审计/HAL核验和8的synthetic seed，不读取原CAICT快照。bootstrap后及seed后7类别、7连接、3个非空Lab绑定全部Mock、endpoint `192.0.2.10`；7个实际HAL类均经 `is_mock_driver` 核验。最终实时HAL API同为mock。

专用API `127.0.0.1:18189`；专用Vite `127.0.0.1:15189`，临时配置 `gui/output/pc04a9/vite.config.ts` 的 `/api/v1/ws`、`/api/v1/ota`、`/api` 全部指向18189。未使用或重启用户8000/5173服务。完成后只关闭本次API PID1809、Vite PID1875及自建浏览器，两个临时端口均无监听；库、日志、截图、工作树、venv和output全部保留。

原件：`red.json`、`green.json`、`green-final.json`、`layout.json`、`in-flight.json`、`draft.json`、`unknown-lock.json`、`final-http.json`、`gui-related.log`、`build.log`、`bootstrap.json`、`bootstrap.log`、`api.log`；截图 `before-1800.png`、`before-1100.png`、`after-wide.png`、`after-narrow.png`、`narrow-canvas-scrolled.png`、`focus-narrow-located.png`、`expanded-wide.png`、`expanded-narrow.png`、`in-flight-pending.png`、`focused-history-modal.png`、`unknown-lock.png`。保留首轮选择器精确匹配/短超时造成的失败尝试；最终RED修正为确实因缺功能失败，GREEN和最终复核均通过。

最终只读SQL：修订、正式执行、采用、选择历史表各0行；隔离图始终r0、原JSON不变。没有启动任何采集或硬件作业，没有修改原CAICT、默认DB、仪器接线、CE回接门、补偿和现场B/HOLD。未验真实硬件采集在途、真实保存成功在途、任意极小窗口或复杂图可读性，不据本片授予正式校准/认证资格。
