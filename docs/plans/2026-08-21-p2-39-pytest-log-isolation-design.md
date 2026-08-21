# P2-39 pytest 与运行日志隔离设计

## 可观察故障

pytest 收集 `tests/conftest.py` 时会导入 `app.main`。`app.main` 在模块导入阶段调用
`setup_logging()`，而 `settings.log_dir` 默认指向 `./logs`。测试进程因此会在运行服务的
日志目录中创建与轮转 `app.log`、`scpi.log`、校准、测量、审计等日志；轮转处理器按
`backupCount` 删除旧归档。历史实证曾在一次测试会话中把日志从 253 个文件 / 3.5 GB
缩到 24 个 / 727 MB，现场仪器往返证据被静默删除。

## 边界与全集

本片只隔离 pytest 进程的日志根，不修改生产日志格式、留存策略、文件名、API 或执行日志
语义。

| 站点 | 当前行为 | 本片裁决 |
|---|---|---|
| `tests/conftest.py` | 只在导入应用前隔离 HAL 模式 | 同一时点强制建立进程级临时日志根并写入 `LOG_DIR` |
| `app.config.settings` | 模块导入时读取 `.env` / 环境变量 | 继续作为日志目录真值；pytest 只是提前换掉其输入 |
| `app.main` | 导入时调用 `setup_logging(settings.log_dir)` | 不加 pytest 嗅探，不改变生产启动链 |
| `setup_logging()` | 创建并轮转九类文件日志 | 完整保留；测试日志仍可被日志契约测试观察 |
| `api.system_logs` | 从 `settings.log_dir` 读取日志 | 测试中自然读取临时根，不需要专用分支 |
| pytest 子进程 / worker | 可继承调用方的 `LOG_DIR` | 每个 pytest 进程在 conftest 导入时重新覆盖为自己的临时根 |
| 显式日志单测 | 直接传入 `tmp_path` | 保持原样，不受全局根影响 |

## 方案比较

### A. 在 pytest 入口导入应用前换源（采用）

`tests/conftest.py` 创建一个模块生命周期的 `TemporaryDirectory`，无条件把 `LOG_DIR`
指向它，再导入 `app.main`。每个 pytest 进程得到独立目录；目录对象存活到进程结束并自动
清理。

优点：改动只在测试边界；生产代码无新分支；所有现有文件日志仍工作；子进程和并行 worker
不会继承并复用运行日志根。缺点：测试结束前会占用一份临时日志空间，但生命周期有界。

### B. `setup_logging()` 检测 pytest 后改目录（拒绝）

这会把测试框架知识引入生产日志器，并依赖 `sys.modules`、进程名或环境嗅探。任何漏判都会
重新触碰运行日志，误判又会让正式服务把证据写进临时目录。

### C. pytest 下关闭全部文件 handler（拒绝）

虽然不会轮转运行日志，但会让大量日志路由、脱敏、执行日志和 API 测试失去真实载体，形成
测试与生产行为分叉。

## 数据流与生命周期

1. pytest 加载 `tests/conftest.py`。
2. conftest 创建唯一临时目录，并无条件设置 `os.environ["LOG_DIR"]`。
3. conftest 导入 `app.main`；`app.config.settings` 此时读取临时绝对路径。
4. `setup_logging()` 正常创建所有 handler，但只在临时根内读写和轮转。
5. 日志 API 与测试中的应用实例继续读取同一个 `settings.log_dir`。
6. pytest 进程退出后，临时目录对象清理测试日志；运行日志目录从未被打开。

## 失败与安全方向

- 误拒绝：测试日志被写入临时目录，最坏是测试结束前多占少量空间。
- 误放行：测试打开运行日志并轮转删除不可恢复的仪器证据。

两者代价明显不对称，因此 conftest 必须无条件覆盖 `LOG_DIR`，不能使用 `setdefault` 允许
调用方把 pytest 指回运行日志。真实服务不加载测试 conftest，不受影响。

## 验证

新增子进程回归：调用方预置一个带历史 `app.log` 和归档的“受保护运行日志目录”，再启动
一条会导入 `app.main` 的 pytest。修复前该目录会被创建、追加或轮转；修复后目录清单、
内容和元数据保持不变，子进程的 `settings.log_dir` 位于独立临时根。

同时增加顺序门，确认日志隔离语句位于 `from app.main import app` 之前；运行日志配置、
SCPI 证据、执行日志、系统日志 API 与完整 rule gates 回归。

## 非目标

- 不清理现有 DB、日志、worktree 或测试沉积；该工作属于后续 P2-40。
- 不改变正式日志留存天数或敏感 SCPI 30 天上限。
- 不把测试日志改写为内存 mock，也不跳过 `setup_logging()`。
- 不处理非 pytest 的临时脚本；本条可观察故障限定为 pytest 导入应用链。

## 实施与验证（当前代码提交 `903f811`）

- RED：子 pytest 继承受保护 `LOG_DIR` 后，`app.log` 被轮转并新增九类当前日志，保护目录
  快照断言失败；证明测试确实命中本条故障，而不是只检查源码形状。
- GREEN：conftest 无条件覆盖 `LOG_DIR` 后，同一子进程测试通过；保护目录的文件名、字节、
  大小与 mtime 全部保持不变。
- 门变异：把直接赋值改成 `setdefault`，顺序门按预期失败；恢复后完整 rule gates
  **53 passed**。
- 日志相关回归：**66 passed**；全后端：**4172 passed / 5 skipped**。
- 全量测试前后对 worktree `api-service/logs` 的文件名、大小与 mtime manifest 做精确比较，
  结果完全一致，确认全量 pytest 没有触碰运行日志。
- `compileall` 通过（仅一条既有 `test_rule_gates.py` 无效转义 SyntaxWarning）；
  `git diff --check origin/main...HEAD` 通过。
- fresh 内审：P1/P2/P3=0。生产日志配置零改动，范围只覆盖测试入口、端到端回归与顺序门。
