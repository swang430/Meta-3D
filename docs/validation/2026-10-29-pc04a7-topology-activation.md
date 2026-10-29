# PC-04A-7 拓扑启停软件验证摘要

基线 `cc8bbd8aa765f238190ba4cfc23e757932e30a00`，分支 `codex/pc04a7-topology-activation`。仅 GUI 复用既有 `updateTopology`，发送 `{is_active, expected_revision}`；无后端、契约、迁移、依赖或正式选择规则修改。独立内审、外审和发布由主任务后续接续，不据本摘要关闭现场 B/HOLD。

## 本片结果

- 浏览器先真实选择停用图，缺“启用拓扑”入口而 RED；helper 首轮 7 pass / 1 fail。实现后 8 pass。三项独立变异（不翻转目标、扩散图数组、固定旧修订）各 7 pass / 1 fail，恢复 8 pass；生产和测试文件前后 SHA256 完全一致。
- 相关 GUI 回归：84 tests / 84 pass / 0 fail，794.071917ms，exit 0。`npm run build`：exit 0，7844 modules，11.40s；保留既有动态/静态 import 与大 chunk 提示，不称无警告。
- 既有后端相关回归：库、修订、路径选择、暗室绑定共 105 passed / 253 warnings，32.57s，exit 0。局部 GUI/API 既有契约档，无生产共享后端变化，不重复历史全量。

## 新隔离库与真实浏览器

新目录 `/tmp/pc04a5d-zIcrVz/`、新库 `browser.sqlite`；沿既有 fixture 的严格命名守卫复用 bootstrap，环境先于任何 app 导入。bootstrap 后、seed 后、最终审计均核 7 类别为 Mock、连接全为 `192.0.2.10`、4 个 Lab 各 7 条非空 Mock 绑定；实际初始化的 7 类 HAL 全部通过 `is_mock_driver`。专用 API `127.0.0.1:18077`，Vite `127.0.0.1:15177`，唯一 `/api` 代理包含 REST/OTA/WS，全部指向本片 API。未写用户原 CAICT、r4、默认数据库或 8000/5173 服务，未启动真实硬件。

目标图 `94929dfa-5389-4209-a54c-49989db2742b`，Lab `2823ebdd-9698-4547-bc02-034980d61b4f`；同暗室 peer `fe9b8706-5ad6-4576-a950-9d40547c1342`。两图均由隔离 fixture 生成，不复制用户图。Playwright headed 真实表单/按钮操作，网络仅使用真实离线或延迟 `continue`，不伪造响应、不调用 React handler。

| 场景 | 可核结果 |
|---|---|
| 取消／启用／停用／连续动作／重载 | 取消保持 r0/inactive；启用 r1、停用 r2、再次启用 r3，重载仍选该 UUID/启用。每次写只有 flag 与当前修订 |
| 正式选图与路径门 | 真实 `orchestrate_switch_topology`：r0 inactive 选 peer；r1 active 选目标；r2 inactive 回 peer；最终 r7 active 选目标。显式路径 HTTP 分别 422→200 一条→422→200，不放宽 inactive 门 |
| 保形 | SQL 逐列核目标除 flag/revision/updated_at 外全部相同，另外三图全部列相同；所有三数组、default、Lab bindings 保持；历史快照保留，只新增正常修订 |
| dirty／pending | 实际排版产生草稿后启停禁用；放弃草稿不写服务器。1200ms 真实网络延迟下确认、库选择和保存禁用，原 API 仍处理并回读 |
| 409 | 弹窗旧令牌时另一真实 PATCH 先更新；旧请求 409，输入保留、确认禁用；只读核对后显式采用最新，不自动重试 |
| 数据库写 unknown | 真实浏览器离线写失败，不显示成功；联网后 GET 与取消核查均仍锁定；显式采用才结束核查，恢复期间 PATCH 数为 0 |
| 弹窗打开后真实采集变 busy | 先开停用弹窗，再由真实 API 启动 Mock 作业，原样延迟历史 GET 返回 running；确认随真实 busy 禁用。终态回读后释放，最终仍可停用，未吞 busy |

实际 Mock 作业 `dbedc17e-050f-44a0-a9b2-cd6c26279517`：真实 running→simulated；samples=[]、net_loss=null、cleanup_confirmed=null、formal_eligible=false。不把 simulated 或软件锁释放当真实 RF 停发、实测或校准资格。短暂离线时观察到采集按钮锁，但未单独证明长期采集 GET 失败的全部恢复分支；本片未扩历史已验矩阵。

## 原件与边界

完整命令、输入 hash、失败尝试、API 日志、Mock manifest、只读 SQL 与正式消费者输出在本机 `/tmp/pc04a5d-zIcrVz/` 和本片 SDD `task-1-report.md`；截图在 `output/playwright/pc04a7-*.png`。未将本机目录当远程下载地址。主要截图为 `red-missing-activation`、`confirm-enable`、`enabled`、`disabled`、`reloaded-enabled`、`dirty-locked`、`pending-locked`、`conflict409`、`unknown-locked`、`modal-became-collection-busy`、`final-library`。

开发中有只读 Select 被误用 fill、相对 API URL、原生确认使 CLI 分段返回、并行浏览器脚本以及辅助区收起导致定位超时的失败尝试，全部保留；最终结果以完成的结构化回执、API/SQL 原件为准。未验证真实仪器、现场校准、认证、跨进程/PostgreSQL 并发或启停后自动执行正式测试。没有新增跨 SPA 持久 unknown 锁；沿原库工作流离页重入只重新 GET，不自动重发。
