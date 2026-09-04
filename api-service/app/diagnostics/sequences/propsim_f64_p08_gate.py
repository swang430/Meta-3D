"""F64 P0-8a 门序列 (`propsim_f64_p08_gate`) — P0-8 出发前半的唯一合法载体 (P1-24)。

P0-8 的现场协议 (`docs/guides/on-site-debug-protocol.md` Phase 1.5) 要求在正式测试前
用一条**可归档、可复跑**的剧本证明: p08 场景包加载得上、输入参考闭环收敛、运行中改参
写得进、旁路态电平读得出。之前这段只存在于协议散文里, 现场要么手敲 SCPI 要么写临时
脚本 —— 两者都被规矩禁了 (memory `feedback_instrument_debug_via_diagnostic_sequence`)。

**手册依据** (NotebookLM「PROPSIM 资料」`982222b7-4953-46cd-9949-00fa97882353`,
2026-08-01 查证, 详表见 `docs/design/p1-24-f64-p08-gate-sequence.md` §0):

- 加载 = CLOSE → CALC:FILT:FILE → *OPC?(长超时) → SYST:ERR? → STATE?==STOPPED
  (ATE AN §5.3; 生产事务 `load_local_scenario` 已按此实现, 本剧本**复用不复制**)。
- `INP:LEV:AUTOSET` 是 **stopped 态**命令 (§20.4.4.7) —— 所以排在 GO **之前**
  (已 merge 协议曾把它排在 run 后, 本片随行纠错)。失败 (无信号/过强) = 设备错误进
  队列, **手册没有任何 -300 之类的哨兵返回值** (同为本片纠错的对象)。
- clipping / cut-off 的正确读法 = `SYST:STAT?` (§20.4.2.5): 返回 `1`=干净, 否则
  `0,<src>,...` 列出 `Input cut-off` / `Digital Clipping` 等。
- `OUTP:GAIN:CH <out>,<dB>` RUNNING/STOPPED 均合法 (ATE AN §2.5); 查询形式
  `OUTP:GAIN:CH? <out>` 返回纯数字 dB (§20.4.5.7); 范围用 `OUTP:GAIN:LIM? <out>`
  (§20.4.5.8) —— **超范围会被静默钳到最近合法值**, 所以改参后必须回读比对,
  钳位与未生效都在回读断言处现形。这两条查询是生产驱动未用过的**新增 SCPI**,
  已按「新增 SCPI 先查 NotebookLM」过手册 (2026-08-01)。
- `INP:LEV:MEAS? <in>,<t>` 运行态合法 ("所有查询类命令运行中合法", ATE AN §2.5);
  旁路态手册未涵盖 → 旁路电平这步**只如实记录**, 不预设它该等于什么。
  校准旁路本身 = 单径模型 **-10 dB 信道增益** (ATE AN §2.4.5), 影响的是输出侧;
  输入测量量的是 UXM 打进来的信号, 旁路前后理应同窗口可读 —— 这正是本步的判据
  (读得出), 不是数值断言。

**排雷** (与设计稿 v1 的两处偏差, 实现期修正, 见设计稿 §0.4):

1. 退旁路**不假设自动续跑**: 手册 ATE AN §2.4.5 说"进旁路前在跑→退旁路后继续跑",
   但 2026-07-03 现场实证 (test_f64_bypass_state_machine.py 头注) 是**恢复衰落 =
   STATIC 0 + 显式 GO**。物理现实定案: 退旁路后读 STATE? **如实记录**, 非 RUNNING
   则显式 GO 恢复 —— 两种固件行为都走得通, 且把答案归档 (F64R-7 邻接问题)。
2. 收尾**不发 CLOSE**: 剧本若绕过驱动直发 CLOSE, 驱动的 `_loaded_emulation_file`
   身份缓存会变 stale (验证打在真实生效端母题)。场景包留驻 + GOS 停住即收尾;
   正式测试的加载事务自己带 CLOSE preflight。

**复用生产原子** (不自开 socket, 不重抄事务): `load_local_scenario` /
`autoset_inputs` (fail-loud 版, 区别于无错误门的 `autoset_input_level`) /
`start_emulation` / `stop_emulation` / `set_bypass_mode` / `set_output_gain` /
`measure_input`。剧本级直查 (`_query`) 只用于**原样归档**回读值与零残留检查。

**前置声明**: UXM 满 RB DL 已激活是 CE↔BS 协调的操作员确认项, 序列不隐式假设 ——
参数 `uxm_dl_confirmed` 必须显式传 JSON true 才开跑。

会改仪器状态 (加载/GO/旁路/增益), 故 `safe_during_test=False`。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)

# 复用不复制: 错误码解析 / await 包装 / STATE? 七态归一 都已有单一真值源。
from app.diagnostics.sequences.propsim_f64_health import _maybe_await, _parse_err
from app.diagnostics.sequences.propsim_f64_state_machine import classify_state
from app.hal.propsim_f64 import F64BypassMode
from app.services.diagnostic_context import DiagnosticContext
from app.hal.channel_emulator_manifest import channel_emulator_implements


metadata = SequenceMetadata(
    name="PROPSIM F64 P0-8a 门序列",
    description=(
        "P0-8 出发前半的门剧本: 加载 p08 场景包(生产事务) → AUTOSET 输入参考"
        "(stopped 态) → SYST:STAT? 收敛判定 → GO → 运行中 ±Δ 增益往返(写后回读) → "
        "衰落/旁路两态 INP:LEV:MEAS? → 还原并停住。每步后核错误队列零残留。"
        "前置: UXM 满 RB DL 已激活(参数显式确认)。会改仪器状态。"
    ),
    required_categories=["channelEmulator"],
    params_schema=[
        {"name": "uxm_dl_confirmed",
         "label": "UXM 满 RB DL 已激活 (操作员确认, 必须勾选)",
         "type": "boolean", "default": False},
        {"name": "smu_path",
         "label": ".smu 场景包路径 (SCD 里 N78/ARFCN 636666/BW40 那行的关联文件)",
         "type": "string", "default": ""},
        {"name": "input_num", "label": "输入端口号 (UXM DL 接入)", "type": "number",
         "default": 1},
        {"name": "output_num", "label": "输出端口号 (增益往返用)", "type": "number",
         "default": 1},
        {"name": "gain_delta_db", "label": "增益往返 Δ (dB, 最小扰动)", "type": "number",
         "default": 1.0},
    ],
    safe_during_test=False,
)

# INP:LEV:MEAS? / AUTOSET 的测量窗口 (§20.4.4.6 合法档 0.5/1/3/5/10)。
# 衰落态与旁路态用**同一窗口**, 否则两次读数不可比 (设计判据原文"与衰落态同窗口")。
_MEAS_TIME_S = 3.0

# 增益回读比对容差 (dB)。回读是 §20.4.5.7 的纯数字 dB, 只防浮点格式化误差;
# 钳位 (§20.4.5.8) 造成的偏差远大于此, 会被这道断言抓住。
_GAIN_TOL_DB = 0.05

# Δ 上限 (dB)。门的目的是最小扰动验证写路径, 不是扫增益 —— 手滑传大 Δ 会真动
# 链路电平, 影响在测的 UXM DL。
_GAIN_DELTA_MAX_DB = 3.0

# Δ 下限 (dB, Codex #260 R1): |Δ| ≤ 回读容差 (0.05) 时, 写被忽略也能过回读断言
# (|orig-target| ≤ 容差恒真); Δ < 命令两位小数分辨率 (0.01) 时写串还会四舍五入回
# 原值 —— 两种情况写路径门都在空转。0.1 = 容差与分辨率之上留一档余量。
_GAIN_DELTA_MIN_DB = 0.1

# 剧本要求的 **F64 私有**原子 —— 缺任何一个说明 ce 不是 PROPSIM 驱动 (或版本不符), 拒跑。
#
# ⚠️ P2-57（内审 F1）：`start_emulation` / `stop_emulation` **已从本元组移出**。
#    它们是 `ChannelEmulatorDriver` 的**共同**操作，P2-57 给基类补齐 14 个
#    NotImplementedError 桩之后，`hasattr` 对任何 CE 驱动恒为真 —— 留在这里
#    等于一条永远通过的空门。共同操作的能力改由 manifest 回答（见下方 `_MANIFEST_OPS`）。
_REQUIRED_METHODS = (
    "load_local_scenario", "autoset_inputs",
    "set_bypass_mode", "set_output_gain", "measure_input",
)

#: 本剧本还要用到的**共同**操作 —— 走 manifest，不走 hasattr。
_MANIFEST_OPS = ("start_emulation", "stop_emulation")


class _Abort(RuntimeError):
    """中止剧本但**仍要走收尾还原** —— 语义同 propsim_f64_state_machine._Abort:
    "把仪器还原成接手时的样子"必须是所有退出路径的共同出口。"""


class _Gate:
    """步骤记录 + 剧本级回读/零残留检查。

    生产原子 (load/GO/STATIC/GAIN) 自带 drain→写→错误门, 剧本不重抄; 本类只补
    两件生产方法不做的事: ① 把关键回读的**仪器原样回复**记进 ``step.raw``
    (归档比对用, 协议字段约定见 protocol.SequenceStepResult), ② 每步之后核
    错误队列**零残留** (P0-8a 判据之一)。
    """

    def __init__(self, ce: Any, log: Callable[[str], None]) -> None:
        self._ce = ce
        self._log = log
        self.steps: List[SequenceStepResult] = []

    async def _q(self, cmd: str, timeout: Optional[int] = None) -> Optional[str]:
        if timeout is not None:
            raw = await _maybe_await(self._ce._query(cmd, timeout=timeout))  # noqa: SLF001
        else:
            raw = await _maybe_await(self._ce._query(cmd))  # noqa: SLF001
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    def add(self, label: str, success: bool, detail: str,
            raw: Optional[str], started: float) -> SequenceStepResult:
        step = SequenceStepResult(
            label=label, success=success, detail=detail,
            duration_ms=int((time.monotonic() - started) * 1000), raw=raw,
        )
        self.steps.append(step)
        self._log(f"  {'✓' if success else '✗'} {label}: {detail}"
                  + (f"  raw={raw!r}" if raw is not None else ""))
        return step

    async def run_atom(self, label: str, coro_factory: Callable[[], Any],
                       ok_detail: str) -> bool:
        """跑一个生产原子 (返回 bool 的驱动方法), 失败时把 `_last_error` 带出来。"""
        started = time.monotonic()
        try:
            ok = bool(await _maybe_await(coro_factory()))
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"异常 {type(e).__name__}: {e}", None, started)
            return False
        detail = ok_detail if ok else (
            f"驱动返回失败: {getattr(self._ce, '_last_error', None) or '见驱动日志'}")
        self.add(label, ok, detail, None, started)
        return ok

    async def read_state(self, label: str, *, expect: Optional[str] = None) -> Optional[str]:
        """STATE? 一次, 原样归档。expect 语义同 state_machine.read_state:
        传 = 已知目标必须核; 不传 = 待测未知量只记录 (旁路下/退旁路后报什么)。"""
        started = time.monotonic()
        try:
            raw = await self._q("DIAG:SIMU:STATE?")
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"查询异常 {type(e).__name__}: {e}", None, started)
            return None
        state, note = classify_state(raw)
        ok = state is not None if expect is None else state == expect
        detail = state or note
        if expect is not None and state != expect:
            detail = f"期望 {expect}, 实际 {state or note}"
        self.add(label, ok, detail, raw, started)
        return state

    async def read_float(self, label: str, cmd: str) -> Optional[float]:
        """单值数字回读 (OUTP:GAIN:CH? 形态, §20.4.5.7 纯数字 dB), 原样归档。"""
        started = time.monotonic()
        try:
            raw = await self._q(cmd)
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"查询异常 {type(e).__name__}: {e}", None, started)
            return None
        try:
            val = float((raw or "").strip().strip('"'))
        except ValueError:
            self.add(label, False, f"回复解析不出数字: {raw!r}", raw, started)
            return None
        self.add(label, True, f"{val}", raw, started)
        return val

    async def read_float_pair(self, label: str, cmd: str) -> Optional[Tuple[float, float]]:
        """双值回读 (OUTP:GAIN:LIM? 的 "<lo>,<hi>", §20.4.5.8), 原样归档。"""
        started = time.monotonic()
        try:
            raw = await self._q(cmd)
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"查询异常 {type(e).__name__}: {e}", None, started)
            return None
        try:
            parts = (raw or "").strip().split(",")
            pair = (float(parts[0]), float(parts[1]))
        except (ValueError, IndexError):
            self.add(label, False, f"回复解析不出两个数字: {raw!r}", raw, started)
            return None
        self.add(label, True, f"{pair[0]},{pair[1]}", raw, started)
        return pair

    async def read_syst_stat(self, label: str, *, record_only: bool = False) -> Optional[bool]:
        """SYST:STAT? (§20.4.2.5): "1"=干净; "0,<src>,..." 列出活跃告警。
        返回 True/False/None(读不出)。clipping / cut-off 的**正确读法**就是这条
        (设计稿 §0 纠错点: 不是去猜某个哨兵返回值)。

        `record_only`: P0-8a 判据只含 **AUTOSET 后**那次 STAT 必须干净; 旁路下那次
        是待归档观测 (旁路态告警语义手册未涵盖) —— 只记录不判失败, 语义同
        state_machine.read_state 的 expect 传/不传之分。查询异常仍算失败 (读都读
        不出跟"读出了告警"是两回事)。"""
        started = time.monotonic()
        try:
            raw = await self._q("SYST:STAT?")
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"查询异常 {type(e).__name__}: {e}", None, started)
            return None
        norm = (raw or "").strip()
        if norm == "1":
            self.add(label, True, "干净 (无活跃告警)", raw, started)
            return True
        if norm.startswith("0"):
            srcs = [p.strip() for p in norm.split(",")[1:] if p.strip()]
            self.add(label, record_only,
                     f"活跃告警: {', '.join(srcs) or '(未列明)'}"
                     + (" (只记录)" if record_only else ""), raw, started)
            return False
        self.add(label, record_only, f"非预期格式: {raw!r}", raw, started)
        return None

    async def residue(self, label: str) -> bool:
        """错误队列零残留检查: SYST:ERR? 循环读到 `0,"No error"` (FIFO §20.5.4,
        上界 100)。生产原子各自的错误门已消费过自己产生的错误 —— 这里读到的任何
        非零条目都是**没人认领的意外**, 判失败并原样归档。读不出错误码 = 队列
        状态未知, 同样不能当干净 (判据与 state_machine.clear_error_queue 同源)。"""
        started = time.monotonic()
        drained: List[str] = []
        try:
            for _ in range(100):
                raw = await self._q("SYST:ERR?")
                code, _text = _parse_err(raw or "")
                if code == 0:
                    break
                if code is None:
                    self.add(label, False,
                             f"SYST:ERR? 读不出错误码 ({raw!r}) — 队列状态未知, 不能当干净",
                             raw, started)
                    return False
                drained.append((raw or "").strip())
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"读队列异常 {type(e).__name__}: {e}", None, started)
            return False
        if drained:
            self.add(label, False, f"残留 {len(drained)} 条未认领错误",
                     "; ".join(drained), started)
            return False
        self.add(label, True, "零残留", None, started)
        return True


def _reject(reason: str) -> SequenceRunResult:
    return SequenceRunResult(success=False, summary=reason)


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    drivers = getattr(hal, "drivers", {}) or {}
    ce = drivers.get("channelEmulator")
    if ce is None:
        return _reject(driver_not_loaded_summary("channelEmulator"))

    refusal = mock_driver_refusal_summary("channelEmulator", ce)
    if refusal:
        return _reject(refusal)

    missing = [m for m in _REQUIRED_METHODS if not hasattr(ce, m)]
    # 共同操作按 manifest 判（P2-57 内审 F1）
    missing += [
        m for m in _MANIFEST_OPS if not channel_emulator_implements(ce, m)
    ]
    if missing or not hasattr(ce, "_query"):
        return _reject(
            f"CE 驱动 {type(ce).__name__} 缺本剧本要求的生产原子: "
            f"{', '.join(missing) or '_query'} —— 本剧本按 PROPSIM F64 驱动的"
            "生产事务编排, 需要真实 PROPSIM 驱动。"
        )

    # ── 参数门。全部显式校验, 不做真值强转 (state_machine 同款纪律:
    #    JSON 字符串 "true" 经 bool() 是 True, 会把"没确认"变成"确认过")。
    if params.get("uxm_dl_confirmed") is not True:
        return _reject(
            "uxm_dl_confirmed 未显式确认 (必须是 JSON true) —— UXM 满 RB DL 是本门的"
            "物理前置: AUTOSET 对着没信号的输入跑必然报设备错误, 跑了也白跑。"
            "先在 UXM 上激活满 RB DL (CE↔BS 协调), 确认后勾选此参数再跑。"
        )
    smu_path = params.get("smu_path")
    if not isinstance(smu_path, str) or not smu_path.strip():
        return _reject(
            "smu_path 为空 —— 本门要加载 p08 场景包 (拍板默认: SCD 登记的 "
            "N78 / ARFCN 636666 / BW40 那条, 实测频率已验)。路径查 GUI 仪器抽屉"
            "「信道模型」或 standard_channel_definitions.associated_file_path, "
            "填 F64 本地路径 (D:\\...) 后再跑。"
        )
    smu_path = smu_path.strip()
    input_num = params.get("input_num", 1)
    output_num = params.get("output_num", 1)
    for name, val in (("input_num", input_num), ("output_num", output_num)):
        if type(val) is not int or val < 1:
            return _reject(
                f"{name}={val!r} 非法 —— 必须是 ≥1 的 JSON 整数 (端口号)。"
            )
    delta = params.get("gain_delta_db", 1.0)
    if (type(delta) not in (int, float)
            or not (_GAIN_DELTA_MIN_DB <= abs(delta) <= _GAIN_DELTA_MAX_DB)):
        return _reject(
            f"gain_delta_db={delta!r} 非法 —— 必须是 {_GAIN_DELTA_MIN_DB}≤|Δ|≤"
            f"{_GAIN_DELTA_MAX_DB} 的数字。上限防手滑真动在测链路电平; 下限防门空转: "
            f"|Δ|≤回读容差 ({_GAIN_TOL_DB}) 时写被忽略也能过回读断言 (Codex #260 R1)。"
        )
    delta = float(delta)

    g = _Gate(ce, log)
    findings: Dict[str, Any] = {}
    aborted: Optional[str] = None

    # 还原簿记: 只记"我们动过什么", 还原段对着当前实际值收敛。
    gain_orig: Optional[float] = None
    gain_moved = False
    bypass_entered = False

    try:
        # ── ① 加载 p08 场景包 —— 生产事务 (CLOSE→复查 CLOSED→FILE→*OPC? 长超时→
        #     错误门→CENT:CH? 回读真频), 剧本不重抄。
        log(f"  · 加载场景包: {smu_path}")
        if not await g.run_atom("加载 p08 场景包 (load_local_scenario)",
                                lambda: ce.load_local_scenario(smu_path),
                                f"已加载 {smu_path} (真频以 CENT:CH? 回读为准)"):
            raise _Abort("场景包加载失败 — 后续全部无从谈起")

        # ── ② 加载后必须是 STOPPED (已驻留未启动) —— AUTOSET 的 stopped 态前提。
        #     residue 排在 STATE? **之后** (Codex #260 R2): 排在前面的话, STATE?
        #     直查若压了错, 会被下一个原子 (AUTOSET) 事务开头的 drain 静默吞掉 ——
        #     零残留判据对这个窗口就是空转。residue 必须紧贴"下一个会 drain 的
        #     原子"之前, 兜住它前面所有直查。后同。
        if await g.read_state("加载后 STATE?", expect="STOPPED") != "STOPPED":
            raise _Abort("加载后不在 STOPPED — AUTOSET 的 stopped 态前提不成立")
        if not await g.residue("加载与读态后错误队列"):
            raise _Abort("加载与读态后错误队列有残留/未知")

        # ── ③ AUTOSET 输入参考闭环 (stopped 态命令, §20.4.4.7) —— 排在 GO 之前,
        #     这正是本片对已 merge 协议的时序纠错。用 fail-loud 的 autoset_inputs
        #     (清 stale→AUTOSET→*OPC?→错误门), 不用无错误门的 autoset_input_level。
        if not await g.run_atom(f"AUTOSET 输入 {input_num} (stopped 态)",
                                lambda: ce.autoset_inputs([input_num], _MEAS_TIME_S),
                                f"输入 {input_num} 参考已按测量收敛 (t={_MEAS_TIME_S}s)"):
            raise _Abort(
                "AUTOSET 失败 (设备错误: 无信号/过强) — 先查 UXM 满 RB DL 是否真在发"
            )
        # ── ④ 收敛判定: SYST:STAT? 必须干净 (无 Input cut-off / Digital Clipping)。
        stat = await g.read_syst_stat("AUTOSET 后 SYST:STAT?")
        findings["syst_stat_after_autoset"] = g.steps[-1].raw
        if stat is not True:
            raise _Abort("AUTOSET 后 SYST:STAT? 不干净 — 输入参考没收敛, 不带病 GO")
        # residue 贴在 GO (下一个会 drain 的原子) 之前, 同时兜 AUTOSET 与 STAT? 直查。
        if not await g.residue("AUTOSET 与收敛判定后错误队列"):
            raise _Abort("AUTOSET 与收敛判定后错误队列有残留/未知")

        # ── ⑤ GO —— 生产事务 (drain→STATIC 0→GO→*OPC?→错误门→STATE? 终态确认)。
        if not await g.run_atom("GO (start_emulation)", lambda: ce.start_emulation(),
                                "仿真已启动"):
            raise _Abort("GO 失败 — 见驱动错误")
        # 判据 RUNNING 断言 #1 (剧本级回读原样归档, 不只信驱动布尔)。
        if await g.read_state("GO 后 STATE?", expect="RUNNING") != "RUNNING":
            raise _Abort("GO 后不在 RUNNING")
        findings["state_after_go"] = g.steps[-1].raw

        # ── ⑥ 运行中改参: ±Δ 增益往返。先读范围与原值 (§20.4.5.7/8, 新增 SCPI
        #     已过手册), 超上限就往下走 —— 超范围写会被**静默钳位**, 回读断言负责现形。
        limits = await g.read_float_pair(f"OUTP:GAIN:LIM? {output_num}",
                                         f"OUTP:GAIN:LIM? {output_num}")
        if limits is None:
            raise _Abort("增益范围读不到 — 不盲写")
        lo, hi = limits
        findings["gain_limits"] = [lo, hi]
        gain_orig = await g.read_float(f"OUTP:GAIN:CH? {output_num} (原值)",
                                       f"OUTP:GAIN:CH? {output_num}")
        if gain_orig is None:
            raise _Abort("增益原值读不到 — 不知道该还原到哪, 不动")
        findings["gain_orig_db"] = gain_orig
        # residue 贴在写增益 (下一个会 drain 的原子) 之前 — 兜 GO 后 STATE?/LIM?/原值三条直查。
        if not await g.residue("GO 与增益读后错误队列"):
            raise _Abort("GO 与增益读后错误队列有残留/未知")
        # 方向选择: 首选 orig+Δ, 越界则翻到 orig-Δ —— 两个候选都做**双界**检查
        # (Codex #260 R1: 原写法首选只查上界, 负 Δ 在 orig 贴下限时选出越下界的
        # 候选直接中止, 而反方向明明合法)。
        cand_fwd, cand_rev = gain_orig + delta, gain_orig - delta
        if lo - 1e-9 <= cand_fwd <= hi + 1e-9:
            target = cand_fwd
        elif lo - 1e-9 <= cand_rev <= hi + 1e-9:
            target = cand_rev
        else:
            raise _Abort(
                f"增益窗口 [{lo},{hi}] 放不下原值 {gain_orig}±{delta} 的往返 — 不硬写"
            )
        gain_moved = True  # 从这里起, 还原段要负责把增益放回 gain_orig
        if not await g.run_atom(f"OUTP:GAIN:CH {output_num},{target:.2f} (运行中改参)",
                                lambda: ce.set_output_gain(output_num, target),
                                f"已写 {target:.2f} dB"):
            last_error = str(getattr(ce, "_last_error", "") or "")
            if "未获权威回读确认" in last_error:
                raise _Abort(f"{last_error} — 写路径没真生效或被钳位")
            raise _Abort("运行中增益写入失败")
        back = await g.read_float(f"OUTP:GAIN:CH? {output_num} (改参后回读)",
                                  f"OUTP:GAIN:CH? {output_num}")
        findings["gain_target_db"] = target
        findings["gain_readback_db"] = back
        if back is None or abs(back - target) > _GAIN_TOL_DB:
            raise _Abort(
                f"增益回读 {back} ≠ 目标 {target:.2f} (±{_GAIN_TOL_DB}) — "
                "写路径没真生效或被钳位"
            )
        if not await g.residue("改参后错误队列"):
            raise _Abort("改参后错误队列有残留/未知")

        # ── ⑦ 衰落态输入电平 (运行中查询合法, ATE AN §2.5)。
        started = time.monotonic()  # 先取再测 — 3s 窗口的耗时是归档量 (内审 F3)
        fading = await _maybe_await(ce.measure_input(input_num, _MEAS_TIME_S))
        if fading is None:
            g.add("衰落态 INP:LEV:MEAS?", False,
                  "测量失败 (设备错误: 无信号/过强)", None, started)
            raise _Abort("衰落态输入电平读不出")
        g.add("衰落态 INP:LEV:MEAS?", True,
              f"avg={fading[0]} dBm, crest={fading[1]} dB (t={_MEAS_TIME_S}s)",
              None, started)
        findings["fading_level"] = {"avg_dbm": fading[0], "crest_db": fading[1]}
        # measure_input 没有自带错误门, 且下一个生产原子的事务会先 drain ——
        # 不在这里核, 无主错误会被静默吞掉, "每步后零残留"就成了假声明。
        if not await g.residue("衰落态测量后错误队列"):
            raise _Abort("衰落态测量后错误队列有残留/未知")

        # ── ⑧ 进校准旁路 (STATIC 3) —— 生产方法 (drain→STATIC→错误门→幂等消歧)。
        #     2026-07-03 实证: 运行态切 STATIC≠0 会自动暂停 → 旁路下 STATE? 只记录。
        bypass_entered = True  # 先记账再动手: 写一半失败也要还原
        if not await g.run_atom("进校准旁路 (set_bypass_mode STATIC 3)",
                                lambda: ce.set_bypass_mode(F64BypassMode.CALIBRATION),
                                "已进校准旁路 (单径 -10 dB, ATE AN §2.4.5)"):
            raise _Abort("进旁路失败")
        await g.read_state("旁路下 STATE? (只记录, 手册未定义)")
        findings["state_in_bypass"] = g.steps[-1].raw
        if not await g.residue("进旁路后错误队列"):
            raise _Abort("进旁路后错误队列有残留/未知")

        # ── ⑨ 旁路态输入电平 —— 判据是**读得出** (与衰落态同窗口), 不是数值断言:
        #     旁路态下 MEAS? 的有效性手册未涵盖, 数值只归档供下次现场比对。
        started = time.monotonic()  # 同上 (内审 F3)
        bypass_lv = await _maybe_await(ce.measure_input(input_num, _MEAS_TIME_S))
        if bypass_lv is None:
            g.add("旁路态 INP:LEV:MEAS?", False,
                  "测量失败 — 旁路态读不出输入电平 (归档: 手册未涵盖此态)", None, started)
            raise _Abort("旁路态输入电平读不出 (P0-8a 判据之一)")
        g.add("旁路态 INP:LEV:MEAS?", True,
              f"avg={bypass_lv[0]} dBm, crest={bypass_lv[1]} dB (与衰落态同窗口)",
              None, started)
        findings["bypass_level"] = {"avg_dbm": bypass_lv[0], "crest_db": bypass_lv[1]}
        await g.read_syst_stat("旁路下 SYST:STAT? (只记录)", record_only=True)
        findings["syst_stat_in_bypass"] = g.steps[-1].raw
        if not await g.residue("旁路态测量后错误队列"):
            raise _Abort("旁路态测量后错误队列有残留/未知")

        # ── ⑩ 退旁路 + 恢复运行。**不假设自动续跑** (手册说续、2026-07-03 实证不续):
        #     读 STATE? 如实记录, 非 RUNNING 则显式 GO —— 判据 RUNNING 断言 #2。
        if not await g.run_atom("退旁路 (set_bypass_mode STATIC 0)",
                                lambda: ce.set_bypass_mode(F64BypassMode.DISABLED),
                                "已退旁路"):
            raise _Abort("退旁路失败 — 仪器可能仍在旁路中")
        bypass_entered = False  # 已确认退出, 还原段无需再管
        after_exit = await g.read_state("退旁路后 STATE? (只记录: 续不续跑是待验语义)")
        findings["state_after_bypass_exit"] = g.steps[-1].raw
        if after_exit != "RUNNING":
            # 显式 GO 会 drain — 先兜住上面那条 STATE? 直查可能压的错。
            if not await g.residue("退旁路读态后错误队列"):
                raise _Abort("退旁路读态后错误队列有残留/未知")
            if not await g.run_atom("显式 GO 恢复 (固件未自动续跑)",
                                    lambda: ce.start_emulation(), "已恢复运行"):
                raise _Abort("退旁路后显式 GO 恢复失败")
        if await g.read_state("恢复后 STATE?", expect="RUNNING") != "RUNNING":
            raise _Abort("退旁路后未能恢复 RUNNING")
        if not await g.residue("退旁路后错误队列"):
            raise _Abort("退旁路后错误队列有残留/未知")

    except _Abort as e:
        aborted = str(e)
    except Exception as e:  # noqa: BLE001
        aborted = f"剧本中断: {type(e).__name__}: {e}"

    # ── 收尾还原 —— 所有退出路径的共同出口, 对着当前实际值收敛, 不假设主流程
    #    走到了哪 (state_machine 同款教训: 中途裸 return 会把仪器留在中间态)。
    try:
        # 还原-0 (内审 F1): **中止时先把队列残余原样归档, 再动还原原子** ——
        # 测量/回读失败的中止路径 (衰落 MEAS? 设备错误正是本门要诊断的对象) 会把
        # 错误字面值留在队列里, 而下面第一个生产原子的事务 drain 会把它静默吞掉
        # (只进 logger), 归档里真因零出现、末尾还写着假"零残留"。residue 本身
        # 就带原样归档; 返回值不消费 —— 收尾还原无论如何要继续走。
        if aborted is not None:
            await g.residue("中止后错误队列 (先归档再还原)")
        # 还原-1 旁路: 只在剧本可能把它留在非 0 档时收敛。
        if bypass_entered:
            cur = await g.read_float("还原前 MODEL:STATIC?", "DIAG:SIMU:MODEL:STATIC?")
            if cur is None:
                g.add("还原旁路档 (放弃)", False,
                      "当前档位读不到 — 不猜; 接手时为衰落 (STATIC 0), 请人工核对",
                      None, time.monotonic())
            elif cur != 0:
                if await g.run_atom("还原旁路档 STATIC 0",
                                    lambda: ce.set_bypass_mode(F64BypassMode.DISABLED),
                                    "已退旁路"):
                    await g.read_float("还原后 MODEL:STATIC?", "DIAG:SIMU:MODEL:STATIC?")
            else:
                g.add("还原旁路档 (无需)", True, "已在 STATIC 0", None, time.monotonic())
        # 还原-2 增益: 只要动过就放回原值, 并回读核对。
        if gain_moved and gain_orig is not None:
            cur_gain = await g.read_float(f"还原前 OUTP:GAIN:CH? {output_num}",
                                          f"OUTP:GAIN:CH? {output_num}")
            if cur_gain is not None and abs(cur_gain - gain_orig) <= _GAIN_TOL_DB:
                g.add("还原增益 (无需)", True, f"已是 {cur_gain} dB", None, time.monotonic())
            elif await g.run_atom(f"还原增益 → {gain_orig:.2f} dB",
                                  lambda: ce.set_output_gain(output_num, gain_orig),
                                  f"已还原 {gain_orig:.2f} dB"):
                back = await g.read_float(f"还原后 OUTP:GAIN:CH? {output_num}",
                                          f"OUTP:GAIN:CH? {output_num}")
                if back is None or abs(back - gain_orig) > _GAIN_TOL_DB:
                    g.add("还原增益核对", False,
                          f"回读 {back} ≠ 原值 {gain_orig:.2f} — 请人工核对",
                          None, time.monotonic())
        # 还原-3 停住: 对着 STATE? 收敛 (RUNNING 才停; 收尾稳态 = 场景包留驻 + STOPPED)。
        #     不发 CLOSE — 直发会让驱动身份缓存变 stale, 正式测试的加载事务自带
        #     CLOSE preflight (docstring 排雷 #2)。
        now = await g.read_state("收尾前 STATE?")
        if now == "RUNNING":
            if await g.run_atom("收尾 GOS (stop_emulation)", lambda: ce.stop_emulation(),
                                "已停住并倒回 (场景包留驻)"):
                await g.read_state("收尾后 STATE?", expect="STOPPED")
        elif now in ("STOPPED", "CLOSED"):
            # CLOSED = 未加载 (如加载失败中止), 是最干净的稳态 —— 别喊人工核对
            # (内审 F2; 口径与 stop_emulation 把 CLOSED 当"确保停止已达成"同源)。
            g.add("收尾停住 (无需)", True,
                  "已是 STOPPED (场景包留驻)" if now == "STOPPED"
                  else "CLOSED (未加载, 干净稳态)", None, time.monotonic())
        else:
            g.add("收尾停住 (放弃)", False,
                  f"当前状态 {now or '读不到'} 非 RUNNING/STOPPED — 不硬闯, 请人工核对",
                  None, time.monotonic())
        await g.residue("收尾错误队列")

        ok = all(s.success for s in g.steps) and aborted is None
        # 关键数值写进 summary — 归档 2048 字节截断保头部, 步骤长表会被切
        # (state_machine 同款教训)。
        nums: List[str] = []
        if "fading_level" in findings:
            nums.append(f"衰落 avg={findings['fading_level']['avg_dbm']} dBm")
        if "bypass_level" in findings:
            nums.append(f"旁路 avg={findings['bypass_level']['avg_dbm']} dBm")
        if findings.get("gain_readback_db") is not None:
            nums.append(
                f"增益往返 {findings.get('gain_orig_db')}→{findings.get('gain_readback_db')} dB")
        head = f"⚠ {aborted} | " if aborted else ""
        return SequenceRunResult(
            success=ok,
            summary=(head + f"P0-8a 门 {'PASS' if ok else 'FAIL'} ({len(g.steps)} 步)"
                     + (": " + ", ".join(nums) if nums else "")),
            steps=g.steps,
            extra=findings,
        )
    except Exception as e:  # noqa: BLE001
        return SequenceRunResult(
            success=False,
            summary=(f"收尾还原中断: {type(e).__name__}: {e} — 仪器可能停在中间态"
                     + (f" (先前已中止: {aborted})" if aborted else "")
                     + ", 请人工确认旁路档/增益/运行态"),
            steps=g.steps,
            extra=findings,
        )
