# P1-30 设计稿 — SCPI 往返日志的证据能力

> 状态：**✅ 已实现**（用户 2026-08-03 review 后拍板：截断上限「提到 2000 + env 可调」、
> 写命令「成功也补一条完成行」）
> 立项来源：2026-08-03 用户提出「log 大量是示意式的，撑不起调试复现」
> Roadmap: P1-30

---

## 0. 双实证前置（⓪⁺ ①）

| 项 | 结论 |
|---|---|
| **memory 查询** | 已做。命中 `feedback_effective_end_not_nominal`（标称端 vs 生效端 —— 本片的 `instrument_id` 覆盖 bug 正是这个母题）、`feedback_pr_scope_equals_its_purpose`（范围纪律）、`feedback_review_findings_verify_premise_first`（计数类结论必须带谓词）、`feedback_instrument_debug_via_diagnostic_sequence`（日志是诊断序列的证据载体） |
| **NotebookLM** | **本片不适用**。改动只碰日志的**记录方式**，不新增 / 不修改任何 SCPI 命令、下发序列、状态机语义或前置条件。驱动层的"空回复 vs not-ready 语义是否相同"确实要查手册 —— 但那属于**语义判定**，本片刻意不做（见 §4 范围外） |

---

## 1. 目的 —— 要修的那**一个**可观察故障

> **现场调试人员打开 `scpi.log`，看不出一次仪器往返到底发生了什么。**

三个具体表现（全部实测，口径写在括号里）：

### 病① 不知是不是事实

`app/hal/base.py:153` 与 `:168` —— TX 日志记在 `_do_write` / `_do_query` **执行之前**：

```python
def _write(self, cmd, **kwargs):
    self._log_scpi_write(cmd)      # ← 先记
    result = self._do_write(cmd, **kwargs)   # ← 后执行；抛异常则无任何配对记录
    return result
```

所以 `TX: xxx` 这行的真实语义是**"程序打算发这条"**，不是"仪器收到并接受了"。异常路径上没有任何一条日志说明它失败了、失败在哪一步。**也没有耗时** —— "一轮要多久"这类问题日志答不了。

### 病② 不知是不是完整

`app/hal/base.py:119` —— `f"RX: {response.strip()[:200]}"`，**硬截断 200 字符且无任何标记**。

实测（口径：全部 31 个 `scpi.log*`，只取 `hal_mode == "real"` 的 RX 行，共 171,170 条）：

| 现象 | 条数 | 占 real RX |
|---|---|---|
| 长度**恰好 200**（= 被截断） | **22,914** | 13.4% |
| 长度 0（`RX:` 后面空白） | **60,565** | 35.4% |

**RX 的最大长度就是 200** —— 也就是说**日志里从未出现过任何一条长响应的全貌**。被砍的都是谁：

| 命令 | 被截条数 | 是什么 |
|---|---|---|
| `BSE:MEASure:NR5G:CELL1:BTHRoughput:DL:TSTatistics:JSON?` | **22,608** | **下行吞吐量统计 JSON —— 整个项目的核心测量数据** |
| `SYST:INFO?` | 140 | F64 系统信息查询（**该命令返回什么本文不下断言** —— 那是仪器语义、要查手册，而本片声明了 NotebookLM 不适用。只陈述可观测事实：被砍掉的那 200 字符里，日志中可见的开头是 `PROPSIM F64,32,RF,v2.0,2,Band: 450MHz - 6000MHz,Main license`，后续内容**从未在日志里出现过**） |
| `BSE:STATus?` | 136 | UXM 状态 |
| `BSE:CONFig:NR5G:CELL1:ACTive:STATe?` | 26 | 小区激活态 |
| `SYSTem:ERRor?` | 1 | **错误队列自己被砍了** |

### 病③ 有内容根本没打

**查询发出后日志里没有下文**：**90,585 条**（口径：`hal_mode == "real"` 的含 `?` 的 TX 共 261,755，RX 共 171,170，差值即无下文；**34.6%**）。

⚠️ **谓词一（别归因）**：只能说**"有去无回"**。是超时、是异常、还是 coroutine 从未被 await —— **日志本身没记，所以无从判断**。不得说成"失败了 9 万次"。

⚠️ **谓词二（别按相邻行数）**：本节初稿按"TX 之后紧接着不是 RX"数得 **110,185**，**偏高 21.6%，已作废**。两种机制都会打断相邻性 —— ① **并发**：TX 记在 `_scpi_lock` **之外**且在 `_do_*` 之前，broadcaster 1 Hz × 32+ 查询与测量序列并行时，连续几条 TX 先落盘、结果行随后交错；② **嵌套**：F64 `_do_query` 超时后在同一条命令的窗口内调 `_drain_after_timeout` / `_drain_errors`，那里每条 `SYST:ERR?`（上界 64 次）各产生一对 TX/RX，排完才写外层 ERR。**配对必须按 `query` 字段，不能按行序**。（内审 F3 抓出 —— 而且本文 §2 四行契约里当时写的 34.6% 与 §1 的 110,185 是同一份文档里互相矛盾的两个数。）

另：**约 160–185 处 `except` 吞掉异常且不记日志不重抛**，其中整块只有 `pass` 的约 40–50 处。

⚠️ **这个数没有唯一值，别当精确值引用**（内审 F11 抓出）——口径稍变结果就变：
全块扫描 **162 / 43**、12 行窗口 **165 / 51**、10 行窗口 **185 / 42**，内审独立
复算得 **175 / 38**。要用它给未来那片定范围，先把口径钉死成一条能跑的命令
（见 roadmap 的同日 Discovered 条，那里贴了脚本）。→ **本片不修，进 backlog**（见 §4）。

### 额外发现（用户没提，但把上面三条全放大）

**`instrument_id` 字段在全部 759,894 行 SCPI 日志里恒为 `-`**（口径：所有 `scpi.log*` 全量统计，取值分布 `{'-': 759894}`，**100%**）。

根因是**标称端 vs 生效端**（memory `feedback_effective_end_not_nominal` 同一母题）：

```python
# app/hal/base.py:113 —— 驱动老老实实传了
extra={"instrument_id": self.instrument_id, "direction": "TX"}

# app/core/logging_config.py:50 —— ContextFilter 无条件覆盖掉
record.instrument_id = current_instrument_id.get("-")
```

`extra=` 在 record 创建时把值写上去，`ContextFilter.filter()` 随后**无条件重写**成 contextvar 的值（默认 `-`，而 SCPI 路径上没人 set 过它）。仪器身份只在 `logger` 名里侥幸留存（`app.hal.scpi.uxm-5g` 等）。

**后果**：调试人员没法按 `instrument_id` 过滤日志 —— 那个字段看起来存在、永远是 `-`。上面病①②③ 的每一条证据，都因此少一个维度。

---

## 2. 范围（⓪① 四行契约）

```
搜索命中：memory feedback_effective_end_not_nominal / feedback_pr_scope_equals_its_purpose
          目标文件自己的禁令：base.py:139-142 有「别把 coroutine 丢进 _log_scpi_response」
          的现场 bug 注释（CAICT 2026-05-13）—— 本片不得破坏 sync/async 双路径透明性
必要性：现场调试人员打开 scpi.log，看不出一次往返实际发生了什么
        （48.8% 的真实 RX 要么空、要么被砍；34.6% 的查询有去无回；仪器身份 100% 丢失）
范围：动 3 个生产文件（app/hal/base.py + app/core/logging_config.py + app/config.py）
      —— 第三个是实现期发现的（见 §3.2 的修正）；
      枚举到 ~160-185 处静默 except / app.log 78% 噪声 / logs 3.5GB，这次一处不做，全进 backlog
爆炸半径：原 bug 最坏 = 日志不可用（不影响运行）
          修完最坏 = 日志体量涨 + 若 try/except 写错会改变控制流
          → 用「只加日志、异常原样重抛、不碰返回值」约束把 Y 压到 ≤ X
```

**每个改动文件标一个字（⓪⑦）**：

| 文件 | 字 | 理由 |
|---|---|---|
| `app/hal/base.py` | **修** | 不改它，"看不出往返发生了什么"原样还在 |
| `app/core/logging_config.py` | **修** | 不改它，`instrument_id` 恒 `-`，往返记录仍缺仪器维度 |
| `app/config.py` | **修** | 不改它，`.env` 里配的截断上限被静默忽略，文档承诺的旋钮是假的 |
| `tests/test_scpi_log_evidence.py`（新） | **修** | ⓪④ 要求门 + 变异 |
| `GEMINI.md` | **顺带** | 日志通道表写着 scpi.log 是「每条 TX/RX **原文**」—— 这句话本来就不真（一直在 200 截断），改完更不真（多了 OK/ERR 两类）。同一次改动暴露、不改下次照样误导读者 |
| `docs/roadmap-first-call.md` | **顺带** | 立项 + 收口登记 |

---

## 3. 改法（修法优先级：去掉 > 换源 > 收窄 > 加机制）

### 3.1 `instrument_id` 覆盖 —— **收窄**（不是加机制）

```python
def filter(self, record):
    record.session_id = current_session_id.get("-")
    # 收窄：只在调用方没通过 extra= 显式指定时才用 contextvar 兜底。
    # 原实现无条件覆盖 → SCPI 路径 759,894 行全部丢失仪器身份。
    if not hasattr(record, "instrument_id"):
        record.instrument_id = current_instrument_id.get("-")
```

`session_id` 同理评估（当前无已知冲突方，先只改 `instrument_id`，避免顺手扩大）。

### 3.2 截断显式化 —— **收窄 + 补事实**

```python
def _log_scpi_response(self, cmd, response, duration_ms=None):
    body = response.strip()
    full_len = len(body)
    if full_len > _RESP_MAX:
        body = body[:_RESP_MAX] + f"…[truncated {_RESP_MAX}/{full_len}]"
    self._scpi_logger.debug(
        f"RX: {body}",
        extra={"instrument_id": self.instrument_id, "direction": "RX",
               "query": cmd, "resp_len": full_len, "duration_ms": duration_ms},
    )
```

- `resp_len` **永远记真实长度** —— 即使截断，读者也知道被砍了多少。
- 上限从硬编码 200 改为可配置，默认 **2000**。

  ⚠️ **实现期修正（不是原设计）**：初版写成 `os.getenv("SCPI_LOG_RESP_MAX")`，
  实证发现**这个旋钮在项目自己的配置通道里是失效的** —— `.env` 由
  pydantic-settings 直接读进 `Settings` 对象，**不注入 `os.environ`**
  （实测：import `app.config` 前后 `os.environ` 里都没有 `DATABASE_URL`，
  而 `settings.database_url` 有值）。所有其它日志配置（`log_dir` /
  `log_retention_days` / `log_scpi_enabled`）走的都是 `Settings`。
  已改为 `app/config.py` 的 `log_scpi_resp_max: int = 2000`，`.env` 里写
  `LOG_SCPI_RESP_MAX=200` 生效（实测读到 333 验证过）。因此本片实际动了
  **3 个生产文件**，第三个是 `app/config.py`（标 **修** —— 不改它，
  文档承诺的旋钮就是假的）。
- **体量评估（内审 F7 修正 —— 初版只算了 scpi.log，漏了两个同源出口）**：
  `app.hal.scpi` 是 `propagate: True`，每条 TX/OK/RX/ERR **同时**落 root 的
  `file_app`(DEBUG) 与 console。实证：`app.log.2026-07-21` 有 260,884 条带
  `direction` 的记录，`scpi.log.2026-07-21` 261,689 条 —— **1:1 复制**。
  所以 22,914 条长响应 × 最多 1800 额外字符 ≈ +41 MB 要**按 ×2 算 ≈ +82 MB**
  （scpi.log 与 app.log 各一份；现 `scpi.log*` 合计 179 MB）。
  ⚠️ 而 `app.log` 正是 P3-19 立项要治的那个（已 33 MB、78.4% 是心跳噪声）——
  **本片把它推得更大**，这笔账要记在 P3-19 头上。
  ⚠️ console 在 `settings.debug=True`（当前默认，`main.py` 传的就是它）下是
  DEBUG，现场终端单条 RX 从 200 字符变 2000，`StreamHandler` 同步写，
  慢 TTY / 管道下会顶在事件循环线程上。
  这三处都由 `LOG_SCPI_RESP_MAX` 一个旋钮同时调回。

### 3.3 往返配对 —— **加机制**（唯一一处，代价已量化）

```python
def _write(self, cmd, **kwargs):
    self._log_scpi_write(cmd)
    t0 = time.perf_counter()
    try:
        result = self._do_write(cmd, **kwargs)
    except Exception as exc:
        self._log_scpi_error(cmd, exc, (time.perf_counter() - t0) * 1000)
        raise                      # ← 原样重抛，控制流零变化
    return result
```

`_log_scpi_error` 记 `direction="ERR"` + 异常类型 + 消息 + 耗时。

⚠️ **async 路径必须同等处理**：`_do_write` / `_do_query` 返回 coroutine 时，异常发生在 `await` 时刻而非调用时刻，try/except 包不住 —— 得在 `_log_response_after_await` 里同样包一层。**这是最容易漏的一半**（`base.py:139-142` 的历史注释正是同一个坑）。

**体量代价**（口径：real 模式全量）：写命令仅 2,293 条，查询 261,755 条 —— ERR 行只在异常时产生，正常路径**零新增行**。

### 3.3⁺ 仍然覆盖不到的一半：`CancelledError`（实现期发现，**本片不修**）

`except Exception` **抓不到 `CancelledError`** —— 它在 Python 3.8+ 继承
`BaseException`。内审 F4 实跑探针：

```
asyncio.wait_for(driver._query("SLOW?"), 0.05)  →  scpi 记录只有 [('TX', 'TX: SLOW?')]，无 ERR
task.cancel()                                    →  同样只有 TX
```

所以修完之后，**"被上层取消/超时"与"coroutine 从未被 await"仍是同一种签名**。

§1 病③ 原来写的"这正是本片要修的东西"**是过强的断言，已改**。要覆盖只能
**加机制**（`except BaseException: log; raise` —— 裸 raise，控制流零变化，
取消展开期不 await），而"审查一轮里想加机制 = 停下来报告"（⓪⑤）——
**本轮只改文档，机制进 backlog**。`base.py` 的模块 docstring 已写明这个缺口。

### 3.4 空回复的可辨识性 —— **零改动，由 3.2 顺带解决**

`resp_len: 0` + `duration_ms` 一出现，"仪器回了空串"（有 RX 行、len 0、有耗时）与"有去无回"（根本没有 RX 行）就自然分开了。**不做任何语义判定**（空串 vs not-ready 是否等价 → 那是驱动层语义，要查 NotebookLM，本片不碰）。

### 3.5 门 —— 三条，每条配变异实跑（⓪④）

| 档 | 门 | 变异 |
|---|---|---|
| 不变量 | `ContextFilter` 不得覆盖 record 上已有的 `instrument_id` | 去掉 `hasattr` 判断 → 红 |
| 行为 | `_do_query` 抛异常 → scpi logger 收到 `direction=ERR` 一行，**且异常原样传出** | 去掉 except → 红；改成吞异常 → 红 |
| 行为 | 响应长于上限 → 消息含 `truncated` 标记且 `resp_len` = 真实长度 | 去掉标记 → 红；`resp_len` 记成截断后长度 → 红 |

⚠️ 门里断言 logger emit 必须复位 `.disabled`（memory `feedback_test_logger_emit_alembic_pollution`：in-process alembic 的 `fileConfig(disable_existing_loggers=True)` 会永久禁用已导入 logger，导致全量顺序 flaky）。**提交前跑全量，不是单文件。**

---

## 4. 明确不做（枚举结果进 backlog，⓪③）

| 项 | 实测 | 去向 |
|---|---|---|
| 约 160–185 处 `except` 吞异常不记日志（整块只有 `pass` 的约 40–50 处） | 口径敏感，见 §1 的警告 | Discovered → 独立片（需逐处判"该记还是该重抛"，量大） |
| `app.log` 78.4% 是 `Cache updated`/`Cache expired` 一对 DEBUG 心跳（各 52,650 次 / 共 134,362 行） | 实测 | **P3-19**（已存在的 app.log 噪声治理片） |
| `logs/` 3.5 GB / 253 文件，`app.log` 单文件 33 MB | 实测 | P3-19 |
| 驱动层"空回复 vs not-ready"语义判定（`propsim_f64.py` get_metrics 把两者合并成 `None` 且不进 `query_errors`） | 实测 60,565 条空回复 | Discovered → 需查 NotebookLM 的独立片 |
| 执行相位每步「输入参数 vs 实际生效值」记录 | 未查证 | Discovered |
| `.env.example` 完全没有 log 段（`LOG_DIR` / `LOG_RETENTION_DAYS` / `LOG_SCPI_ENABLED` / `LOG_DB_ENABLED` 四个兄弟项全缺） | 实测 | **越界，不做** —— 只补 `LOG_SCPI_RESP_MAX` 一个反而更不一致；这是先于本片存在的缺口，不改它「看不出往返发生了什么」照样修好了。→ Discovered |

---

## 5. 验收（怎么证明修好了）

**实跑结果（2026-08-03，含内审后补强）**：

- 门 **22 条全绿**；**13 条变异逐条实跑，全部让门变红**；还原后复跑 22 绿。

  | # | 变异 | 来源 |
  |---|---|---|
  | M1 | contextvar 恢复无条件覆盖 `instrument_id` | 原设计 |
  | M2 / M7 | sync / async 两侧不记 ERR 行 | 原设计 |
  | M3 | `query` 吞掉异常（`return None` 代替 `raise`） | 原设计 |
  | M4 | 截断不加标记（回到静默 `[:N]`） | 原设计 |
  | M5 | `resp_len` 记截断后长度 | 原设计 |
  | M6 | 写命令成功不记 OK 行 | 原设计 |
  | M8 | 默认上限退回 200 | 原设计 |
  | M9 | 旋钮改回 `os.getenv`（`.env` 值被静默忽略） | 实现期发现 |
  | **M10** | **上限常量写死成字面量 `200`（旋钮当场死掉）** | **内审 F1 —— 原门全绿** |
  | **M11 / M12** | **RX / OK 耗时换成常量 `0.0`** | **内审 F6 —— 原门全绿（`>=0` 是恒真断言）** |
  | **M13** | **ERR 消息体不设上限** | **内审 F9** |

  ⚠️ **M10 / M11 / M12 是内审 agent 自己造出来的** —— 我原来那 19 条门对它们
  **全绿**。M10 尤其典型：三条旋钮门只测 `_resolve_resp_max()` 的返回值，两条
  截断门又都 `monkeypatch` 掉了 `_SCPI_LOG_RESP_MAX` 这个生效端 —— 两边都碰不到
  "这个常量从哪来"这条链（`feedback_effective_end_not_nominal` 同一母题）。
  已补 `test_effective_limit_comes_from_settings_not_a_literal`（不 monkeypatch
  常量，从实际输出反推上限）与三条耗时行为门（断言慢/快调用在读数上分得开）。

- 全量 **2890 passed, 4 skipped, 0 failed**（131s）。内审当时复跑的 2887 是补 3 条门之前的数。
- 真实 `dictConfig` 链路落盘实测（不是手动调 filter）：

  ```
  [TX ] inst=f64-real-check  len=-     dur=-       TX: FREQ?
  [RX ] inst=f64-real-check  len=10    dur=0.003ms RX: 3550000000
  [TX ] inst=f64-real-check  len=-     dur=-       TX: BSE:...JSON?
  [RX ] inst=f64-real-check  len=3412  dur=0.002ms RX: XXX…[truncated 2000/3412]
  [TX ] inst=f64-real-check  len=-     dur=-       TX: INIT:IMM
  [OK ] inst=f64-real-check  len=-     dur=0.002ms OK: INIT:IMM
  [TX ] inst=f64-real-check  len=-     dur=-       TX: BOOM?
  [ERR] inst=f64-real-check  len=-     dur=0.003ms ERR: BOOM? -> TimeoutError: read timed out
  ```

  `instrument_id` 不再是 `-`；`resp_len` 记 3412 而消息体只有 2000 + 标记。
- `.env` 通道实测：写入 `LOG_SCPI_RESP_MAX=333` → `_resolve_resp_max()` 读到 **333**
  （改前的 `os.getenv` 版本读不到，会静默用 2000）；`.env` 已还原并校验。

**⚠️ 覆盖面如实申报**：以上全部在 **mock / 构造响应**下验证 —— 只证明机制成立，
**不证明真机语义**。真实仪器上的验证（尤其被截断的吞吐量 JSON 到底多长、
60,565 条空回复的真因）要到下次现场，走诊断序列而非临时脚本。

---

原计划的验收步骤（供复核对照）：

1. 跑一遍诊断序列（mock 即可 —— 只证机制，不证语义），检查新 `scpi.log`：
   - `instrument_id` 不再恒 `-`
   - RX 行带 `resp_len` 与 `duration_ms`
   - 造一条超长响应 → 出现 `…[truncated N/M]`
   - 造一条抛异常的 query → 出现 `direction=ERR` 行**且异常照常传播**
2. 三条门 + 各自变异实跑（看输出再说"已跑"，⓪⑥）
3. 全量 pytest（不是单文件）
