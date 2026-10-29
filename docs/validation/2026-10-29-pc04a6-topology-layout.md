# PC-04A-6 软件验证摘要

基线 `3057b409a17e41e58d9b9de2b95bb77932b08e8b`，分支 `codex/pc04a6-topology-layout`。仅 GUI 位置布局、显示空间与相关测试/指南；无后端、API、数据库迁移或依赖修改。未跑后端全量；独立审查、PR 外审及发布由主任务后续接续。

## 行为与验证范围

- 排版纯函数仅改位置；32 路端口自然序、确定性输入倒序、尺寸避让、回路/孤点、跨层同行及位置撤回均有行为测试。撤回保留后续属性和边修改、不复活删除节点、不移动新增节点；不同 scope/revision 拒绝旧快照。
- 初轮缺失功能 RED 为 3 fail；真实画面暴露其他模式终点挤占 PA 列后，另补跨层同行 RED 为 1 fail/3 pass，再修为 4 pass。最终参数保形与撤回两项变异分别令对应行为断言失败，恢复后输入 hash 相同。
- 最终相关 GUI 命令（cwd `gui`）：`npx --no-install tsx --test test/topologyLayout.test.ts test/topologyDraft.test.ts test/topologyRevisionState.test.ts test/topologyLibraryState.test.ts test/topologyPortContract.test.ts test/topologyInternalPaths.test.ts test/topologyHandleFreeze.test.ts test/topologyOperationalLabContext.test.ts test/pc04a2RouteCalibration.test.ts src/features/TopologyEditor/*.test.ts`。**82 tests / 82 pass / 0 fail / 837.419542ms，exit 0**。
- `npm run build`：exit 0，**7844 modules，11.95s**。存在两项动态/静态混用 import 提示和大 chunk 警告，不宣称无警告。

## 真实 API 与浏览器

新临时库 `/tmp/pc04a5d-fYEU9h/browser.sqlite`；复用既有 fixture 的严格新库路径守卫，env 先于 app 导入。bootstrap 后与 seed 后各核 7 类别、7 个实际 HAL driver 全 Mock；4 个 Lab 的非空绑定与所有连接 endpoint 均指向 `192.0.2.10`。API 仅 `127.0.0.1:18076`，Vite 仅 `127.0.0.1:15176`，所有 `/api` 代理均核向该独立 API。不写用户 8000/5173 服务，不重启它们。

只读 r4 参考复制为新图 `e552b57f-3b9a-4ea6-94f6-b048262642cf`，Lab `3d44801f-d6a1-42fc-9e74-fbfcd1720ba3`。原用户图与用户绑定未复制为活动配置，也未写入。浏览器使用真实 Playwright 鼠标/滚轮/表单，未调用 React handler、未伪造响应。

| 可观察行为 | 实际结果 |
|---|---|
| 专注空间与窗口调整 | 1280×720 画布约1248×566；1920×1080 约1888×967；保存入口可见，退出专注不丢当前图 |
| 120 节点/122 边/32 PA | 当前 MIMO 模式67个可见节点；DOM 矩形无重叠；32条 PA→对应 Probe 的纵向差约16.67，端口自然序保留 |
| 选线/缩放/拖动 | B1 线缆真实点击打开 `conn_ce_b1_to_hprobe_1v__pa_out`；B1/B16/B32 局部有可辨标签；PA B16 实际鼠标拖动改变位置 |
| 撤回保护 | 修改 B1 器件名称后撤回排版，名称保留、位置恢复原 r4 值；再排版并保存到r5，撤回失效 |
| 保存中 | 仅对真实网络增加1500ms延迟，原 API 正常处理；保存中排版/撤回/模式均禁用，最终真实保存成功 |
| 网络未知 | 浏览器真实离线后保存失败，未知锁保留、排版/撤回禁用；重新联网后显式 GET/采用服务器最新，无自动重发 |
| 并发409 | 另一真实 PATCH 将隔离图推进r6，浏览器旧令牌保存409，草稿保留；显式核对/采用后再排版保存至r7 |
| 辅助区状态 | 收起/退出专注/展开后仍是同一个已连接 DOM 面板，批量频点输入 `3500,3600` 保留；不把本项当正在运行采集的实测证明 |
| 保存重载 | 最终r7显式刷新并重新进入射频拓扑，67个可见节点坐标与真实GET逐一相等（容差0.01），无自动重排、无未保存改动，撤回禁用 |

只读 SQL/API 最终审计通过：除显式演练修改的 B1 名称外，120 节点全部非位置字段保形；122 条连接与所有模式完整相等，inactive/nondefault、身份、暗室、开关不变。隔离源图 raw 与原 fixture 相同、r0、无修订；各 Lab 绑定原样；执行、诊断、采用及选择历史表均0行。本片没有启动采集或仪器作业。

## 原始证据与限制

命令、API回执、Mock审计和测试日志保留于 `/tmp/pc04a5d-fYEU9h/`；截图在 `output/playwright/pc04a6-*.png`。核心证据：`gui-final.log`、`build-final.log`、`audit-final.json`、`undo-save-success.log`、`drag-unknown.log`、`conflict409.log`、`save-pending.log`、`responsive-success.log`、`panel-retention.log`。

首轮 `pc04a6-layout-full.png` 因开发期间热重载切回隔离 r0，加上默认最小缩放，不能证明 r4 可读性；`pc04a6-r4-overview.png`/`b1-zoom.png` 另暴露跨层错行，均保留作失败依据，不当作通过证据。修后证据为 `pc04a6-r4-aligned-overview.png`、`pc04a6-r4-b1-final.png`、`b16-final.png`、`b32-final.png`、`edge-selected.png`、`undo-attribute.png`、`unknown-locked.png`、`conflict409.png`、`save-pending.png`。

开发阶段出现错误选择器/抽屉按钮名称导致的超时日志，已用真实快照纠正后重验；不把失败尝试隐去。既有路由面板对 inactive 隔离副本返回422，不放宽该资格门。未验证正在运行的真实采集、真实仪器、现场校准及任意复杂图零交叉。源码仍无条件挂载同一 RouteCalibrationPanel，采集 busy/unknown 判据未变；本片不扩展未改生命周期矩阵。
