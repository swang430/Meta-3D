# P2-35 设计稿：`current_execution_id` 测试间泄漏隔离

> 2026-08-21。来源：roadmap `[discovered 2026-08-21 during P2-29 全量回归]` 第②点。
> 目标：全量测试回到 0 failed —— 治掉 `test_p1_36_execution_id::test_no_execution_means_default_not_empty`
> 在全量顺序下的必失败。

## 1. 可观察故障

全量顺序下（也是任何"泄漏文件在前、p1_36 在后"的子集顺序下）：

```
FAILED tests/test_p1_36_execution_id.py::test_no_execution_means_default_not_empty
AssertionError: 无执行上下文时 execution_id=['ca2253dc-...']，应为 '-'
```

最小复现组合（本片 RED，实跑 0.15s，1 failed）：

```
pytest tests/test_mimo_ota_report_verified_backcompat.py::test_vrt_terminal_transition_allows_only_one_archive_owner \
       tests/test_p1_36_execution_id.py::test_no_execution_means_default_not_empty
```

## 2. 泄漏机理（勘察结论，修正了 roadmap 条目的归因）

`current_execution_id` 是进程级 ContextVar（`app/core/logging_config.py:58`，default `"-"`）。
测试进程的**主线程**共享同一个 context —— 任何在主线程同步代码里的
`current_execution_id.set(...)` 不还原，就永久泄漏给同进程内之后收集到的所有测试。

三类调用路径里，只有一类会泄漏到主线程：

| 路径 | contextvar 落在哪 | 泄漏到主测试线程？ |
|---|---|---|
| TestClient 请求（commissioning 各测试全是这形态） | portal 线程 / anyio 线程池 worker 的 context，且被 `AuditMiddleware` 最外层 token `finally` reset | 否 |
| async 测试里的 set（p1_42 的模拟 downstream） | `run_until_complete` 的 Task context 副本 | 否 |
| **主线程同步直调**带 set 的生产函数 / 帮手 | 主线程 context，无人还原 | **是** |

⚠ roadmap 条目把泄漏归因到 `api/commissioning.py:539` 的端点 set —— 勘察实证这个归因不准：
commissioning 测试全走 TestClient，泄不到主线程。实证的泄漏者是
`tests/test_mimo_ota_report_verified_backcompat.py`（字母序在 p1_36 之前）在主线程直调
`VrtExecutionService.stop()/.complete()` → `get()`（`vrt_execution_service.py:124`）内 set。
`tests/test_p1_47c_execution_scpi_evidence.py` 的 `_execution` 帮手（:84）与
`test_record_rejects_cross_execution_context`（:362）同形态（字母序在 p1_36 之后，
祸及的是 47c 之后的文件 —— p2_29 的文件级自净 fixture 就是为它而生）。

## 3. 触点全集枚举表（31 处，逐个判"动/不动"）

grep `current_execution_id` 全仓（排除 .venv / __pycache__）：

### 生产侧 —— 全部不动

| 触点 | 语境 | 判定 |
|---|---|---|
| logging_config.py:58 | ContextVar 定义（default="-"） | 不动 |
| logging_config.py:71 | ContextFilter 只读 get | 不动 |
| logging_config.py:379/386 | set/reset 配对（清理日志时临时隔离） | 自净，不动 |
| audit_middleware.py:98→114（WS）/98→200（HTTP） | **最外层 token + finally reset，生产兜底本尊** | 不动 |
| audit_middleware.py:106/167-168/189 | 中间件内部 get / state 回传 set（仍在 98 的 token 保护圈内） | 不动 |
| commissioning.py:539/692/897 | 端点内**故意** set（本请求剩余日志归属此执行） | 不动，见下 |
| test_case_runner.py:211/263 | 请求侧 set（注释明写"必须在 create_task 之前"，子任务继承） | 不动 |
| test_case_runner.py:424 | 后台任务 `_run_case` 顶部 set —— create_task 的 context 副本，任务结束消亡 | 不动 |
| test_case_runner.py:461/468 | set/reset 配对（日志收尾失败时临时隔离） | 自净，不动 |
| vrt_execution_service.py:102/124 | create/get 内故意 set（VRT 每次请求盖执行身份，get 是唯一 choke point） | 不动 |
| scpi_evidence.py:160-162/733-736、execution_scpi_evidence.py:197 | 只读 get | 不动 |

**生产侧不动的三条依据**：

1. **HTTP/WS 生产路径无泄漏**：`AuditMiddleware` 在最外层 `set("-")` 持 token，
   HTTP 与 WebSocket 两条分支的 `finally` 都 `reset(execution_token)` ——
   端点内的裸 set 全部被整体还原。
2. **端点内加 reset 是功能性破坏，不是修复**：中间件 `finally` 里
   `current_execution_id.get("-")`（:189）要靠端点留下的值去 `close_execution_log`
   并给审计汇总行归属 execution_id —— 端点自己 reset 掉，P1-36/P1-42 的整条
   "本请求日志归属此执行"语义就断了。别为测试改生产语义。
3. **后台任务路径自灭**：`create_task` 继承的是 context **副本**，任务结束即消亡。

### 测试侧

| 触点 | 语境 | 判定 |
|---|---|---|
| test_p1_36_execution_id.py 全部 set | set/reset 配对（finally） | 自净，不动 |
| test_p1_40_execution_logs.py 全部 set | 配对 | 自净，不动 |
| test_p1_42_audit_execution_context.py:89/103/141/173 | 模拟 downstream 内 set，被 AuditMiddleware reset 兜住 + async task 副本 | 不动 |
| test_p1_47b_instrument_evidence.py:44/48、383/389 | 配对 | 自净，不动 |
| **test_p1_47c:84、:362** | **裸 set 无还原 —— 泄漏源** | 不改该文件（他片），由套件级 fixture 兜住 |
| **test_mimo_ota_report_verified_backcompat.py:1342/1374 等直调** | **主线程直调 VrtExecutionService —— 实证泄漏者** | 不改该文件（直调是该测试的合法形态），由套件级 fixture 兜住 |
| test_p2_29_model_load_evidence.py 文件级 autouse fixture | 文件级自净样板 | **保留不删**（任务书硬规矩；套件级落地后成冗余，另片收） |

## 4. 方案：conftest 套件级 autouse fixture（一处兜所有）+ 行为门

### 4a. `tests/conftest.py` 新增

```python
@pytest.fixture(autouse=True)
def _suite_isolate_execution_contextvar():
    token = current_execution_id.set(current_execution_id.get("-"))
    yield
    current_execution_id.reset(token)
```

- `set(get("-"))` 拿 token、teardown `reset(token)` = **恢复到本测试进入时的值**，
  不硬写 `"-"` —— 语义最保守，不改变任何测试进入时看到的世界，只把测试内的
  泄漏挡在测试边界。
- conftest 的 autouse setup 先于模块内 fixture、teardown 晚于它们 —— 正好在最外层
  包住 p2_29 的文件级 fixture 与 47c 的 db fixture 链，无嵌套冲突。
- 对 async 测试无害：fixture 本身同步跑在主线程 context，set/reset 严格配对。
- 每测试开销一对 set/reset，微秒级。

### 4b. 行为门：新文件 `tests/test_p2_35_contextvar_isolation.py`

同文件两条测试按定义序执行，**门自带泄漏源，不依赖套件里其它文件的顺序巧合**：

- `test_a_...`：故意 `current_execution_id.set("p2-35-deliberate-leak")` 不还原
  —— 复刻"主线程直调生产 set 函数"的泄漏形态（坏输入制造者）；
- `test_b_...`：断言 `current_execution_id.get("-") == "-"` —— 上一条的泄漏
  必须没有到达本条（断言者）。

正反两向：fixture 在 → 全绿（不误伤）；fixture 被摘/改坏（set 后不 reset、reset 错 token）
→ b 当场红（能抓坏输入）。这就是"套件级 fixture 本身即门"，门的强度为**行为门**档。

### 4c. 取舍：不做的两件事及理由

- **不加"测试文件不得裸 set"的静态 AST 门**：静态判据无法区分 p1_42 那种
  "故意在被中间件包裹的 downstream 里 set"的合法形态，会误伤；套件级 fixture
  已把危害本身清零，静态门退化成纯风格检查。按 ⓪⑤ 修法优先级（去掉>换源>收窄>加机制），
  不加机制。
- **不兜 `current_session_id`**：grep 实证测试侧对它的 set 全部配对
  （test_f64_check_errors_family:224/245、p1_36:112/118），无泄漏实证。
  用 ⓪⑦ 判据"不改它，①的故障还在吗" —— 不兜它 p1_36 照样绿，属越界，不做；
  记入报告的发现区。

## 5. 变异计划（⓪④，实跑）

| 变异 | 预期 |
|---|---|
| 把 conftest 的 `_suite_isolate_execution_contextvar` 整个注释掉 | RED 最小组合复红（p1_36 失败）+ 行为门 b 红 |
| （恢复后）正常态 | RED 组合绿、行为门绿、全量 0 failed |

## 6. 验收

1. RED 最小组合（§1）在修后绿；
2. 行为门文件单跑绿；变异实跑红；
3. **全量 `pytest -q --color=no -p no:cacheprovider` 0 failed**（本片后不再有任何已知失败豁免）。
