# PC-04A-11：auto 实际 Mock 的显式模拟校准

## 获准范围与根因

用户要求保留 `auto` 自动选择策略，以一个 PR 修复显式模拟批量校准误拒。基准为 `4b444fb3`。旧 `require_explicit_mock_context` 在核实际驱动之前，要求资源与实验室绑定的 `driver_mode` 都是 `mock`，因此一致的 `auto` 加实际 Mock 也被拒绝。

修法是收窄错误的保存策略限制：允许一致的 `mock` 或 `auto`，继续拒绝 `real`、未知策略和绑定分叉；参与的 CE、分析仪、有切换步骤时的 RF 开关必须通过既有 `is_mock_driver()`。不靠全局模式字符串、名称或声明推断实际驱动。保存的 `auto` 不被写成 `mock`。

## 入口与消费者全集

| 站点 | 本片处置 |
| --- | --- |
| `fixed_route_jobs.require_explicit_mock_context` | 唯一生产改动；策略白名单与绑定一致性，实际驱动判据不变 |
| `route_batch_plan.build_batch_plan` | 预览和启动重新构建清单时复用同一守卫，冻结开关步骤允许 auto |
| `fixed_route_jobs.resolve_configuration/start/_execute` | 启动和租约内重核不变；CE/SA 实际混合拒绝不变 |
| `route_batch_jobs` 的启动、租约校验、人工等待结束、逐项采集 | 继续重核当前绑定及实际驱动；不放松保存身份与冻结摘要 |
| `instrument_test_lease.hold` | 重核与 HAL reload 共用协调锁，先核后取得控制，持有整个生命周期；不新增锁 |
| `fixed_route_acquisition.collect_fixed_route` | 合成输入再次要求 CE/SA 均 Mock，沿原命令拼装生成预览，不发仪器 I/O |
| `route_batch_switch.apply_batch_switch_steps` | 模拟分支复用真实命令 builder、仅预览；真实开关资格门不改 |
| evidence、application-preview、确认采用、执行冻结 | 保留 simulated 来源、formal=false，不将合成损耗授予正式补偿资格 |
| GUI/OpenAPI/Pydantic/TypeScript | 请求响应字段及显示不变，无四镜像结构改动；错误信息更准确 |

仪器协议/SCPI 语义：不适用；不新增或推测任何仪器命令。真实/混合驱动误放行代价高于误拒，所以缺失、未知和不一致均保守拒绝。非参与资源仍沿用原绑定一致性检查，不扩大本片范围。

## 验证与交付

- TDD：新 HTTP auto 正例和批次等待后漂移、带开关计划先 RED，再最小生产修复。
- 相关回归：单路、批预览/启动/等待、模拟来源与采用隔离、租约。新临时 SQLite 在导入前指定环境，测试业务库使用隔离 fixture；不碰用户 DB/8000/5173。
- 验证档位：共享安全入口变化，稳定输入后由主代理唯一运行最终全后端；独立审查不重复全量。GUI/生成类型/构建依赖不变，不重复 GUI 构建，不声称本片浏览器验收。
- 实现与必需回归完成，独立功能审查 CLEAN，外审状态随本片 PR 跟踪；未部署。原件留在本机 `/tmp/pc04a11-ceujcd`，不是仓库下载链接。
- Ready PR 按最新 HEAD 核 R1/R2 和所有评论通道；不以历史失败或空 checks 冒充全绿。

## 操作边界

`auto` 是驱动选择策略，不是“模拟”或“真实”的结果证明。此修复不改变 HAL 的自动选择规则、不保证现场自动切换成功；运行时选到真实驱动会拒绝合成样本。用户配置、原 CAICT、当前 PA 拓扑、历史证书和 B/HOLD 均不修改；此 PR 不包含部署或本机服务重启。

## 实际验证（2026-11-08）

| 阶段 | 实际结果 |
| --- | --- |
| 旧代码 HTTP RED | 3 failed /5 passed /120 warnings，7.87s；auto 正例与批次被误拒 |
| 旧代码开关 RED | 1 failed /8 deselected /50 warnings，1.24s；同一策略误拒 |
| 修复定点 GREEN | 29 passed /227 warnings，26.96s，exit0 |
| 相关生产链 | 275 passed /478 warnings，143.61s，exit0 |
| 唯一最终全后端 | 8629 passed /17 skipped /3 failed /11475 warnings，1154.83s，exit1，不称全绿 |

相关命令（在 `api-service`，导入前指定新的临时 `DATABASE_URL` 和 `USE_MOCK_INSTRUMENTS=true`）：

```sh
.venv/bin/python -m pytest tests/test_pc04a11_auto_mock.py tests/test_pc04a8_mock_contract.py tests/test_pc04a8_mock_safety.py tests/test_pc_04a_fixed_route_api.py tests/test_pc_04a_fixed_route_acquisition.py tests/test_pc06a1_batch_plan.py tests/test_pc06a1_batch_api.py tests/test_pc06a1_batch_jobs.py tests/test_pc06a1_batch_safety.py tests/test_instrument_test_lease.py -q
```

全量复用既有 `tests.pc04a8_browser_fixture --bootstrap-only --kind full` 创建新 `/tmp/pc04a8-IzR2fP/full.sqlite`，bootstrap 后显式设置并审计7类、全部Lab绑定及7/7实际Mock。该目录前缀来自复用夹具，不代表使用旧数据。随后运行：

```sh
DATABASE_URL=sqlite:////tmp/pc04a8-IzR2fP/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest -q --color=no -o log_cli=false
```

基准 `4b444fb3` 加本片生产/测试改动，`tested.patch` SHA256为 `94970962ed376189128f394446ea4ed554174a3d48c870a2718813082bf8b239`。1853个已跟踪输入和82项安装包版本清单运行起止一致；全量后只更新本记录及roadmap的验证文字，不改变生产/测试输入。未跑新版浏览器/build，不能将历史结果称作本片实跑。

失败归因：在单独干净基线工作树 `4b444fb3` 仅复跑上述三门，结果 **2 failed /1 passed /41 warnings，1.00s**。G8指向旧 `task-3-report.md` 中的历史UUID执行路由；G11指向两份旧SDD报告的 `/api/v1/ws`；与全量错误一致。gitignore门仅在本工作树存在旧未跟踪 `.superpowers/sdd/.gitignore` 内容 `*` 时失败；把同一规则加入临时基线后，**3 failed /40 warnings，0.95s**，三项错误文本与全量完全一致。原规则保留，未改历史文档、测试门或预期。不能称干净基线也有三项失败。

独立审查席 `pc04a11_review` 已核守卫全部入口、实际驱动判据、租约/等待重核、正式采用消费者及 RED/GREEN 原件；不重复全量。证据含 `red.log`、`red-switch.log`、`green.log`、`related.log`、`full.log`、`full-bootstrap.json`、`full-input-before/after.sha256`、包版本清单、基线定点日志。现场/计量资格、部署仍未验证。
