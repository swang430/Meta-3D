"""UXM KPI 回读对账 —— 把 #275 换上的那批命令逐条发出并**打印原始回复**。

为什么需要它（兄弟序列都替代不了）
--------------------------------
#275 把 8 个 KPI 的命令、元素下标、单位、前置条件整批换成手册版本，但
**本地零真机验证** —— 全部依据来自手册与真机历史日志。而现有两个序列
结构上都答不了本片要问的问题：

- `uxm_scpi_compatibility` 答的是「这条命令**通不通**」（存不存在 / -113）。
  它不看返回值，**答不了「回了几个元素、第几个是什么、单位是什么」**。
- `uxm_manual_spelling_probe` 答的是「我们当年是不是**拼错了**」。

而 #275 的正确性全押在**返回值的形状与下标语义**上：取错一位（CQI 的
`maximum` vs `average`）会系统性乐观；单位判错（bps vs Mbps）差 10⁶；
RI 的 bin 是码点还是层数，差一整个 rank。这些**只有把原始回复摆出来、
跟仪表面板对照**才能定。

本序列的契约：**只呈现，不判定**
--------------------------------
每一项都打印仪器的原始回复（`raw`，逐字保留），并把**候选读法并排列出来**
让操作员对着面板挑，**不预设哪个对**。

⚠️ **绝不传 expect** —— 拿期望值去比等于预设答案，那正是本序列要治的病。
（同 `propsim_f64_state_machine` 的禁令：F64R-7 那类"它到底返回什么字面值"
的问题，一旦带上期望就白问了。）

写法来源
--------
NotebookLM「Keysight UXM5G 网络测试 SCPI 编程指南」`236d9621-...`，
2026-08-03 三轮查证（见 `docs/design/uxm-kpi-readback-fix.md`）；
CQI / RI 的**逐元素布局**取自仓库内厂商原件
`Instrument_API_Doc/Keysight UXM NR SCPI/UXM5G_SCPI_02_NR_PHY_Measurements.md`
——那段代码块在 NotebookLM 的摄取里丢了，它自己说的。
**禁盲试**：这里每一条都能在手册里指到，不是我们编的变体。

安全性
------
⚠️ **不是只读序列**。它必须发这些**改变仪器状态**的命令，否则所有 KPI 查询
恒返 `9.91E+37`（手册明确的硬前置）：

  · `BSE:MEASure:NR5G:BTHRoughput:STATe ON`  —— 开吞吐量/BLER 累积（全局）
  · `BSE:MEASure:NR5G:<cell>:CSI:STARt`      —— 开 CSI（CQI/RI）累积
  · `BSE:CONFig:MEASurement:REPort ON`       —— 开 UE 测量报告队列
  · `BSE:MEASure:NR5G:BTHRoughput:CLEar`     —— **清零正在累积的窗口**

所以 `safe_during_test=False`。**`STATe` 与 `REPort` 的原值会在 `finally` 里
写回**（同 `uxm_config_truth_probe` 的纪律：写过就必须恢复，绝不把仪器留在
被本序列改过的状态）；`CLEar` **不可逆** —— 这是它不能与真实测试并行的硬理由，
不是"最好别并行"。
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.diagnostic_context import DiagnosticContext
from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
# 复用不复制：错误码解析与方言解析跟兄弟序列同源，免得两份判据漂移。
from app.diagnostics.sequences.uxm_scpi_compatibility import (
    _profile_for_driver,
)

# 与兄弟序列 uxm_manual_spelling_probe 同款判据（含 IGNORECASE）——
# 同一个参数在两个序列里给两种答案，现场输小写就是一次莫名其妙的拒跑。
_CELL_TOKEN = re.compile(r"CELL(?:[1-9]|1[0-4])|SELected", re.IGNORECASE)

# SCPI 的 NaN —— 手册反复强调：测量没开 / 刚 reset / 还没收到样本时，
# 所有 float 型计数与比率都返回 9.91E+37。
_SCPI_NAN = 9.9e37

metadata = SequenceMetadata(
    name="UXM KPI 回读对账 (打印原始回复, 供现场跟面板比)",
    description=(
        "把 #275 换上的那批 KPI 命令逐条发出并打印**原始回复**：元素个数、"
        "各下标的值、以及每个歧义点的候选读法（单位 bps/Mbps、CQI 取 max 还是 "
        "average、RI 的 bin 是码点还是层数、RSRP 是码点还是 dBm）。"
        "**只呈现不判定** —— 对着仪表面板挑哪个对。"
        "⚠ 会开测量累积并清零窗口，不能与真实测试并行。"
    ),
    required_categories=["baseStation"],
    params_schema=[
        {"name": "cell", "label": "小区 (留空=用当前方言的主小区)",
         "type": "string", "default": ""},
        {"name": "window_s", "label": "每次等待累积的秒数 (前置后等一次 + CLEar 后等一次, 共两次)",
         "type": "number", "default": 3.0},
    ],
    safe_during_test=False,  # 开累积 + 清零窗口，会毁掉正在测的 KPI
)


async def _maybe_await(value: Any) -> Any:
    """UXM 的 `_do_*` 是同步 def（F64 才是 async）—— 两种都兜住。"""
    if asyncio.iscoroutine(value):
        return await value
    return value


def _fmt(v: Optional[float], tok: Optional[str] = None) -> str:
    """把一个元素显示成人能读的样子。

    ⚠ **三种"没有值"必须长得不一样**（本序列的门抓出来的）——
    在一个专门用来"呈现真相"的序列里，把它们都渲染成 `—` 等于把三件事
    混成一件（跟 P1-30 治的"测到 0"vs"没读到"是同一个母题）：
      · SCPI NaN（9.91E+37）= 仪器说"我没数据"   → `NaN(9.91E+37)`
      · 空元素                = 回复里就是个空位   → `<空>`
      · 解析不了              = 回了非数字         → `<原样 token>`
    """
    if v is not None:
        # ⚠ 用 .10g 不用 g —— `g` 只有 6 位有效数字, progress=12345678
        #   会显示成 1.23457e+07, 跟面板**逐位对不上**, 而本序列的全部价值
        #   就在"跟面板比"。
        return f"{v:.10g}"
    if tok is None:
        return "—"                       # 下标越界，压根没这个元素
    t = tok.strip()
    if not t:
        return "<空>"
    try:
        f = float(t)
        if f != f or abs(f) >= _SCPI_NAN:
            return "NaN(9.91E+37)"
    except ValueError:
        pass
    return f"<{t}>"


def _tokens(raw: str) -> List[str]:
    """原样切出各元素的 token（不 strip 掉空元素）—— 显示时要用它区分
    「空位」「非数字」「NaN」，光有 float 值区分不了。"""
    return (raw or "").split(",")


def _parse_doubles(raw: str) -> List[Optional[float]]:
    """逗号分隔的 double 列表 → list；SCPI NaN / 空 / 非数字 → None。

    ⚠ **空元素也占位**（不是丢弃）—— 丢位会让后面所有下标左移一格，
    那正是本序列要帮现场排除的错位问题。
    ⚠ 值为 None 时**只说明"不是个可用数字"**，具体是哪种要看 `_tokens()`
    的原样 token（见 `_fmt`）。
    """
    out: List[Optional[float]] = []
    for tok in _tokens(raw):
        t = tok.strip()
        if not t:
            out.append(None)
            continue
        try:
            v = float(t)
        except ValueError:
            out.append(None)
            continue
        out.append(None if (v != v or abs(v) >= _SCPI_NAN) else v)
    return out


def _at(vals: List[Optional[float]], toks: List[str], i: int) -> str:
    """按下标取一个元素的显示串；越界给 `—`（= 压根没这个元素）。"""
    if not (0 <= i < len(vals)):
        return "—"
    return _fmt(vals[i], toks[i] if i < len(toks) else None)


def _all_elems(vals: List[Optional[float]], toks: List[str]) -> str:
    return ", ".join(f"[{i}]={_at(vals, toks, i)}" for i in range(len(vals)))


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    bs = drivers.get("baseStation")
    if bs is None:
        return SequenceRunResult(
            success=False, summary=driver_not_loaded_summary("baseStation"))
    refusal = mock_driver_refusal_summary("baseStation", bs)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)
    if not hasattr(bs, "_query"):
        return SequenceRunResult(
            success=False,
            summary=(f"baseStation 驱动 {type(bs).__name__} 没有 SCPI 查询通道 "
                     f"(_query)"))

    profile = _profile_for_driver(bs)
    profile_name = getattr(profile, "PROFILE_NAME", "?")

    # ⚠ 本序列的命令全部取自手册的 `BSE:` 命令树。在别的方言上跑会全回 -113，
    #   于是得出"手册写法也不支持"的**错结论** —— 而"把自己发错当成机器不支持"
    #   正是兄弟序列 uxm_manual_spelling_probe 存在要治的病，自己踩上去就荒唐了。
    #   所以方言不匹配**直接拒跑，不猜**。
    if not getattr(profile, "MEAS_TPUT_DL_OTA", None):
        return SequenceRunResult(
            success=False,
            summary=(
                f"当前方言 {profile_name} 没有定义 KPI 回读命令（`MEAS_TPUT_DL_OTA` 等）。"
                "本序列的命令取自手册的 BSE: 命令树（LTE_NR_IRAT），在别的方言上跑会"
                "全回 -113 并给出错误结论。先确认 UXM 跑在 LTE_NR_IRAT 上，或先把"
                "该方言的命令形式查手册补齐（见 roadmap 同名 Discovered 条）。"))

    # ⚠ 不能直接 .strip() —— 传进来的可能是 int/None/其它类型（实测 {"cell": 1}
    #   会抛 AttributeError 并逃出 run()）。跟同一函数里 window_s 的兜法保持一致。
    raw_cell = params.get("cell")
    cell = (str(raw_cell).strip() if raw_cell is not None else "") or getattr(
        profile, "PRIMARY_CELL", "CELL1")
    if not _CELL_TOKEN.fullmatch(cell):
        return SequenceRunResult(
            success=False, summary=f"cell 参数非法: {cell!r}")
    # ⚠ 不能写 `params.get("window_s") or 3.0` —— **`0` 是 falsy**，
    #   操作员显式传 0（想跳过等待）会被静默换成 3.0，而且一声不吭。
    #   `0` / `None` / 键缺省是三件事，要分开判。
    raw_window = params.get("window_s")
    if raw_window is None or raw_window == "":
        window_s = 3.0
    else:
        try:
            window_s = max(0.0, float(raw_window))
        except (TypeError, ValueError):
            window_s = 3.0

    steps: List[SequenceStepResult] = []

    def _step(label, success, detail, raw=None, ms=None):
        steps.append(SequenceStepResult(
            label=label, success=success, detail=detail, raw=raw,
            duration_ms=ms))

    async def _q(cmd: str) -> str:
        return await _maybe_await(bs._query(cmd))

    async def _w(cmd: str) -> None:
        await _maybe_await(bs._write(cmd))

    async def _err() -> str:
        """**排空**错误队列，返回本次取到的全部条目（原样，不解释）。

        ⚠ 两处都要（内审 F3）：
          · 只 pop 一条 → 一条命令产生两个错误时，第二条会串到**下一步**名下；
          · 跑前不 `*CLS` → 上一次操作的 stale 错误被记到本序列的命令头上，
            于是把**对的**命令记成"手册写法也不支持" —— 正是本文件 docstring
            点名要避免的病。兄弟序列 uxm_scpi_compatibility 就是先发 `*CLS`。
        """
        out: List[str] = []
        for _ in range(16):          # 上界防仪器一直吐
            try:
                r = (await _q("SYSTem:ERRor?")).strip()
            except Exception as e:  # noqa: BLE001
                out.append(f"<读错误队列失败: {e}>")
                break
            if not r:
                break
            out.append(r)
            if r.startswith("0,") or "no error" in r.lower():
                break
        else:
            # ⚠ 跑满 16 次没见 `No error` = **队列没排空**（内审 F5）。
            #   剩下的会漂到下一条命令名下 —— 正是本轮在治的那个病，
            #   只是发生在上界这一格。**必须说出来并把该步判红**，
            #   不能悄悄返回一串看着挺全的错误。
            #   （单纯调大 16 只是把边界挪远，不解决"撞上了没人知道"。）
            out.append("<队列未排空: 已读 16 条仍未见 No error —— "
                       "此后各步的错误归属不可信>")
        return " || ".join(out) if out else "<空>"

    def _err_clean(err: str) -> bool:
        """错误队列这一轮是不是干净的（用来给步骤定 success，见内审 F4）。

        ⚠ 判据必须**逐条**看，不能拿整串去找 `no error`：
        `_err()` 是**排空到 `0,"No error"` 才停**的，所以脏队列长这样
        `-113,"Undefined header" || 0,"No error"` —— 用「整串含 no error」判
        **恒为真**，这道门在真机上等于不存在。

        上一版就是这么写的，内审 F4 那批 `_err_clean(err)` 因此**从没红过**；
        我的门当时绿，是因为假仪器**永远回 -113、从不回 `No error`**，
        `_err()` 撞满 16 次上界才返回 —— 那不是真机的样子。
        （Codex #277 P1 补门时实跑撞出来的。）
        """
        if not err:
            return False
        return all(p.strip().lower().startswith("0,") or "no error" in p.lower()
                   for p in err.split("||"))

    async def _probe(label: str, cmd: str, expect_n: Optional[int],
                     interpret) -> Optional[List[Optional[float]]]:
        """发一条返回 double 列表的查询，打印原始回复 + 候选读法。

        `expect_n` 只用来**报告元素个数对不对**，不作为通过条件 ——
        个数不符恰恰是最要紧的发现（下标会整体错位）。

        ⚠ **查完立刻排空错误队列**（Codex #277 P1）—— 两条路径都要：
          · 查询抛异常那条**最要紧**：命令头不认识时仪器把 `-113` 塞进队列、
            读超时抛异常，错误**留在队列里**漂到下一条命令名下；
          · ①-⑦ 全不排空时，这些错误一路攒到 ⑧b，把 `CLEar` 记成"不支持" ——
            现场据此把**对的**命令从驱动里删掉，正是本文件 docstring 要防的病。
        """
        t0 = time.perf_counter()
        try:
            raw = await _q(cmd)
        except Exception as e:  # noqa: BLE001
            ms = int((time.perf_counter() - t0) * 1000)
            err = await _err()
            _step(label, False,
                  f"查询抛异常: {type(e).__name__}: {e}；错误队列: {err}", ms=ms)
            return None
        ms = int((time.perf_counter() - t0) * 1000)
        err = await _err()
        vals = _parse_doubles(raw)
        toks = _tokens(raw)
        n = len(vals)
        head = f"{n} 个元素"
        if expect_n is not None:
            head += (" ✓ 与手册一致" if n == expect_n
                     else f" ⚠ **手册说 {expect_n} 个 —— 个数不符则所有下标错位**")
        detail = f"{head}；{interpret(vals, toks)}；错误队列: {err}"
        _step(label, _err_clean(err), detail, raw=raw, ms=ms)
        return vals

    # ── 方言完整性：九条命令逐个查，缺的**显式记 SKIPPED**（内审 F7）──
    # 早先只用 MEAS_TPUT_DL_OTA 一个字段代表九条 —— 那是**代理判据不是真判据**：
    # 别的方言若只补了这一条，序列会跑完 N 步全绿、summary 说"无失败步"，
    # 而操作员按 roadmap 的九项对应表以为都问过了，实际有几项从没发出去。
    _NEEDED = [
        ("MEAS_TPUT_DL_OTA", "① DL OTA 吞吐量"),
        ("MEAS_TPUT_UL_OTA", "② UL OTA 吞吐量"),
        ("MEAS_BLER_DL", "③ DL BLER"),
        ("MEAS_BLER_UL", "④ UL BLER"),
        ("MEAS_CSI_CQI", "⑤ CQI 统计"),
        ("MEAS_CSI_RI", "⑥ RI 直方图"),
        ("MEAS_UE_REPORT_JSON", "⑦ UE L3 测量报告"),
        ("MEAS_BTHROUGHPUT_CLEAR", "⑧ CLEar 圈窗口"),
    ]
    missing_cmds = [(n, lb) for n, lb in _NEEDED if not getattr(profile, n, None)]

    # ── 前置：记原值，供 finally 写回 ────────────────────────────
    state_cmd = getattr(profile, "MEAS_BTHROUGHPUT_STATE", None)
    report_cmd = getattr(profile, "MEAS_UE_REPORT_STATE", None)
    csi_state_cmd = getattr(profile, "MEAS_CSI_STATE", None)
    csi_stop_cmd = getattr(profile, "MEAS_CSI_STOP", None)
    orig_state: Optional[str] = None
    orig_report: Optional[str] = None
    orig_csi: Optional[str] = None
    # ⚠ **判定值与呈现值分家**（内审 F1）：`orig_csi` 恒等于仪器原样答的
    #   token，可不可信单独用这个旗标记。上一版直接把 orig_csi 置 None，
    #   于是仪器明明答了 STOP、现场记录却写"读不到" —— 证据被删掉，
    #   而这份记录的全部价值就在证据。同文件 `_read_orig` 在同一母题下
    #   是对的（保住值、只标不可信），CSI 曾是三条恢复路径里唯一删证据的。
    csi_pre_trusted = False
    touched_state = False
    touched_report = False
    touched_csi = False

    async def _read_orig(cmd: str, what: str) -> Optional[str]:
        """读一个开关的原值，供跑完写回。

        ⚠ **`?` 形式手册未说明**（2026-08-04 NotebookLM 三问确认：
        `BTHRoughput[:STATe]` 与 `CONFig:MEASurement:REPort` 都只写了设置形式、
        未标 `Query only`、命令总表里也是不带 `?` 的）。所以这里读**失败是正常情况**，
        不是仪器坏了 —— 但读不到就**不能猜一个值写回去**（原值可能本来就是 ON，
        猜 OFF 写回比留着更糟），只能如实报出来让人手动确认。

        ⚠ 正因为它是**投机查询**，三条路径都必须自己排空错误队列
        （Codex #277 P1）：手册未说明的命令头最可能被拒 → `-113` 留在队列里 →
        紧跟着的 `... ON` 是**受支持**的写入，却因为读到这条 stale 错误被记成"被拒"。
        """
        try:
            v = (await _q(f"{cmd}?")).strip()
        except Exception as e:  # noqa: BLE001
            err = await _err()
            _step(f"P0 读 {what} 原值", False,
                  f"读不到原值（{type(e).__name__}: {e}）。⚠ 该 `?` 形式**手册未说明**，"
                  f"读不到属预期之内；但本序列**不会写回** {what}，"
                  f"跑完请手动确认仪表状态。本条自己的错误队列: {err}", raw=None)
            return None
        err = await _err()
        if not v:
            _step(f"P0 读 {what} 原值", False,
                  f"回了空串 —— 视为读不到（该 `?` 形式手册未说明）。"
                  f"本序列**不会写回** {what}，跑完请手动确认。"
                  f"本条自己的错误队列: {err}", raw="")
            return None
        # ⚠ 读回了值 **不等于** 这个值可信（内审 F1）：队列脏说明这条查询本身
        #   出了问题，而这个值是要**写回仪器**的。同一个 docstring 上面就写着
        #   "读不到就不能猜一个值写回去" —— 拿不可信的值写回是同一件事的变体，
        #   而且更糟：全程报绿，操作员不会再去手动确认，可能把本来 ON 的悄悄关掉。
        #   代价不对称：判脏而实净 = 多花人力确认；判净而实脏 = 静默改仪器状态。
        if not _err_clean(err):
            _step(f"P0 读 {what} 原值", False,
                  f"读回了 {v!r}，但仪器**同时把这条查询记进了错误队列**: {err}。"
                  f"这个值不可信，**不拿它写回**。⚠ {what} 会被本序列留在 ON，"
                  f"跑完请手动确认。", raw=v)
            return None
        _step(f"P0 读 {what} 原值", True,
              f"原值 {v!r}，跑完会写回；本条自己的错误队列: {err}", raw=v)
        return v

    try:
        # 跑前排空错误队列 —— 否则 stale 错误会被记到本序列的命令头上（内审 F3）
        # ⚠ `*CLS` 是本序列发的**第一条写命令**，也曾是唯一没人验证接受与否的一条
        #   （内审 F4）——它失败时只进 `log()` 文本，而操作员看的是 steps，
        #   于是记录写着"已发 `*CLS` 并排空"、success 还是绿的。
        #   更糟的是我那道"每条写命令都要有一步能红"的不变量门，
        #   **恰好把 `*CLS` 排除在外** —— 洞正开在唯一没覆盖的那条上。
        cls_ok = True
        try:
            await _w("*CLS")
        except Exception as e:  # noqa: BLE001
            cls_ok = False
            log(f"  · *CLS 失败（{e}）—— 下面的错误队列读数可能含历史残留")
        pre_err = await _err()
        # `*CLS` 清错误队列 —— 发完还脏，说明它没生效（或错误是发完才到的），
        # 两种都让"哪条命令产生了哪个错误"的归属不再可信，要报出来。
        _step("P0 清空错误队列", cls_ok and _err_clean(pre_err),
              (f"已发 `*CLS` 并排空；残留: {pre_err}") if cls_ok else
              (f"⚠ **`*CLS` 没发出去** —— 此后每一步的错误队列读数都可能含历史"
               f"残留，本序列对「哪条命令产生了哪个错误」的归属**不可信**，"
               f"别据此判定命令支不支持。排空到的残留: {pre_err}"), raw=None)

        for name, label in missing_cmds:
            _step(f"{label} —— SKIPPED", False,
                  f"方言 {profile_name} 未定义 `{name}` —— 本项**没有问过**，"
                  f"不要按 roadmap 的九项对应表当作已核验。", raw=None)

        # ① 三条前置（roadmap 清单第 ⑧ 项：它们**真被接受**了吗）
        if state_cmd:
            orig_state = await _read_orig(state_cmd, "BTHRoughput:STATe")
            touched_state = True   # 先置：写抛异常≠没写到仪器，保守地一律尝试恢复
            await _w(f"{state_cmd} ON")
            err = await _err()
            _step("P1 开吞吐量/BLER 累积", _err_clean(err),
                  f"已发 `{state_cmd} ON`；错误队列: {err}", raw=None)

        csi_start = getattr(profile, "MEAS_CSI_START", None)
        if csi_start:
            # ⚠ 手册原文：`CSI:STARt` 是 Imm Action，且
            #   "If an NR CSI measurement is already running for the cell,
            #    the request is **ignored**." / "If the specified cell is off,
            #    the request is **ignored**."
            #   所以**只发不回读分不清「开成功」和「被静默忽略」** —— 而 CQI/RI
            #   全 NaN 时操作员会误判成"命令形式不对"，把整片结论建在错前提上。
            #   `CSI:STATe?` 手册标 **Query only: True**，返回 STOP|WAIT|MEAS。
            async def _csi_state() -> Tuple[Optional[str], str]:
                """读一次 CSI 状态，**自己排空自己的错误队列**（Codex #277 P1）。

                两次调用一前一后夹着 `CSI:STARt`：前一次不排空，错误会被记到
                STARt 头上；后一次不排空，错误会漂到 P3 的 `REPort ON` 头上。
                """
                if not csi_state_cmd:
                    return None, "<未查>"
                try:
                    v: Optional[str] = (
                        await _q(csi_state_cmd.format(cell=cell))).strip()
                except Exception:  # noqa: BLE001
                    v = None
                return v, await _err()

            orig_csi, err_pre = await _csi_state()
            # ⚠ 读到 token ≠ 这个 token 可信 —— 内审 F1 的母题在 CSI 上的镜像
            #   （Codex #277 R2：R1 把 err_pre/err_post 捕获出来了，却没接进判定）。
            #   这里错边的**代价不对称**：
            #     · 误当成 STOP → `finally` 真去发 `CSI:STOP`，**打断本来就在跑的测量**；
            #     · 误当成"在跑" → 只是不关，下次 `CSI:STARt` 被忽略、CQI/RI 掺进
            #       本序列样本 —— 这是**静默错数**，本来比"打断"更重；
            #       它之所以仍是较轻那侧，**唯一理由是那条分支留了显式告警**，
            #       所以那条告警必须挂在**红**上（内审 F3），挂在绿上这个论证就塌了。
            #   判定用旗标，**不动 orig_csi 本身**（内审 F1）。
            csi_pre_trusted = _err_clean(err_pre)
            touched_csi = True
            await _w(csi_start.format(cell=cell))
            err = await _err()
            after_csi, err_post = await _csi_state()
            # 回读自己的队列脏 = 这个 STOP/WAIT/MEAS 不可信 →
            # 不能据此宣布 `CSI:STARt` 生效了（那正是本步存在的意义）。
            running = (_err_clean(err_post) and bool(after_csi)
                       and after_csi.upper().startswith(("MEAS", "WAIT")))
            # ⚠ 红了要给**对得上的**理由（内审 F6）——「不是 MEAS/WAIT 才会被忽略」
            #   这句在"回读是 MEAS 但队列脏"那一格当场自相矛盾。
            if not _err_clean(err_post):
                why = (f"⚠ **本步红是因为回读自己的队列脏** —— 回读值 "
                       f"{after_csi!r} 不可信，不能据它宣布 STARt 生效；"
                       f"**不是**「状态不对」。")
            elif not running:
                why = ("**不是 MEAS/WAIT 就说明 STARt 被静默忽略**（小区关着，"
                       "或已在跑），那样 ⑤⑥ 的 NaN 是前置没生效、"
                       "不是命令形式不对。")
            else:
                why = ""
            _step("P2 开 CSI (CQI/RI) 累积", running and _err_clean(err),
                  f"已发 `{csi_start.format(cell=cell)}`；"
                  f"**回读 CSI:STATe? = {after_csi!r}**（发之前 {orig_csi!r}）—— "
                  f"手册：STOP=未运行 / WAIT=已启动等开始时刻 / MEAS=正在采集。{why}"
                  f"错误队列 —— STARt 自己的: {err}"
                  f"（两次 STATe? 各自的: {err_pre} / {err_post}，"
                  f"**分开记，别把它们算到 STARt 头上**；"
                  f"任一次的队列脏，对应的那个状态值就按**读不到**处理 —— "
                  f"不拿不可信的值去决定要不要 STOP）", raw=after_csi)

        if report_cmd:
            orig_report = await _read_orig(report_cmd, "MEASurement:REPort")
            touched_report = True
            await _w(f"{report_cmd} ON")
            err = await _err()
            _step("P3 开 UE 测量报告队列", _err_clean(err),
                  f"已发 `{report_cmd} ON`；错误队列: {err}", raw=None)

        log(f"  · 前置已下发，等 {window_s:g}s 让统计累积")
        await asyncio.sleep(window_s)

        # ② DL / UL OTA 吞吐量（清单 ①②③）
        def _tput_read(vals, toks):
            avg = vals[4] if len(vals) > 4 else None
            lines = [f"按手册下标 current=idx1={_at(vals, toks, 1)}, "
                     f"average=idx4={_at(vals, toks, 4)}"]
            if avg is not None:
                lines.append(
                    f"**单位待定** → 若是 bps: {avg / 1e6:.3f} Mbps；"
                    f"若已是 Mbps: {avg:.10g} Mbps。**跟面板读数比，差 10⁶ 就是 bps**")
            else:
                lines.append(
                    "average 无值（NaN/缺）→ **本轮定不了单位**；先确认前置生效 "
                    "+ 有数据业务在跑，再重跑本序列")
            lines.append("全部元素: " + _all_elems(vals, toks))
            return "；".join(lines)

        if getattr(profile, "MEAS_TPUT_DL_OTA", None):
            await _probe("① DL OTA 吞吐量",
                         profile.MEAS_TPUT_DL_OTA.format(cell=cell), 6, _tput_read)
        if getattr(profile, "MEAS_TPUT_UL_OTA", None):
            await _probe("② UL OTA 吞吐量",
                         profile.MEAS_TPUT_UL_OTA.format(cell=cell), 6, _tput_read)

        # ③ DL / UL BLER（清单 ④）
        if getattr(profile, "MEAS_BLER_DL", None):
            await _probe(
                "③ DL BLER", profile.MEAS_BLER_DL.format(cell=cell), 10,
                lambda v, t: (
                    f"驱动取 idx8=pdschBlerRatio={_at(v, t, 8)}"
                    f"（对照 idx4=nack-ratio={_at(v, t, 4)}）"
                    "；全部元素: " + _all_elems(v, t)))
        if getattr(profile, "MEAS_BLER_UL", None):
            await _probe(
                "④ UL BLER", profile.MEAS_BLER_UL.format(cell=cell), 6,
                lambda v, t: (
                    f"驱动取 idx4=nack-ratio={_at(v, t, 4)}"
                    "；全部元素: " + _all_elems(v, t)))

        # ④ CQI（清单 ⑤）—— 取错一位会系统性乐观
        if getattr(profile, "MEAS_CSI_CQI", None):
            await _probe(
                "⑤ CQI 统计", profile.MEAS_CSI_CQI.format(cell=cell), 6,
                lambda v, t: (
                    "厂商原件 result[0]=绝对子帧号 [1]=count [2]=min [3]=max "
                    "[4]=average [5]=median；"
                    f"**驱动取 idx4(average)={_at(v, t, 4)}**，"
                    f"对照 idx3(maximum)={_at(v, t, 3)}、idx0={_at(v, t, 0)}。"
                    "**跟面板的 CQI 均值比** —— 若面板等于 idx3 说明下标该退一位；"
                    "全部元素: " + _all_elems(v, t)))

        # ⑤ RI 直方图（清单 ⑥）—— 码点 vs 层数差一整个 rank
        def _ri_read(v, t):
            counts = [x for x in v if x is not None]
            total = sum(counts)
            if not counts or total <= 0:
                return ("直方图全空/全 NaN —— 看 P2 步的 `CSI:STATe?` 回读："
                        "不是 MEAS 就是**前置没生效**，不是命令形式不对；"
                        "全部 bin: " + _all_elems(v, t))
            as_code = sum((i + 1) * x for i, x in enumerate(v) if x is not None) / total
            as_rank = sum(i * x for i, x in enumerate(v) if x is not None) / total
            return (
                f"**驱动按「bin 是 3GPP 码点、rank=码点+1」算 → 平均 rank "
                f"{as_code:.2f}（四舍五入 {round(as_code):d}）**；"
                f"若 bin 直接是 rank 则为 {as_rank:.2f}（{round(as_rank):d}）。"
                "**跟面板显示的 rank 比** —— 面板若是前者说明驱动对。"
                "（rank 0 物理上不存在，若算出 0 一定是权重反了）；"
                "全部 bin: " + _all_elems(v, t))

        if getattr(profile, "MEAS_CSI_RI", None):
            await _probe("⑥ RI 直方图",
                         profile.MEAS_CSI_RI.format(cell=cell), 8, _ri_read)

        # ⑥ UE L3 测量报告（清单 ⑦）—— 口径未知，本序列就是来定它的
        rep_cmd = getattr(profile, "MEAS_UE_REPORT_JSON", None)
        if rep_cmd:
            t0 = time.perf_counter()
            try:
                rep_raw = await _q(rep_cmd.format(cell=cell))
                ms = int((time.perf_counter() - t0) * 1000)
                err = await _err()          # 排空归本条（Codex #277 P1）
                _step(
                    "⑦ UE L3 测量报告 (RSRP/RSRQ/SINR 口径)", _err_clean(err),
                    "⚠️ **手册未说明**这些值是 3GPP 上报码点还是已换算的 dBm/dB —— "
                    "驱动当前**刻意不填** `rsrp_dbm`/`sinr_db`，只把原样值留进证据。"
                    "**现场判法：跟面板的 RSRP 读数比 —— 3GPP 的 rsrp-Result 码点 "
                    "0..127，dBm = 值 − 156；差 156 就是码点，相等就是 dBm。**"
                    "原始 JSON 见 raw（P1-30 后 scpi.log 也留了完整响应）。"
                    f"错误队列: {err}",
                    raw=rep_raw, ms=ms)
            except Exception as e:  # noqa: BLE001
                ms = int((time.perf_counter() - t0) * 1000)
                err = await _err()
                _step("⑦ UE L3 测量报告", False,
                      f"查询抛异常: {type(e).__name__}: {e}；错误队列: {err}",
                      ms=ms)

        # ⑦ CLEar 真能圈窗口吗（清单 ⑨）
        # ⚠ 两次读各自成步、各带自己的 raw（内审 F9）——
        #   合成串违反 protocol.py 的「raw 原样存」约定；
        #   且任一步抛异常不能把前面 7 步的证据一起带走（内审 F8）。
        clear_cmd = getattr(profile, "MEAS_BTHROUGHPUT_CLEAR", None)
        if clear_cmd and getattr(profile, "MEAS_TPUT_DL_OTA", None):
            tcmd = profile.MEAS_TPUT_DL_OTA.format(cell=cell)
            before_v = await _probe("⑧a 清零前读一次吞吐量", tcmd, 6,
                                    lambda v, t: "progress=" + _at(v, t, 0))
            try:
                await _w(clear_cmd)
                err = await _err()
                _step("⑧b 发 BTHRoughput:CLEar", _err_clean(err),
                      f"已发 `{clear_cmd}`；错误队列: {err}", raw=None)
            except Exception as e:  # noqa: BLE001
                # 12 个命令站点里最后一条漏排空的异常出口（内审 F2）——
                # 不排空则这条 CLEar 的错误漂到 ⑧c，把**对的** DL 吞吐量查询
                # 记成红，现场据此判它不支持。写超时后命令仍到达是常见形态。
                err = await _err()
                _step("⑧b 发 BTHRoughput:CLEar", False,
                      f"抛异常: {type(e).__name__}: {e}；错误队列: {err}", raw=None)
            await asyncio.sleep(window_s)
            after_v = await _probe("⑧c 清零后读一次吞吐量", tcmd, 6,
                                   lambda v, t: "progress=" + _at(v, t, 0))
            b0 = before_v[0] if before_v else None
            a0 = after_v[0] if after_v else None
            # `decided` = 这一步**真的判定了**吗（内审 F6）。以前恒 True ——
            # 于是 verdict 自己写着"本次无法判定"，步骤却报绿、summary 报"无失败步"。
            if b0 is None or b0 <= 0:
                decided = False
                verdict = ("⚠ **本次无法判定** —— 清零前 progress 本来就是 "
                           f"{_fmt(b0)}，没有可归零的累积。先让 UE attach + "
                           "起数据业务，等 progress 涨上去再跑本序列。")
            elif a0 is None:
                decided = False
                verdict = "⚠ 清零后读不到 progress，无法判定"
            elif a0 < b0:
                decided = True
                verdict = (f"清零前 {_fmt(b0)} → 清零后 {_fmt(a0)}，**变小了** —— "
                           "与 CLEar 生效一致（仍请跟面板确认）")
            else:
                decided = True
                verdict = (f"清零前 {_fmt(b0)} → 清零后 {_fmt(a0)}，**没变小** —— "
                           "可能 CLEar 没生效，也可能窗口内涨回去了；"
                           f"把 window_s 调小再跑一次可区分")
            _step("⑧ CLEar 能否圈窗口（结论）", decided, verdict, raw=None)

    finally:
        # ── 恢复：写过就必须写回（同 uxm_config_truth_probe 的纪律）──
        # ⚠ 判据用 `is not None and != ""`，不是真值判断（内审 F1）——
        #   `orig == ""` 是 falsy，会让恢复整条路径**静默跳过**，而 P1/P3 的
        #   detail 还写着"跑完写回"。**无论恢复与否都必须留一条步骤**，
        #   否则这份现场记录就在说假话。
        # ⚠ CLEar 不可逆 —— 这是 safe_during_test=False 的硬理由。
        async def _restore(touched, cmd, orig, what):
            if not (touched and cmd):
                return
            if orig is None or orig == "":
                _step(f"R 写回 {what}", False,
                      f"**没有写回** —— 原值读不到（该 `?` 形式手册未说明），"
                      f"不猜一个值写回去（原值可能本就是 ON，猜 OFF 更糟）。"
                      f"⚠ {what} 现被本序列留在 ON，请手动确认。", raw=None)
                return
            try:
                await _w(f"{cmd} {orig}")
            except Exception as e:  # noqa: BLE001
                err = await _err()
                _step(f"R 写回 {what}", False,
                      f"**恢复失败**（{type(e).__name__}: {e}）—— "
                      f"仪表可能仍开着 {what}，请手动确认。错误队列: {err}", raw=None)
                return
            # ⚠ SCPI 里 `_write` 返回**只代表传输成功**，命令被不被接受是从
            #   `SYSTem:ERRor?` 回来的（Codex #277 P1）。这一步以前写死 True ——
            #   跟内审 F4 修掉的 P1/P3 是同一个母题，我当时没扫到恢复段这个镜像。
            #   报"已恢复"而实际没恢复，比不恢复更糟：操作员不会再去手动确认，
            #   累积开着直接污染下一次测试。
            err = await _err()
            ok = _err_clean(err)
            _step(f"R 写回 {what}", ok,
                  (f"已恢复为 {orig!r}；错误队列: {err}") if ok else
                  (f"**恢复没生效** —— `{cmd} {orig}` 发出去了，但仪器把它记进了"
                   f"错误队列: {err}。⚠ {what} 可能仍被本序列留在 ON，"
                   f"会污染下一次测试的统计，**请手动关掉**。"), raw=None)

        await _restore(touched_state, state_cmd, orig_state, "BTHRoughput:STATe")
        await _restore(touched_report, report_cmd, orig_report, "MEASurement:REPort")

        # CSI：只在**本序列开之前它是 STOP** 时才关回去（内审 F5 + 代价不对称）。
        # 无脑发 STOP 会打断本来就在跑的 CSI；不关则下次真实测试的 `CSI:STARt`
        # 会被仪器**忽略**（手册原文），测出来的 CQI/RI 含本序列窗口的样本、被稀释。
        if touched_csi and csi_stop_cmd:
            if csi_pre_trusted and orig_csi and orig_csi.upper().startswith("STOP"):
                try:
                    await _w(csi_stop_cmd.format(cell=cell))
                except Exception as e:  # noqa: BLE001
                    err = await _err()
                    _step("R 关回 CSI 累积", False,
                          f"**恢复失败**（{type(e).__name__}: {e}）。错误队列: {err}",
                          raw=None)
                else:
                    # 同上：write 返回 ≠ 命令被接受（Codex #277 P1 的同母题镜像）
                    err = await _err()
                    ok = _err_clean(err)
                    _step("R 关回 CSI 累积", ok,
                          (f"本序列开之前是 {orig_csi!r}，已发 CSI:STOP 恢复；"
                           f"错误队列: {err}") if ok else
                          (f"**关回没生效** —— CSI:STOP 发出去了但进了错误队列: "
                           f"{err}。⚠ CSI 累积可能仍开着，下次真实测试的 "
                           f"`CSI:STARt` 会被仪器**忽略**，CQI/RI 会掺进本序列的"
                           f"样本、被稀释。**请手动 STOP**。"), raw=None)
            elif csi_pre_trusted and orig_csi:
                # 可信地读到「本来就在跑」—— 不关就是**正确的恢复**，判绿。
                _step("R 关回 CSI 累积", True,
                      f"**不关** —— 本序列开之前 CSI 状态是 {orig_csi!r}（可信读数，"
                      f"非 STOP），发 STOP 会打断本来就在跑的测量。", raw=None)
            else:
                # ⚠ 内审 F3：这一格里仪器**很可能本来是 STOP**，被本序列开着走了 ——
                #   报绿的话下面那句告警就挂在 ✅ 上，操作员不会去做。
                _step("R 关回 CSI 累积", False,
                      f"**没关，也不确定该不该关** —— 开之前读到的是 {orig_csi!r}，"
                      f"而这次读数{'的错误队列是脏的' if orig_csi else '没读到'}，"
                      f"**不可信**，所以不敢发 STOP（万一它本来在跑就被打断了）。"
                      f"⚠ 若确认之前没在跑，**请手动 STOP** —— 否则下次 "
                      f"`CSI:STARt` 会被仪器忽略、CQI/RI 会掺进本序列的样本"
                      f"（那是**静默错数**，比报错更难发现）。", raw=None)

    failed = [s.label for s in steps if not s.success]
    return SequenceRunResult(
        success=not failed,
        summary=(
            f"KPI 回读对账完成（方言 {profile_name}，小区 {cell}）：{len(steps)} 步，"
            + (f"**{len(failed)} 步失败**: {failed}" if failed else "无失败步")
            + "。⚠️ 本序列**只呈现不判定** —— 每步的 raw 是仪器原样回复，"
              "候选读法写在 detail 里，请对着仪表面板逐条挑，"
              "结论回填 roadmap 的『#275 整批必须现场核验』条。"
        ),
        steps=steps,
        extra={"profile": profile_name, "cell": cell, "window_s": window_s},
    )
