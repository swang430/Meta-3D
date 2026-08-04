# P1-32 设计稿 — `configure_mac_throughput_test()` 的缺命令处置

> 2026-08-04 立稿。**只做本地半**；补正确命令形式那半是 P1-33。

## 双实证前置

- **memory（恒适用）**：`project_testcase_driven_instrument_arch` ——
  **路径 B（正式测试，有 TestCase）绝不用默认 fallback 静默兜底，真没匹配就 fail-loud**。
  `measure.py` 这条调用链正是路径 B。
- **NotebookLM + 手册原件**：⚠️ **这一项我连错两次，记录在案**。

  1. 最初判「不适用」（理由：本片不改命令形式）→ **用户当场加强规则**：
     「SCPI/HAL 必须在 NotebookLM 里找到确认」；
  2. 补查后 NotebookLM 答「NSA 模式**即对应** LTE_NR_IRAT」，我照单全收，
     把措辞 / CLAUDE.md / P1-33 方向全改成「**仪器支持**、是我们 profile 没写」；
  3. 内审追问 → 再查 → **NotebookLM 自己撤回**：那句「在手册原文里**完全没有依据**，
     属于根据通信行业背景知识做出的**推断**」；
  4. 用户指出**单点问题该直接查库里的手册原件** → grep
     `Instrument_API_Doc/Keysight UXM NR SCPI/*.md` 拿到权威答案。

  **手册原件实况**：`IRAT` 确是独立的 Application Mode 取值（`IRAT` 20 处 /
  `NSA | SA | IRAT` 38 / `SA | IRAT` 16 / `NSA | IRAT` 15 / `IRAT-SA` 13），
  这 11 条标 `NSA | SA` 不含 IRAT ——**但对照组证伪了这个推论**：
  我们 IRAT profile 里**已定义、现场在用**的 `CELL_BAND` / `CELL_DL_ARFCN` /
  `CELL_DL_BW` **同样标 `NSA | SA`**。

  **结论：该字段答不了 TAP 可用性，两个方向都没证据 = 未经查证。**
  （且这批命令**从未被真机普查过** —— `uxm_scpi_compatibility` 跳过 `None` 模板。）

  **对本片的影响**：机制不变（graceful-skip + 结构化结果 + 调用方中止），
  **措辞一律中性** —— 代码/日志/错误消息里既不说"仪器不支持"也不说"仪器支持"，
  只说「本 profile 未定义 + 该 TAP 是否支持未经查证 + 出发前普查确认」。
  有门 `test_error_message_makes_no_claim_about_instrument_capability` 守着。

  **教训（已下沉 CLAUDE.md + memory）**：「查了」≠「找到确认」——
  `notebook_query` 会把推断说成结论，语气跟引原文时一样。
  追问「**这句话在手册原文里有没有依据？是原文还是你的推断？**」，它会自己认；
  **单点问题直接查手册原件**。

## 故障（可观察的那一个）

`UxmLteNrIratProfile` 继承 `UxmTestApp` **基类**，本函数要用的 11 条命令
**11/11 都是 `None`** → 第一条 `.format()` 抛 `AttributeError` → 整段 `except`
吞掉 → `return False`。而 `measure.py:389-401` **丢弃返回值**、无条件
`start_signaling()`。

净效果：**3GPP MIMO OTA MAC 层吞吐量测试的全部配置在现场那台仪器上从未生效**，
而测出来的数被当作合规结果。AMC 开着 + MCS 由 CQI 动态调 —— 测的是
**UXM 调度器的行为，不是 DUT 的 MIMO 能力**，量纲就不对。

## 目标文件自己的禁令（动手前 grep 到的）

| 位置 | 禁令 | 本稿如何遵守 |
|---|---|---|
| `uxm_base_station.py:674` | **半生效配置不许报 applied** | `applied` 只列**真发出去**的；`ok` 要求全部必要命令都发了且无异常 |
| `uxm_base_station.py:813` | 布尔契约 `return False`，**不能向 HAL caller 裸抛** | 仍不抛；改的是返回**形态**，不是改成抛异常 |
| `measure.py:1531` | fail-loud，**不许退回猜** | 必要命令缺失 → `FAILED`，不猜、不降级跑 |

## 两个决策（2026-08-04 用户拍板）

**① 必要命令被跳过 → 中止，标 `FAILED`**（不走"degraded + 警告"）。

依据：仓库已有**结构完全相同**的先例 `measure.py:290` ——
`mimo_port_preset` typo 时 `set_cell_config` 只 log+return False 不 abort、
**静默保留旧路由**，所以调用方做前置 fail-loud 直接 `FAILED`。

与"路损未校准只警告"的区别在**错的性质**：路损是量对、偏移量没校准；
本片是**量纲不对**（测的是调度器不是 DUT 能力）。

代价：P1-33 落地前，现场这一步硬失败、拿不到吞吐数 —— 这是知情选择。

**② 驱动返回结构体**（不是 bool + 旁挂状态）：`applied` / `skipped` /
`missing_mandatory` 三份清单。调用方据 `missing_mandatory` 判，报告也能列出
**到底哪几条没下去**。

## 必要 / 可选切分（8 / 3）

| 级别 | 命令 | 为什么 |
|---|---|---|
| **必要** | `PDSCH_SCHED_ALGO` | Full Buffer 没开 → 测的是打流能力 |
| | `PDSCH_AMC_ENABLE` `PUSCH_AMC_ENABLE` | AMC 没关 → 测的是 UXM 调度器（函数 docstring 自己有一整段论证） |
| | `PDSCH_MCS` | 与 AMC=OFF 共同定义工作点 |
| | `PDSCH_RB_ALLOC` | RB 不满 → 吞吐随分配缩放 |
| | `TDD_PATTERN` `TDD_PERIOD` | DL/UL 比例变 → 绝对值不可比 |
| | `CSIRS_PORTS` | 端口数不匹配 → **根本跑不到目标层数** |
| **可选** | `HARQ_MAX_TRANS` `HARQ_PROCESSES` `MEAS_TPUT_STAT_COUNT` | 影响精度/置信区间，**不改量纲** |

分级**只放在驱动里一处**（它才知道语义），调用方只看 `missing_mandatory` ——
避免两份清单漂移。

## 不动的东西

- **KPI 前置 `_enable_kpi_measurements(cell)` 留在第 0 步**（#275 挪上来的，
  有 `M10b` 变异守着）。它必须排在可能跳过的那 11 条**之前**。
- 不碰命令形式本身（P1-33）。
- `MockBaseStation` 没有这个方法，`hasattr` 守门已覆盖 —— mock 路径行为不变。

## 会 stale 的两处「本片不修」注释（③⁺ 文档镜像）

- `uxm_base_station.py:1710` 注释里的「那是先于本片存在的独立缺陷，本片不修」
- `tests/test_uxm_kpi_readback.py:316` docstring 里的「在 IRAT 方言上**必定返回
  False**……本片不修」

两处都要随本片更新，否则留下互相矛盾的镜像。
