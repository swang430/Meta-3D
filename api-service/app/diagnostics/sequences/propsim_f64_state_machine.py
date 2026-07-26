"""F64 状态机语义探测剧本 —— 记录 `DIAG:SIMU:STATE?` 的**字面返回值**。

现场验证的问题分两类:

- **通不通**(这条命令支不支持)→ `propsim_f64_health` 那种只读普查就够了。
- **返回什么字面值**(GOS 之后 `STATE?` 报什么 / 旁路下报什么)→ 需要**带动作的
  剧本**: 发命令 → 等完成 → 查错 → 再问状态, 并把仪器吐出来的原样记下来。

本剧本是第二类的载体, 直接服务 **F64R-7**(`docs/guides/onsite-20260721-todo.md`):
F64R-1(#225)把 `DIAG:SIMU:STATE?` 接成了运行状态的**唯一判据** —— GO 成不成、
GOS 停没停、监控面报不报"在跑"全看它。手册对七态写得很死, 但**有两处手册管不到**,
且我们有相反的现场实证:

  ① GOS 之后 `STATE?` 到底报什么(2026-07-21 现场注释记着"本固件下 GOS 在运行态
     未观察到真停")—— 若属实, `stop_emulation()` 会恒返回 False。
  ② 旁路(STATIC 1/2/3)下 `STATE?` 报什么 —— 手册七态里**没有 BYPASS 态**。

**手册依据**(NotebookLM「PROPSIM 资料」`982222b7-4953-46cd-9949-00fa97882353`,
2026-07-26 查):

- **RUNNING 态再发 GO** → §20.5.2 `-200,"Wrong device state for command"`;错误不清
  会堆到 §20.5.5 `-350` 队列溢出并阻塞通信。**所以本剧本每一步都先查状态再决定发不发**,
  且每步后读一次 `SYST:ERR?`。
- **`GOS` = 停止**并**倒回起点**(§20.4.3.11);`DIAG:SIMU:STOP` 才是不倒回的暂停
  (§20.4.3.10)。**驱动的 `stop_emulation()` 用的正是 GOS** —— 所以本剧本验的就是它,
  代价是仿真时间轴被清零(见 `probe_gos` 参数说明)。
- **旁路在 RUNNING / STOPPED 下都合法**, 且"若进旁路前在跑, 退旁路后继续跑"
  (ATE AN §2.4.5 + §20.4.6.25)。**旁路档不能靠 `STATE?` 判**, 有专用的
  `DIAG:SIMU:MODEL:STATIC?`(§20.4.6.26)—— 故每个检查点两条都问。
- **`*OPC?` 是官方推荐的同步方式**(ATE AN §1.3);它只表示"执行过了", 不表示没出错
  (§20.6.1.2)—— 所以后面必须再读 `SYST:ERR?` + 重新问一次状态。

**剧本刻意避开**手册标明"须在停止态下发"的命令(干扰源增删 `OUTP:INTERF:ADD/REM`、
移动速度 `DIAG:SIMU:MOB:MAN:CH`、RFLO `ROUT:PATH:RFLO:CH`、输入电平
`INP:LEV:AUTOSET`、触发配置 `DIAG:SIMU:TRIG:CONF`)与须在 CLOSED 态下发的
`CALC:FILT:FILE` / `SYST:MSIM:*`。**禁盲试**: 这里只发手册有依据、且生产驱动已在用的命令。

会改仪器状态, 故 `safe_during_test=False`。
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

# 刻意**复用不复制** `propsim_f64_health` 的错误码解析与 await 兼容包装 ——
# 同一条规则存两份, 改的时候必然只改一份。跨模块引私有名是有意为之(同包内,
# 单一真值源优先)。
from app.diagnostics.sequences.propsim_f64_health import _maybe_await, _parse_err
from app.services.diagnostic_context import DiagnosticContext


# 复用驱动的七态白名单(手册 §20.4.3.14 原文枚举)——同理不另抄一份。
from app.hal.propsim_f64 import _SIMULATION_STATES


metadata = SequenceMetadata(
    name="PROPSIM F64 状态机语义探测",
    description=(
        "带动作的 F64 状态机剧本: 逐步 GO / 进旁路 / 退旁路 / GOS, 每步后 "
        "*OPC? → SYST:ERR? → 重新问 DIAG:SIMU:STATE? 与 MODEL:STATIC?, "
        "并把仪器的**原始回复**逐条记下来。服务 F64R-7 的两个待验问题 "
        "(GOS 之后报什么 / 旁路下报什么)。需要仿真已加载; 会改变仪器状态。"
    ),
    required_categories=["channelEmulator"],
    params_schema=[
        {"name": "bypass_mode", "label": "旁路档 (3=校准/2=Butler/1=模型)",
         "type": "number", "default": 3},
        {"name": "probe_gos", "label": "探测 GOS (⚠ 会把仿真倒回起点)",
         "type": "boolean", "default": True},
        {"name": "restore_initial_state", "label": "结束后恢复初始运行态",
         "type": "boolean", "default": True},
    ],
    safe_during_test=False,
)


# 剧本只在这两个状态下动手: 其余(加载中/停止中/卸载中/编辑中)是瞬态或 GUI 占用态,
# 手册未定义此时下发控制命令的行为 → 不碰, 如实报出来让操作员先把仪器弄到稳态。
_ACTIONABLE_STATES = frozenset({"STOPPED", "RUNNING"})

# `MODEL:STATIC?` 的全部合法返回 (§20.4.6.25): 0 禁用 / 1 模型 / 2 Butler / 3 校准。
_BYPASS_MODES = frozenset({"0", "1", "2", "3"})


class _Abort(RuntimeError):
    """中止探测但**仍要走收尾恢复** —— 不能裸 return。

    审查 P1 实证: 现场收工稳态 STOPPED+STATIC 3 下, 剧本先成功退了旁路(衰落已放回),
    紧接着 GO 被拒就裸 `return` —— 仪器被留在 STATIC 0, 已 attach 的手机当场掉,
    而 summary 只说"GO 被拒", 一个字没提旁路档被我们改了。
    "把仪器还原成接手时的样子"必须是**所有**退出路径的共同出口。
    """


def classify_state(raw: Optional[str]) -> Tuple[Optional[str], str]:
    """把 `STATE?` 原始回复归一并按七态白名单分类。

    返回 ``(归一化状态 或 None, 说明)``。**白名单外一律 None** —— 会话错位时的
    迟到应答(如 `0,"NO ERROR"`)绝不能被当成一个"状态"记进结论, 这正是 F64R-1
    给驱动加白名单的理由, 剧本的判定必须与驱动同源, 否则两边对同一台仪器会得出
    不同结论。
    """
    if raw is None:
        return None, "无回复"
    norm = raw.strip().strip('"').upper()
    if not norm:
        return None, "空回复"
    if norm in _SIMULATION_STATES:
        return norm, ""
    return None, f"白名单外(非七态之一): {raw!r}"


class _Probe:
    """把"发命令 → *OPC? → SYST:ERR? → 再问状态"这套手册闭环收成一个入口。

    散在各步骤里内联写会漏 —— F64 这条线上"复位/校验散落多处 → 反复逃逸"已经
    踩过五轮(见 memory feedback_clear_stale_state_enumerate_all_sources)。
    """

    def __init__(self, ce: Any, log: Callable[[str], None]) -> None:
        self._ce = ce
        self._log = log
        self.steps: List[SequenceStepResult] = []

    async def _q(self, cmd: str) -> Optional[str]:
        raw = await _maybe_await(self._ce._query(cmd))  # noqa: SLF001
        return raw if isinstance(raw, str) else (None if raw is None else str(raw))

    @property
    def last_raw(self) -> Optional[str]:
        """刚记下那一步的**仪器原始回复**。

        用途: `read_state` 返回的是归一化后的状态(`RUNNING`), 而归档摘要要写的是
        仪器真吐出来的样子(`  "RunNing"  `)—— 归一化值做不了下次现场的字面比对,
        而那正是 raw 这个字段存在的理由 (Codex #229 P2)。
        `read_state`/`read_bypass` 各自只 append 一步, 所以取最后一步是确定的。
        """
        return self.steps[-1].raw if self.steps else None

    def add(
        self, label: str, success: bool, detail: str,
        raw: Optional[str], started: float,
    ) -> SequenceStepResult:
        step = SequenceStepResult(
            label=label,
            success=success,
            detail=detail,
            duration_ms=int((time.monotonic() - started) * 1000),
            raw=raw,
        )
        self.steps.append(step)
        self._log(f"  {'✓' if success else '✗'} {label}: {detail}"
                  + (f"  raw={raw!r}" if raw is not None else ""))
        return step

    async def read_state(self, label: str, *, expect: Optional[str] = None) -> Optional[str]:
        """问一次 `STATE?`, 原样记录, 返回归一化状态(白名单外 → None)。

        `expect` —— 这个参数是本剧本的**核心区分**, 传不传决定了这一步的性质:

        - **传** = 这个站点的目标**已知**(我们刚写进去的档位 / 手册承诺的转移 /
          恢复的目标态)。写完不比对就等于"错误队列干净就当成功", 而错误队列干净
          **不代表命令真生效** —— 这条线一路在删的就是这种假成功 (Codex #229 两轮
          在 GO 后、退旁路后、三个恢复写各抓了一次, 全是同一个母题的不同站点)。
        - **不传** = 这个站点的值是**待测未知量**(旁路下报什么 / GOS 之后报什么,
          即 F64R-7 的两问)。这些**绝不能**传 expect —— 拿期望值去比等于预设答案,
          本剧本存在的理由就没了。

        判据折在**同一步**里(不另记一条), 免得"写-读-比"散成三处又各自漂。
        """
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
            detail = f"期望 {expect}, 实际 {state or note} — 命令收下了但没真生效"
        self.add(label, success=ok, detail=detail, raw=raw, started=started)
        return state

    async def read_bypass(self, label: str, *, expect: Optional[str] = None) -> Optional[str]:
        """问一次 `MODEL:STATIC?` —— 旁路档的**唯一**权威来源(§20.4.6.26);
        `STATE?` 七态里没有 BYPASS, 判旁路只能问这条。

        ⚠ 回读值要过白名单再返回, 理由跟 `classify_state` 完全一样: 会话错位时的
        迟到应答(如 `0,"NO ERROR"`)会被**原样拼回**收工那条
        `DIAG:SIMU:MODEL:STATIC {initial_bypass}` —— 发出一条畸形命令。
        入参那边已经严到 `type(x) is not int`, 仪器回读值没道理免检
        (驱动侧 `propsim_f64.py` 的旁路回读也是 `isdigit()` 卡过的, 判据同源)。
        """
        started = time.monotonic()
        try:
            raw = await self._q("DIAG:SIMU:MODEL:STATIC?")
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"查询异常 {type(e).__name__}: {e}", None, started)
            return None
        norm = (raw or "").strip().strip('"')
        if norm not in _BYPASS_MODES:
            self.add(
                label, False,
                (f"白名单外(非 0/1/2/3): {raw!r}" if norm else "空回复"),
                raw, started,
            )
            return None
        # `expect` 语义同 read_state: 传了就是"这个档位是我们自己写进去的, 该核";
        # 不传就是"只记录当前档位"。
        ok = True if expect is None else norm == expect
        detail = norm if ok else f"期望 STATIC {expect}, 实际 {norm} — 命令收下了但没真生效"
        self.add(label, success=ok, detail=detail, raw=raw, started=started)
        return norm

    async def clear_error_queue(self, label: str = "*CLS + 排空错误队列") -> bool:
        """开跑前把队列清干净 —— 否则别人留下的旧错误会被算到本次头上。

        实证 (审查 agent 场景 C): 队列里有一条前面操作留下的 `-200`, 剧本第一条
        `GO` 之后读 `SYST:ERR?` 读到的是**那条旧的**, 于是把一次成功的 GO 判成失败。

        手册 (§20.4.1.1 + §20.4.2.1, 2026-07-26 NotebookLM 查证):
        - `*CLS` 只清错误/事件队列与各状态寄存器, **不碰仿真状态机**
          (`*RST` 才会关仿真) —— RUNNING 态下发也安全。
        - `SYST:ERR?` 是 FIFO **一次一条**, 读到即销毁; 要循环读到 `0,"No error"`
          才算真清空。所以 `*CLS` 之后再排一次, 两道都做。
        """
        started = time.monotonic()
        drained: List[str] = []
        try:
            # ⚠ 顺序: **先读空再 `*CLS`**, 不能反过来。`*CLS` 会把队列直接清掉,
            # 先发它就等于把"开跑前仪器上有哪些遗留错误"这条诊断信息冲掉了 ——
            # 而那恰恰是值得归档的线索 (谁在我们之前动过这台仪器、动出了什么)。
            # 读完再补一发 `*CLS` 兜底 (固件不吐 "No error" 时读循环会提前退出)。
            # 上界防呆: 手册 §20.5.4 说队列最多 100 条。
            for _ in range(100):
                raw = await self._q("SYST:ERR?")
                code, _text = _parse_err(raw or "")
                if code in (0, None):
                    break
                drained.append((raw or "").strip())
            await _maybe_await(self._ce._write("*CLS"))  # noqa: SLF001
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"清队列异常 {type(e).__name__}: {e}", None, started)
            return False
        self.add(
            label,
            success=True,
            detail=(f"清掉 {len(drained)} 条开跑前的遗留错误" if drained else "队列本来就是干净的"),
            raw="; ".join(drained) if drained else None,
            started=started,
        )
        return True

    async def write_and_check(self, label: str, cmd: str) -> bool:
        """手册闭环: 写 → `*OPC?` → `SYST:ERR?`。

        `*OPC?` 只保证"执行过了"不保证"没出错"(§20.6.1.2), 所以错误队列**必读** ——
        这正是这条线上"写假成功"母题的解药。
        """
        started = time.monotonic()
        opc_raw: Optional[str] = None
        try:
            await _maybe_await(self._ce._write(cmd))  # noqa: SLF001
            opc_raw = await self._q("*OPC?")
            err_raw = await self._q("SYST:ERR?")
        except Exception as e:  # noqa: BLE001
            self.add(label, False, f"{cmd} 异常 {type(e).__name__}: {e}",
                      opc_raw, started)
            return False
        code, text = _parse_err(err_raw or "")
        # ⚠ 只认 `code == 0`。`None` = 错误队列的回复**读不出错误码**(空串 / 超时后的
        # 迟到应答 / 畸形内容) —— 那意味着这条写命令**根本没经过错误队列确认**,
        # 当成成功就是这条线一路在删的"假成功": 会带着未确认的状态继续发 GO/STATIC/GOS。
        # (Codex #229 P1; 我原来写的是 `code in (0, None)`。)
        ok = code == 0
        self.add(
            label,
            success=ok,
            detail=(f"{cmd} → *OPC?={(opc_raw or '').strip()} "
                    f"SYST:ERR?={code if code is not None else '?'},{text or 'NO ERROR'}"),
            raw=err_raw,
            started=started,
        )
        return ok


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
        return SequenceRunResult(
            success=False, summary=driver_not_loaded_summary("channelEmulator"),
        )

    refusal = mock_driver_refusal_summary("channelEmulator", ce)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)

    if not (hasattr(ce, "_query") and hasattr(ce, "_write")):
        return SequenceRunResult(
            success=False,
            summary=(
                f"CE 驱动 {type(ce).__name__} 没有 SCPI 读写通道 (_query/_write) —— "
                "本剧本按 PROPSIM ATE 手册的 DIAG:SIMU 命令族写, 需要真实 PROPSIM 驱动。"
            ),
        )

    bypass_mode = params.get("bypass_mode", 3)
    probe_gos = bool(params.get("probe_gos", True))
    restore = bool(params.get("restore_initial_state", True))

    # 旁路档只接受手册枚举的 1/2/3 (0 是"退旁路", 由剧本自己发, 不该当探测档传进来)。
    # 必须用 `type(...) is not int` 而不是 `not in (1,2,3)`:
    #   - bool: Python 里 True == 1, JSON 的 true 会被静默当成"模型旁路"
    #     (开关 2 在 #216 踩过同一个坑);
    #   - float: `3.0 in (1,2,3)` 也为真 (审查 agent 实测), 而 f-string 会把它
    #     拼成 `DIAG:SIMU:MODEL:STATIC 3.0` —— 一条畸形命令发给真机。
    #   JSON 的数字没有整型/浮点之分, 前端传 3 还是 3.0 全看序列化, 所以这里
    #   不能只靠"值对不对", 得连**类型**一起卡死。
    if type(bypass_mode) is not int or bypass_mode not in (1, 2, 3):
        return SequenceRunResult(
            success=False,
            summary=(
                f"bypass_mode={bypass_mode!r} 非法 —— 只接受 1 (模型旁路) / "
                "2 (Butler) / 3 (校准旁路)。0 是退旁路, 剧本会自己发。"
            ),
        )

    p = _Probe(ce, log)
    findings: Dict[str, Any] = {}

    log("  · 读初始状态 ...")
    initial_state = await p.read_state("初始 STATE?")
    initial_bypass = await p.read_bypass("初始 MODEL:STATIC?")
    findings["initial_state"] = initial_state
    findings["initial_bypass"] = initial_bypass

    if initial_state is None:
        return SequenceRunResult(
            success=False,
            summary=("初始 DIAG:SIMU:STATE? 读不到合法七态之一 —— 先确认 SCPI 通道正常 "
                     "(跑 F64 健康探针), 不在状态未知时下发控制命令。"),
            steps=p.steps, extra=findings,
        )
    if initial_bypass is None:
        # 审查 P2: 旁路档读不到跟状态读不到**同等严重**, 待遇必须一样。
        # 放行的话: 仪器实际在 STATIC 3 却被当成 0 → 不退旁路就 GO(灰色地带),
        # 且收工时恢复闸同样为假 → 把人家的 STATIC 3 改成 0 还不还原。
        return SequenceRunResult(
            success=False,
            summary=("初始 DIAG:SIMU:MODEL:STATIC? 读不到合法档位 (0/1/2/3) —— "
                     "旁路档未知就动手, 收工时也没法还原成接手的样子。先确认 SCPI 通道正常。"),
            steps=p.steps, extra=findings,
        )
    if initial_state == "CLOSED":
        return SequenceRunResult(
            success=False,
            summary=("F64 当前 CLOSED = 未加载仿真。本剧本要验的是**已加载**仿真的状态迁移; "
                     "CLOSED 下发 GO 只会拿到 -200 wrong device state。先加载一个 .smu 再跑。"),
            steps=p.steps, extra=findings,
        )
    if initial_state not in _ACTIONABLE_STATES:
        return SequenceRunResult(
            success=False,
            summary=(f"F64 当前 {initial_state} 是瞬态/占用态 (加载中·停止中·卸载中·编辑中) —— "
                     "手册未定义此时下发控制命令的行为, 剧本不碰。等它稳定到 "
                     "STOPPED/RUNNING 再跑。"),
            steps=p.steps, extra=findings,
        )

    aborted_reason: Optional[str] = None
    try:
        # ── ⓪ 清队列。别人留下的旧错误会被算到本次头上 (审查实测: 一条 stale -200
        #     让一次成功的 GO 被判失败)。手册确认 *CLS 不碰仿真状态机。
        # 返回值必须消费: 清队列失败(排空查询抛异常 / *CLS 抛异常)却继续往下发
        # GO/STATIC, 等于带着一个没清干净的队列跑, 后面每一步的 SYST:ERR? 判据都
        # 可能读到别人的旧错误 —— 正是本剧本开头加清队列要治的那个病 (Codex #229)。
        if not await p.clear_error_queue():
            raise _Abort("开跑前清错误队列失败 — 带着未清的队列往下跑, 后续判据都不可信")

        # ── ① 若开跑时就在旁路里, 先退出来。
        #     现场收工稳态恰恰是「STOPPED + STATIC 3」—— 下次开机第一件事就是在这个
        #     状态下跑本剧本, 所以这条不是边角料, 是**主路径**。
        #     手册 (2026-07-26 查证): 旁路态下发 GO 是**灰色地带** (进旁路时"仿真被
        #     暂停", 手册没定义此时 GO 的行为, 有 -200 风险); 而退旁路只在"进旁路前
        #     在跑"时才自动恢复播放 —— 初始是 STOPPED 就不会自动跑, 所以退旁路之后
        #     再显式 GO 既合法又必需, **不会变成 GO 两次**。
        if initial_bypass != "0":
            if not await p.write_and_check(
                f"先退旁路 (开跑时是 STATIC {initial_bypass})", "DIAG:SIMU:MODEL:STATIC 0",
            ):
                raise _Abort(f"退旁路失败 — 开跑时在 STATIC {initial_bypass}, 见步骤里的 SYST:ERR? 原文")
            # 退旁路本身可能触发状态迁移 (手册: 进旁路前在跑 → 退旁路后继续跑), 重读一次
            # 当基准。⚠ **必须再过一次同一道闸** —— 入口闸只守了第一次读, 这里可能读到
            # STOPPING/OPENING 之类的过渡态, 甚至有人在这期间把仿真卸了 (审查 P2)。
            rebased = await p.read_state("退旁路后 STATE? (作为后续基准)")
            if rebased is None or rebased not in _ACTIONABLE_STATES:
                raise _Abort(
                    f"退旁路后状态变成 {rebased or '读不到'} —— 不是 STOPPED/RUNNING, "
                    "手册未定义此时下发控制命令的行为, 剧本不碰。"
                )
            initial_state = rebased

        # ── ② 保证进入 RUNNING(旁路与 GOS 两项都要在"在跑"时才验得出东西)
        state = initial_state
        if state == "STOPPED":
            if not await p.write_and_check("GO (STOPPED → 期望 RUNNING)", "DIAG:SIMU:GO"):
                raise _Abort("GO 被拒或报错 — 见步骤里的 SYST:ERR? 原文")
            state = await p.read_state("GO 之后 STATE?")
            findings["state_after_go"] = state
            # 错误队列干净 ≠ 真起来了。不校验就往下走的话, 后面记的"旁路下 STATE?"
            # 和"GOS 之后 STATE?"根本不是**运行态下**的语义, 结论作废还不自知;
            # 而且可能继续往不允许的状态里发控制命令。(Codex #229 P2)
            if state != "RUNNING":
                raise _Abort(f"GO 之后状态是 {state or '读不到'} 而不是 RUNNING — "
                             "后续旁路/GOS 结论都不会是运行态语义, 不继续。")
        else:
            # 手册 §20.5.2 + 现场实证: RUNNING 态再发 GO 会 -200 并累积。
            # 文案要打印**真实 state** —— 上面的闸已经保证只可能是 RUNNING, 但硬编码
            # "已是 RUNNING" 会在闸失效时变成谎报 (审查 P2 抓到过一次)。
            p.add("GO (跳过)", True, f"已是 {state} — 按手册不重复发 GO", None,
                   time.monotonic())

        # ── ② 旁路探测 (F64R-7②)。放在 GOS 之前: 它是非破坏性的(退旁路自动恢复),
        #     万一现场中途要停, 至少这个答案已经拿到。
        if not getattr(ce, "SUPPORTS_STATIC_PASSTHROUGH", False):
            p.add("旁路探测 (跳过)", True,
                   f"驱动 {type(ce).__name__} 无 STATIC 直通能力标志", None, time.monotonic())
        else:
            if await p.write_and_check(
                f"进旁路 MODEL:STATIC {bypass_mode}",
                f"DIAG:SIMU:MODEL:STATIC {bypass_mode}",
            ):
                # ⭐ F64R-7② 的答案就是这两条的 raw
                findings["state_in_bypass"] = await p.read_state("旁路下 STATE?  ⭐F64R-7②")
                findings["state_in_bypass_raw"] = p.last_raw
                findings["bypass_in_bypass"] = await p.read_bypass(
                    "旁路下 MODEL:STATIC?", expect=str(bypass_mode))

            if await p.write_and_check("退旁路 MODEL:STATIC 0", "DIAG:SIMU:MODEL:STATIC 0"):
                # 手册承诺"进旁路前在跑 → 退旁路后继续跑"; 这里验它在本固件上成不成立。
                # 手册承诺"进旁路前在跑 → 退旁路后继续跑"(ATE AN §2.4.5), 这是**已知
                # 目标**不是待测量 → 该核。核不上就不能继续发 GOS: 后面那条 GOS 观测
                # 的前提是"从 RUNNING 出发", 前提不成立结论就作废, 而且可能在过渡态
                # 里继续发控制命令 (Codex #229 第二轮 P1)。
                findings["state_after_bypass_exit"] = await p.read_state(
                    "退旁路后 STATE? (手册承诺应恢复 RUNNING)", expect="RUNNING")
                findings["bypass_after_exit"] = await p.read_bypass(
                    "退旁路后 MODEL:STATIC?", expect="0")
                if findings["state_after_bypass_exit"] != "RUNNING":
                    raise _Abort(
                        f"退旁路后状态是 {findings['state_after_bypass_exit'] or '读不到'} "
                        "而不是手册承诺的 RUNNING — GOS 观测的前提不成立, 不继续。")

        # ── ③ GOS 探测 (F64R-7①) —— 最关键, 也是唯一破坏性的一步, 放最后。
        if probe_gos:
            log("  · GOS 探测 (⚠ 按手册 §20.4.3.11 会倒回仿真起点) ...")
            if await p.write_and_check("GOS (期望停住)", "DIAG:SIMU:GOS"):
                findings["state_after_gos"] = await p.read_state("GOS 之后 STATE?  ⭐F64R-7①")
                findings["state_after_gos_raw"] = p.last_raw
        else:
            p.add("GOS 探测 (跳过)", True, "probe_gos=false", None, time.monotonic())
    except _Abort as e:
        aborted_reason = str(e)
    except Exception as e:  # noqa: BLE001
        aborted_reason = f"剧本中断: {type(e).__name__}: {e}"

    # ⚠ 恢复段在 try **之外** —— 上面任何一步失败都必须走到这里。
    # 审查 P1: 之前中途是裸 return, 于是"先退旁路成功、紧接着 GO 被拒"这条现场
    # 最常见的路径会把仪器留在 STATIC 0(衰落放回来, 已 attach 的手机当场掉),
    # summary 却只字不提旁路档被我们改过。
    try:
        # ── ④ 恢复。**顺序按手册来: 先运行态, 再旁路档** ——
        #     设 STATIC≠0 本身就会把仿真暂停 (§20.4.6.25), 反过来做会让底层状态机
        #     跟物理状态打架 (2026-07-26 NotebookLM 明确纠正过我原来的顺序)。
        #     ⚠ 只恢复"在不在跑"与"旁路档", **恢复不了播放位置** —— GOS 已经倒回起点,
        #     这是 GOS 的语义不是 bug。要保住位置的场景该用 DIAG:SIMU:STOP(暂停)。
        if restore:
            # 恢复的目标是一对值 (initial_state, initial_bypass)。
            # ⚠ **对着目标收敛, 不假设主流程做过什么** —— 前两版都栽在"假设"上:
            #   · 初版假设 GO 一定成功 → 中途失败裸 return, 旁路没还原;
            #   · 二版假设"主流程已经退过旁路" → 只在 initial_bypass≠0 时恢复,
            #     于是"初始就是 0、进了探测旁路、退旁路那步失败"时, 仪器被留在
            #     1/2/3 档没人管 (Codex #229 P1)。
            # 现在改成: 读当前实际值 → 跟目标比 → 不同才写。两个维度都这样。
            now = await p.read_state("恢复前 STATE?")
            if now is None or now not in _ACTIONABLE_STATES:
                # 状态不稳(读不到 / 瞬态)→ **两样都不动**。
                # 旁路档也不能动: `MODEL:STATIC` 按本剧本采用的手册约束只在
                # RUNNING/STOPPED 下才有定义, 在 STOPPING/OPENING 里继续改仪器,
                # 等于在"状态未知就不动手"这条自家纪律上开后门 (Codex #229 P1)。
                # 代价是仪器可能留在跟接手时不同的态 —— 所以要**大声说清楚**
                # 当前是什么、接手时是什么, 让人能手动收拾。
                cur_bypass = await p.read_bypass("恢复前 MODEL:STATIC? (仅记录)")
                p.add(
                    "恢复 (放弃)", False,
                    (f"当前状态 {now or '读不到'} 不稳, 不硬闯。"
                     f"⚠ 接手时是 运行态={initial_state} / 旁路档={initial_bypass}, "
                     f"现在是 运行态={now or '?'} / 旁路档={cur_bypass or '?'} —— 请人工核对复位"),
                    None, time.monotonic(),
                )
            else:
                # ④-1 运行态 (必须排在旁路档**之前**: 设 STATIC≠0 本身会暂停仿真,
                #      §20.4.6.25, 顺序反了会让底层状态机跟物理状态打架)
                if now == initial_state:
                    p.add("恢复运行态 (无需)", True, f"已是 {now}", None, time.monotonic())
                elif initial_state == "RUNNING" and now == "STOPPED":
                    if await p.write_and_check("恢复 GO (初始是 RUNNING)", "DIAG:SIMU:GO"):
                        findings["state_after_restore"] = await p.read_state(
                            "恢复后 STATE?", expect="RUNNING")
                elif initial_state == "STOPPED" and now == "RUNNING":
                    # 用 STOP 不是 GOS: STOP 是暂停不倒回 (§20.4.3.10), 是"最小改动"
                    # 的复位; 剧本自己不该再多倒一次带。
                    if await p.write_and_check("恢复 STOP (初始是 STOPPED)", "DIAG:SIMU:STOP"):
                        findings["state_after_restore"] = await p.read_state(
                            "恢复后 STATE?", expect="STOPPED")
                else:
                    p.add("恢复运行态 (放弃)", False,
                          f"初始 {initial_state} → 当前 {now}, 不是已知可恢复的转移; 请人工处理",
                          None, time.monotonic())
                # ④-2 旁路档 —— 读当前实际档位跟目标比, **含目标就是 "0" 的情况**
                cur_bypass = await p.read_bypass("恢复前 MODEL:STATIC?")
                if cur_bypass == initial_bypass:
                    p.add("恢复旁路档 (无需)", True, f"已是 STATIC {cur_bypass}",
                          None, time.monotonic())
                elif cur_bypass is None:
                    p.add("恢复旁路档 (放弃)", False,
                          f"当前旁路档读不到 — 不猜; 接手时是 STATIC {initial_bypass}, 请人工核对",
                          None, time.monotonic())
                elif await p.write_and_check(
                    f"恢复旁路档 STATIC {cur_bypass}→{initial_bypass}",
                    f"DIAG:SIMU:MODEL:STATIC {initial_bypass}",
                ):
                    findings["bypass_after_restore"] = await p.read_bypass(
                        "恢复后 MODEL:STATIC?", expect=initial_bypass)

        ok = all(s.success for s in p.steps) and aborted_reason is None
        # ⚠ 关键字面值写进 summary —— 归档 (`DiagnosticRun.output_excerpt`) 在 2048
        # 字节处**掐头留尾式截断** (保头部), 一轮完整探测已经 ~1959 字节, 再多几步
        # 尾巴上的 F64R-7 答案就会被切掉。summary 永远排在最前, 放这里才切不掉 ——
        # 而"下次现场拿归档跟这次对照"正是 raw 这个字段存在的理由。
        # ⚠ 摘要写**原始回复**不写归一化值 —— `findings["state_after_gos"]` 是
        # `classify_state` 归一后的 `RUNNING`, 而仪器真吐的可能是 `  "RunNing"  `。
        # 下次现场要做的是**字面比对**, 归一化值做不了这件事; 而完整步骤排在摘要与
        # 日志之后, 超 2048 字节就被截掉, 于是归档里只剩归一化结果 (Codex #229 P2)。
        # 用 repr 保住空白与引号, 跟归档那边同一套形状。
        answers = []
        if findings.get("state_after_gos"):
            answers.append(f"GOS后={findings.get('state_after_gos_raw')!r}")
        if findings.get("state_in_bypass"):
            answers.append(f"旁路下={findings.get('state_in_bypass_raw')!r}")
        # 中止原因排在最前 —— 归档保头部, 操作员先看到"为什么没跑完"。
        head = f"⚠ {aborted_reason} | " if aborted_reason else ""
        return SequenceRunResult(
            success=ok,
            summary=(
                head + f"F64 状态机探测 ({len(p.steps)} 步): "
                + ("⭐F64R-7 " + ", ".join(answers) if answers
                   else "关键问题未取得答案, 见失败步骤")
            ),
            steps=p.steps,
            extra=findings,
        )
    except Exception as e:  # noqa: BLE001
        # 连恢复段都炸了 —— 这才是真的"仪器停在中间态"。
        return SequenceRunResult(
            success=False,
            summary=(f"恢复阶段中断: {type(e).__name__}: {e} — 仪器可能停在中间态"
                     + (f" (先前已中止: {aborted_reason})" if aborted_reason else "")
                     + ", 请人工确认旁路档与运行态"),
            steps=p.steps,
            extra=findings,
        )
