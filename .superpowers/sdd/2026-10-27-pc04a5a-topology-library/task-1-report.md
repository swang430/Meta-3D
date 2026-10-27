# PC04A5a Task1 实施报告

状态：Task1已实现并自查，等待root独立规格/质量审查。尚未声称独立审查或最终验收通过。

实现提交：`2c3f0a442ba56876878876f3c54cf24545242e0c`（feat: 增加保形拓扑副本和库元数据保护）。后续证据提交仅补报告和浏览器文本原件，不改变生产/测试。

## 边界与环境

- BASE：`5282eeb8435c133f1c684962be0a2bd345ac1839`；分支 `codex/topology-library-pa-plan`。
- 已读 Task1 brief、progress、增量审查PASS、设计契约和计划浏览器RED前置；按实施者模板完成自查，不派子agent、不push、不释放主claim。
- 原CAICT、默认DB、用户8000服务零访问/零写入。所有app导入均由调用方先指定新建/tmp SQLite、USE_MOCK_INSTRUMENTS=true；浏览器夹具默认bootstrap后逐类和所有Lab binding显式mock，提交后重读核验。
- NotebookLM不适用：本片无SCPI/仪器语义变更。
- 后端全量责任仍属Task3，本任务没有运行全后端。

## 实现及完整消费关系

| 入口 → 权威源 | 正式消费者 | 可观察断言 |
|---|---|---|
| POST copy → `_resolve_scope` / `_load_scoped_topology` / ORM三个原始图列 | 新UUID保存和响应序列化 | 原图逐JSON类型不变；副本仅两calibrated已有键置null、缺键保留、owner引用与inactive边保留 |
| PATCH name → 本次实际字段集合 | orchestration的chamber+active+updated_at排序 | 真SQL含updated_at列自赋值；两active图下重读时间和resolver ID不变；数据库新时间不回退 |
| Create/Update/copy → 共用名称函数 | 三写入口 | trim后1–200字符；控制字符/null/空白拒绝422；可见Unicode/同名不同UUID允许 |
| template → 模板全部验证后检查同chamber/category已有行 | 原图/默认标记/执行resolver | replace已有行409；空库首次及追加导入均inactive非default，不清旧默认 |
| copy → 新图而非旧采用/证书记录 | Application/Selection、UUID及string两种拓扑证书 | 四表全行序列化前后完全一致；无新采用/选择 |

设计规定三条全集检索已执行，结果分别204/84/27行，原件 `/tmp/pc04a5a-consumers.txt`、`/tmp/pc04a5a-selection.txt`、`/tmp/pc04a5a-import.txt`。同名probe calibration import是其他领域，不修改；GUI service/mock/generated/文案由Task2接续，不在本任务越界修改。现有DELETE和旧NULL topology_id证书兼容不改。

## 浏览器真实 RED（生产代码修改前）

1. 新库 `/tmp/pc04a5a-epwAK6/browser.sqlite`。夹具只用ORM建两个暗室、共享暗室Lab、两个category、101图分页范围及其他范围多图，不调用copy。manifest包含提交后mock核验。
2. 启动前18105/15105无监听；API18105，专用Vite15105，绝不代理到用户8000。Playwright真实headed浏览器选择“PC04A5a实验室0”→“射频拓扑”。
3. 当前scope实际列表200、total=2、两个不同UUID；界面只有“隔离原图-0-1-000”，无库Select/改名/复制入口，不能选回第二图。浏览器真实fetch `POST /api/v1/switch-topologies/{id}/copy?lab_profile_id=...` 返回404/Not Found，未拦截网络响应。
4. 原件：`output/playwright/pc04a5a/browser-red.png`、`pc04a5a-browser-red.snapshot.log`、`browser-red-api.log`、`seed.log`。截图SHA256 `5ce0fc94eacc1171bae5d00b982a6b2fac697664881fcdd91c20a16bf3dd7302`。这些原件保留在本工作树，不清理旧证据。

`.log`被仓库通用日志忽略规则排除，未强行加入ignored日志。为使本任务浏览器证据随提交保存，五份浏览器/seed日志另存同名`.txt`，与本地`.log`逐字节一致；不是重生成或删减。截图及`.txt`为任务交接的可版本化原件。

启动命令（api-service / gui各自目录）：

```bash
pc04a5a_browser_dir=$(mktemp -d /tmp/pc04a5a-XXXXXX)
env DATABASE_URL="sqlite:///$pc04a5a_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a5a_browser_dir/logs" .venv/bin/python -m tests.pc04a5a_browser_fixture
env DATABASE_URL="sqlite:///$pc04a5a_browser_dir/browser.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR="$pc04a5a_browser_dir/logs" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18105
npm run dev -- --config vite.pc04a5a.config.ts --host 127.0.0.1 --port 15105 --strictPort
```

## HTTP TDD 和回归原文

每次pytest先mktemp，再显式DATABASE_URL/USE_MOCK_INSTRUMENTS/BOOTSTRAP_ON_STARTUP。以下是实际命令的测试部分；原日志均保留。

### RED

`python -m pytest tests/test_pc04a5a_topology_library.py -q`

`/tmp/pc04a5a-J4EY44/red.log`：`31 failed, 2 passed, 40 warnings in 1.65s`，pytest exit1。
具体失败：copy404非201；name-only真实PATCH把2020旧时间改当前；无效名称被接受或空值500；replace已有行200而非409；模板仍active/default。不是“找不到测试”或导入错误冒充RED。

### 首轮GREEN与补充边界

- `/tmp/pc04a5a-pmHoGI/green.log`：`33 passed, 40 warnings in 1.42s`，exit0。
- `/tmp/pc04a5a-nHJIZ9/final-focused.log`：`37 passed, 42 warnings in 1.59s`，exit0；补owner所有边、外部证据四表不变、并发新时间不回退、非name-only保留原更新时间语义。

### 指定相关集第一轮

```bash
.venv/bin/python -m pytest tests/test_pc04a5a_topology_library.py tests/test_switch_topology_chamber_binding.py tests/test_p1_57_topology_lab_context.py tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_pc04a4a_final_graph_validation.py tests/test_pc04a4b_port_contract.py tests/test_pc04a4b_port_identity.py tests/test_pc04a4c_internal_routes.py tests/test_pc04a4c_internal_contract.py tests/test_pc04a4c_internal_identity.py tests/test_pc04a4d_conversion.py tests/test_pc04a4d_loss_truth.py -q
```

`/tmp/pc04a5a-bj4saV/related-green.log` 原文：`4 failed, 526 passed, 2409 warnings in 220.44s (0:03:40)`，exit1。

失败逐条消费：

- p1_57新增同室默认保留断言的夹具原为false；修为显式设true后验证不被清。
- 4a OpenAPI闭包发生在同步生成前；生成后重验通过。
- 4a final_graph_validation的两个import分支仍假定导入立即active；按本片有意契约改成“图结构仍可解析、inactive不进正式resolver”，POST/PATCH原有执行断言不变。
- 未把这些失败说成历史已知或忽略，也未为此更改正式resolver。

只重跑涉及修订/闭包的模块：

```bash
.venv/bin/python -m pytest tests/test_pc04a5a_topology_library.py tests/test_switch_topology_chamber_binding.py tests/test_p1_57_topology_lab_context.py tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_final_graph_validation.py -q
```

`/tmp/pc04a5a-zTUXvV/fix-related.log`：`138 passed, 143 warnings in 7.69s`，exit0。
未重新执行其余已通过的相关模块，不合并为一个虚构“全绿总数”。warnings确实存在，不声称输出无警告。

## 实际浏览器 API GREEN

第二个全新库 `/tmp/pc04a5a-Q9y9Qr/browser.sqlite` 同样默认bootstrap+提交后全mock核验。仅停止本任务已知exec session31841的旧API并启动新API，不杀用户进程。真实浏览器fetch结果原件 `output/playwright/pc04a5a/browser-api-green.log`：

```json
{"copyStatus":201,"patchStatus":200,"sourceId":"1b0a0d18-c969-4796-a72e-7149ea589a66","copiedId":"4ba6f3a7-e5b8-4e90-9da7-05d3d0dca93b","copiedName":"浏览器API GREEN副本","inactive":true,"nonDefault":true,"clearedCalibration":true,"timestampUnchanged":true,"renamed":"原图仅改名称","sourceGraphUnchanged":true,"sourceCalibrationRetained":2.5}
```

这仅是Task1网络API GREEN，不是Task2库按钮交互GREEN，也不是Task3综合验收。当前隔离API exec session43233 / Vite session98135仍保留，浏览器session `pc04a5a`。

## 自查和剩余边界

- 不复制Application/Selection/采集run/证书/confirmed；inactive副本不自动执行。不声称永久排除旧NULL topology_id证书；未来显式激活仍可能走现有兼容政策。
- 不改用户CAICT、不引入激活/删除按钮、不实现修订/恢复/并发保存5b、不改接5c。
- generated/service/mock/GUI文案仍待Task2；此中间提交不能当完整四镜像与最终交互交付。
- 最终全后端、分页101行实际第二页请求、完整dirty/busy/迟到/跨Lab/default浏览器矩阵仍属Task3。
- 额外自查发现：历史ORM的connections=[null]/null或nodes=[null]在现有最小示例算法中先于Response校验触发500而非422，无半成品提交。已补3病例并留RED：`/tmp/pc04a5a-k6zD5g/malformed-red.log`，`3 failed, 37 deselected, 40 warnings in 0.27s`。
- 此边界先报告root；父任务当轮已结束、不能即时回复。实现者按Task1明确的“源无法序列化→422”要求做最小解释：只加三数组/每行dict形态拒绝，不修图、不填默认、不扩到保存校验；root仍须复核。代价是损坏形态必须先修复源才能复制，但原契约本就不允许不可响应的半成功副本。
- 形态拒绝后覆盖原3病例及全部Task1+修订模块：`/tmp/pc04a5a-ieAIwr/final-green.log`，`141 passed, 143 warnings in 6.48s`，exit0。后续扩充到全部三个图列的null/[null]对称参数，不改变生产逻辑。
- 最终对称参数版同5模块命令加 `-o log_cli=false`：`/tmp/pc04a5a-nnw09I/final-green.log`，`144 passed, 143 warnings in 6.81s`，exit0（含本任务43例）。这是最新代码/测试版本，不把前轮141或37作为最终数字。
- 实现提交`2c3f0a44`落盘后核验（仓库根目录）：`api-service/.venv/bin/python -m pytest api-service/tests/test_pc04a5a_topology_library.py api-service/tests/test_pc04a4a_nominal_properties.py::test_checked_crud_and_schema_closure_match_live_contract -q -o log_cli=false`。新库 `/tmp/pc04a5a-WxmRCL/test.sqlite`、mock/bootstrap环境同前；`postcommit-green.log`原文 `44 passed, 43 warnings in 4.49s`，exit0。后续只改此报告及证据文本，没有运行第二次全后端。

## 验证版本指纹

各测试运行于BASE加本任务工作区增量，不冒充BASE原代码通过。最终生产文件SHA256如下；浏览器API GREEN早于最后4行损坏形态拒绝，核心copy/name/import逻辑一致，最后拒绝由HTTP回归覆盖。

```text
00e591afe7fec869cda737b6250cfb10cb77924450d852121e53c4ce4088125e  api-service/app/api/switch_topology.py
923f399d9d92523f51dd6fa3574f82f1b1ed6a3f917d0aff118a45e0e96cf9e5  api-service/app/schemas/switch_topology.py
fbf7029b60328164762a75342e8abd8549b2e3308fe7f67aba9875da6ef7a720  api/openapi.yaml
```

自查未发现新硬件调用/默认位/执行绑定写点。`git diff --check` exit0。文件分类均为“修”（API/schema/OpenAPI/针对性回归/隔离fixture和代理/报告），未混入其他原有output、venv或Playwright目录。补改4a final_graph_validation属于本片导入契约消费方回归，不是扩做4a生产能力。

## 独立审查后 P2 修复

独立审查发现probe dict缺id仍在统计先KeyError→500。root裁决本片按现有422契约修复：先补真实HTTP反例RED，再将既有Response校验移到统计之前（flush后、commit前），不修源或补默认。详细命令/日志/输入哈希见同目录 `task-1-fix-report.md`。本轮新反例1 failed/43 deselected，最小换序后Task1全部44例+scope/chamber+OpenAPI闭包累计81 passed/79 warnings/4.16s；未重跑13模块或全后端。等待原reviewer增量确认，原144/44数字仅代表修复前版本，不冒充最新版本。
