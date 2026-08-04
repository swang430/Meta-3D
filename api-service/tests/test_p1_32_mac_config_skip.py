"""P1-32 门 —— `configure_mac_throughput_test()` 缺命令时的处置。

守的三件事：
  · 方言没定义的命令**graceful-skip，不抛** —— 上一版第一条 `.format()` 就崩；
  · **半生效不许报 applied**（本仓库 `set_cell_config` 的既有禁令）；
  · 调用方**必须消费** —— 光返回不够，不消费只是换个姿势继续在
    没配置过的链路上跑测试（Codex #276 P1）。
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.hal.uxm_base_station import (
    MacThroughputConfigResult,
    RealUxmDriver,
)
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)
from tests.test_uxm_kpi_readback import _stub_io


def _strip_comments(src: str) -> str:
    """去掉 `#` 注释后再做文本判断。

    ⚠ 不去注释的文本门会被**注释里的同一个词**喂绿 —— 变异 M9 实证。
    """
    import io as _io
    import tokenize

    out = []
    for tok in tokenize.generate_tokens(_io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        out.append(tok)
    return tokenize.untokenize(out)


def _drv(profile):
    d = RealUxmDriver("uxm-1", {"resource": "TCPIP0::x::inst0::INSTR"})
    d._cmds = profile
    d._connected = True
    return d


def _all_defined():
    """全定义那一侧 —— P1-33 之后**就是 IRAT 本身**（手册形式已补齐）。"""
    return UxmLteNrIratProfile


def _none_defined():
    """全缺那一侧 —— 合成 profile，把必要项全抹掉。

    ⚠ P1-33 前这里用的是真 profile（IRAT=全缺 / 5G=全有）。现在两者都变了：
      IRAT 补齐了手册形式，5G 那 11 条**本来就是编的**（手册 0 命中）已置 None。
      拿生产 profile 当"形态夹具"本来就不稳 —— 改用合成的。
    """
    return type("_NoneDefined", (UxmLteNrIratProfile,),
                {n: None for n in (RealUxmDriver.MAC_CFG_MANDATORY
                                   + RealUxmDriver.MAC_CFG_OPTIONAL)})


def _run(profile, responses=None, **kw):
    d = _drv(profile)
    # `"ALL"` 会去问本 BWP 的 PRB 数（不敲 38.104 表）—— 桩上，
    # 否则走进"读不到就不猜"的分支，测的就不是本门要测的东西了。
    resp = {"*OPC?": "1", "NUM:PRBS": "273", "SYSTem:ERRor": '0,"No error"',
            "SYST:ERR": '0,"No error"'}
    resp.update(responses or {})
    writes = _stub_io(d, resp)
    res = asyncio.run(d.configure_mac_throughput_test(**kw))
    return res, writes


# ── 门① 分级本身 ────────────────────────────────────────────────

class TestGrading:
    def test_grading_covers_exactly_the_commands_the_function_emits(self):
        """⭐ **不变量门** —— 分级清单必须**恰好等于**函数真会发的那批命令。

        少一条 → 新命令没人归类，缺了也不报警；多一条 → 判据引用了根本不发的
        命令，`missing_mandatory` 永远差一格。这两种都不是靠人眼能稳定发现的。

        真值取自 5G_NR 方言（11 条全定义）下 **实际发出去** 的命令名。
        """
        res, _ = _run(_all_defined(), mimo_layers=2)
        emitted = set(res.applied) | set(res.skipped)
        graded = set(RealUxmDriver.MAC_CFG_MANDATORY) | set(
            RealUxmDriver.MAC_CFG_OPTIONAL)
        assert emitted == graded, (
            f"分级清单与函数实发命令不符：只在实发里={emitted - graded}，"
            f"只在分级里={graded - emitted}")

    def test_mandatory_set_is_pinned_to_literals(self):
        """⭐ 内审 F4 —— 现有两条门都拦不住「把必要项偷偷降级成可选」：
        并集相等门（降级不改并集）、以及 `test_reports_all_eight_mandatory_missing`
        **拿常量自己当自己的真值**（自指，恒绿）。实证：把 `CSIRS_PORTS` 挪进
        OPTIONAL，54 passed 全绿。

        所以这里**写死字面量**对账。要改分级，必须同时改这行 —— 那是个
        需要论证的动作，不能顺手滑过去。
        """
        assert set(RealUxmDriver.MAC_CFG_MANDATORY) == {
            "PDSCH_SCHED_ALGO",     # Full Buffer 没开 → 测的是打流能力
            "PDSCH_AMC_ENABLE",     # AMC 没关 → 测的是调度器
            "PUSCH_AMC_ENABLE",
            "PDSCH_MCS",            # 与 AMC=OFF 共同定义工作点
            "PDSCH_RB_ALLOC",       # RB 不满 → 吞吐随分配缩放
            # TDD：手册没有 pattern 字符串命令，是**六个数**（P1-33）
            "TDD_PATTERN_STATE", "TDD_PERIOD",
            "TDD_DL_SLOTS", "TDD_DL_SYMBOLS", "TDD_UL_SLOTS", "TDD_UL_SYMBOLS",
            "CSIRS_PORTS",          # 端口不匹配 → 跑不到目标层数
            # 两条 apply 是**两件事**（内审 F2）：Quick Config 有自己的 apply，
            # 通用 APPLY 管的是把小区缓存配置推进协议栈。
            "QCONFIG_APPLY_ALL", "CONFIG_APPLY",
        }
        assert set(RealUxmDriver.MAC_CFG_OPTIONAL) == {
            "HARQ_MAX_TRANS", "HARQ_PROCESSES",
        }
        # ⛔ 手册里没有对应命令的，单列一档 —— 既不是 profile 缺项也不是被拒
        assert set(RealUxmDriver.MAC_CFG_NO_EQUIVALENT) == {"MEAS_TPUT_STAT_COUNT"}

    def test_mandatory_and_optional_do_not_overlap(self):
        assert not (set(RealUxmDriver.MAC_CFG_MANDATORY)
                    & set(RealUxmDriver.MAC_CFG_OPTIONAL))


# ── 门② IRAT：11/11 缺失 ────────────────────────────────────────

class TestIratAllMissing:
    """现场用的就是这个方言 —— 11 条命令**一条都没有**。"""

    def test_does_not_raise(self):
        """⭐ 上一版在第一条 `.format()` 上抛 AttributeError，
        被整段 `except` 吞成 `return False`。变异：改回 `self._cmds.X.format`
        → 红。"""
        res, _ = _run(_none_defined(), mimo_layers=2)
        assert isinstance(res, MacThroughputConfigResult)
        assert res.error is None, f"不该有异常，实际: {res.error}"

    def test_reports_all_eight_mandatory_missing(self):
        res, _ = _run(_none_defined(), mimo_layers=2)
        assert set(res.missing_mandatory) == set(RealUxmDriver.MAC_CFG_MANDATORY)
        assert len(res.skipped) >= len(RealUxmDriver.MAC_CFG_MANDATORY)
        assert res.ok is False and bool(res) is False

    def test_applied_is_empty_not_optimistic(self):
        """⭐ 「半生效配置不许报 applied」—— 一条都没发就不能列进 applied。"""
        res, _ = _run(_none_defined(), mimo_layers=2)
        assert res.applied == ()

    def test_kpi_prereqs_still_sent_first(self):
        """⭐ 生效端 —— 11 条全跳过，**KPI 前置仍必须发出去**（#275，第 0 步）。
        变异：把 `_enable_kpi_measurements` 挪到 8 组之后 → 本条仍绿，
        但 `test_uxm_kpi_readback.py` 的 M10b 会红；两边合起来才锁死顺序。"""
        _, writes = _run(_none_defined(), mimo_layers=2)
        joined = " | ".join(writes)
        assert "BTHRoughput:STATe ON" in joined
        assert "CSI:STARt" in joined
        assert "MEASurement:REPort ON" in joined

    def test_no_mac_config_command_is_sent(self):
        """跳过就是**真的没发**，不是发了个残缺串。"""
        _, writes = _run(_none_defined(), mimo_layers=2)
        for frag in ("FULLBUFFER", "PDSCh:MCS", "TDD", "HARQ", "CSIRs"):
            assert not any(frag in w and "MEASure" not in w for w in writes), (
                f"跳过的命令仍被发出: {frag}")


# ── 门③ 5G_NR：全定义 ──────────────────────────────────────────

class Test5gAllPresent:
    def test_log_does_not_claim_the_config_took_effect(self, caplog):
        """⭐ 内审 F7 —— 「写出去了」≠「生效了」。

        手册：小区 ON 时多数配置改动要发 `BSE:CONFig:<celltype>:APPLY` 才进
        协议栈；本函数**不发 APPLY**，而调用链上游 `set_cell_config` 收尾会把
        小区恢复 ON。所以日志只能说"已发出"，说 "configured" 就是替仪器宣布生效。
        补 APPLY 是 P1-33 的显式前置。
        """
        import logging

        # ⚠ 必须复位 `.disabled` 并保证 propagate —— 别的用例里 in-process
        #   alembic 的 `fileConfig(disable_existing_loggers=True)` 会**永久禁用**
        #   已导入的 logger，本条在单文件下绿、跑全量才红（memory:
        #   feedback_test_logger_emit_alembic_pollution）。
        drv_logger = logging.getLogger("app.hal.uxm_base_station")
        drv_logger.disabled = False
        drv_logger.propagate = True

        with caplog.at_level(logging.INFO, logger="app.hal.uxm_base_station"):
            _run(_all_defined(), mimo_layers=2)
        msgs = " | ".join(r.getMessage() for r in caplog.records)
        assert "commands sent" in msgs, "没说清只是「已发出」"
        assert "test configured" not in msgs, (
            "日志宣称「configured」—— 没发 APPLY 就说生效，是替仪器宣布")

    def test_all_eleven_applied_and_ok(self):
        res, _ = _run(_all_defined(), mimo_layers=2)
        assert res.missing_mandatory == ()
        assert res.skipped == ()
        assert len(res.applied) == 16   # 14 必要 + 2 可选（TDD 六条 + 两条 apply）
        assert res.ok is True and bool(res) is True

    def test_commands_actually_reach_the_wire(self):
        """⭐ 生效端门 —— 断言**真发出去了**，不是只看返回值好看。"""
        _, writes = _run(_all_defined(), mimo_layers=2, mcs=28,
                         enable_amc=False)
        # ⚠ 断言钉在**整串**上 —— `"28" in joined` 会被 `128`/`280` 喂绿，
        #   `" OFF" in joined` 任何带 OFF 的命令都算数（内审 F10）。
        #   同文件上面刚骂过 `"STOP" in detail` 那个形态，这里自己又犯了。
        # ⚠ P1-33：值形态**全变了**（逐条手册核实过）
        P = _all_defined()
        c = {"cell": "CELL0", "bwp": "BWP0"}
        assert f"{P.PDSCH_SCHED_ALGO} FULL_TPUT" in writes, (
            "Full Buffer 没发 —— 手册枚举是 FULL_TPUT，不是 FULLBUFFER")
        assert f"{P.PDSCH_AMC_ENABLE.format(**c)} FIXed" in writes, (
            "关 AMC 要发资源分配策略 FIXed —— 它**不是**开关命令")
        assert f"{P.PUSCH_AMC_ENABLE.format(**c)} ON" in writes, (
            "UL 固定 MCS 开关语义反过来：ON = 固定 MCS = 关 AMC（手册原文）")
        assert f"{P.PDSCH_MCS} 28" in writes, "固定 MCS 没发"
        assert f"{P.PDSCH_RB_ALLOC} 273" in writes, '"ALL" 没换算成 PRB 整数'
        assert f"{P.TDD_PERIOD.format(cell='CELL0')} MS5" in writes, '"5MS"→MS5 没转'
        assert f"{P.TDD_DL_SLOTS.format(cell='CELL0')} 3" in writes, "DDDSU 的 3 个 D"
        assert f"{P.TDD_UL_SLOTS.format(cell='CELL0')} 1" in writes, "DDDSU 的 1 个 U"
        assert f"{P.TDD_DL_SYMBOLS.format(cell='CELL0')} 6" in writes, "S 槽 DL 符号数"
        assert f"{P.HARQ_MAX_TRANS.format(cell='CELL0')} N4" in writes, "4→N4 没转"
        assert f"{P.HARQ_PROCESSES.format(cell='CELL0')} N16" in writes, "16→N16 没转"
        assert f"{P.CSIRS_PORTS.format(cell='CELL0')} P4" in writes, "4→P4 没转"
        assert P.QCONFIG_APPLY_ALL in " | ".join(writes), (
            "没发 Quick Config 自己的 apply —— 场景/MCS/PRB 只是暂存值")
        assert P.CONFIG_APPLY in " | ".join(writes), (
            "没发通用 APPLY —— 小区缓存配置不进协议栈")


# ── 门④ 部分缺失：必要 vs 可选要分开 ──────────────────────────

class TestPartialProfiles:
    def test_missing_optional_only_still_ok(self):
        """可选命令缺席**不该**让整件事失败 —— 它只影响精度，不改量纲。"""
        class _NoHarq(_all_defined()):
            HARQ_MAX_TRANS = None
            HARQ_PROCESSES = None

        res, _ = _run(_NoHarq, mimo_layers=2)
        assert res.missing_mandatory == ()
        assert set(res.skipped) == {"HARQ_MAX_TRANS", "HARQ_PROCESSES"}
        assert res.ok is True, "只缺可选命令却判失败 —— 会白白挡住能跑的测试"

    def test_missing_one_mandatory_is_enough_to_fail(self):
        """⭐ 缺**一条**必要就够了 —— 不需要 11 条全缺。
        变异：把判据写成「全缺才算失败」→ 红。"""
        class _NoAmc(_all_defined()):
            PDSCH_AMC_ENABLE = None

        res, _ = _run(_NoAmc, mimo_layers=2)
        assert res.missing_mandatory == ("PDSCH_AMC_ENABLE",)
        assert res.ok is False
        assert len(res.applied) == 15, "其余 15 条仍该照发（graceful-skip 不是全停）"


class TestEmptyTemplateIsNotTreatedAsDefined:
    """⭐ 内审 F8 —— profile 写成空串时 `"".format()` 返回 `""`，
    会把 ` DDDSU` 这种**残缺串**真发出去、还报 ok。
    本片把 11 条新接进 `_cmd`，这条缝的爆炸半径是被本片扩大的。"""

    def test_blank_template_counts_as_missing_not_sent(self):
        class _Blank(_all_defined()):
            TDD_DL_SLOTS = ""
            CSIRS_PORTS = ""

        res, writes = _run(_Blank, mimo_layers=2)
        assert "TDD_DL_SLOTS" in res.missing_mandatory
        assert "CSIRS_PORTS" in res.missing_mandatory
        assert res.ok is False
        for w in writes:
            assert w.strip() not in ("3", "P4"), f"发出了残缺串: {w!r}"


class TestExceptionPathDoesNotLie:
    """⭐ 写命令中途抛异常时，**不许谎报成功**。

    本文件既有禁令：布尔契约 `return False`、**不能向 HAL caller 裸抛** ——
    所以异常要吞，但吞了就更不能说"配好了"。变异 M7（异常路径 `error=None`）
    在补这条门之前**全绿**。
    """

    def test_mid_way_write_failure_is_reported_not_swallowed(self):
        d = _drv(_all_defined())
        sent: list[str] = []

        def _boom(cmd, **kw):
            sent.append(cmd)
            if "IMCS" in cmd or "MCS" in cmd:      # 第 3 组就炸
                raise OSError("write boom")

        d._do_write = _boom
        d._do_query = lambda cmd, **kw: "1"
        res = asyncio.run(d.configure_mac_throughput_test(mimo_layers=2))

        assert res.error is not None, "异常被吞了还不留痕 —— 记录在说假话"
        assert "OSError" in res.error
        assert res.ok is False and bool(res) is False
        # ⭐ 半生效不许报 applied：炸之前发出去的照实记，炸之后的**不算**
        assert "PDSCH_SCHED_ALGO" in res.applied
        assert "MEAS_TPUT_STAT_COUNT" not in res.applied
        # ⭐ Codex #279 P2：**没轮到发 ≠ profile 没定义**。
        #    上一版这里写 `n not in applied`，于是 VISA 断线会把"还没轮到发"的
        #    命令算成 profile 缺项，调用方据此让操作员去补 profile，
        #    而真凶是传输错误。异常路径与正常路径**同源**（都从 skipped 派生）。
        assert res.missing_mandatory == (), (
            "把「未及下发」冒充成「profile 未定义」—— 会把排障指向错方向")
        # 拦得住靠的是 `error` 让 ok=False，不靠伪造 missing_mandatory
        assert res.ok is False


# ── 门⑤ 调用方必须消费（本片的另一半）────────────────────────

class TestCallerConsumesTheResult:
    """⭐ Codex #276 P1：光让驱动返回不够 —— 不消费只是换个姿势
    **继续在没配置过的链路上跑测试**。"""

    @pytest.mark.parametrize("cfg,blocked,why", [
        (MacThroughputConfigResult(applied=("A",) * 11), False, "全配好"),
        (MacThroughputConfigResult(missing_mandatory=("PDSCH_MCS",)), True,
         "缺必要命令"),
        (MacThroughputConfigResult(applied=("A",) * 11,
                                   error="TimeoutError: VI_ERROR_TMO"), True,
         "⭐ 11 条全写完但 *OPC? 超时 —— 上一版这一格**放行**（内审 F2）"),
        (MacThroughputConfigResult(skipped=("HARQ_MAX_TRANS",)), False,
         "只缺可选"),
        (False, True, "旧布尔契约 False"),
        (True, False, "旧布尔契约 True"),
        (None, True, "驱动啥都没做"),
    ], ids=["ok", "missing", "opc-timeout", "optional-only",
            "legacy-false", "legacy-true", "none"])
    def test_blocker_decides_correctly_for_every_shape(self, cfg, blocked, why):
        """⭐ **行为门** —— 判定本身的真值表。

        上一版这里只有源码文本/AST 门，把 `or` 改成 `and` 在 138 个用例下
        **全绿**（内审 F3 实证）。判定收窄成 `_mac_config_blocker` 后才打得了门。
        """
        from app.services.mimo_ota.executors.measure import MeasureExecutor

        got = MeasureExecutor._mac_config_blocker(cfg)
        assert (got is not None) is blocked, why
        if blocked:
            assert "不能继续测" in got

    def test_call_site_consults_the_blocker_and_returns_on_it(self):
        """⭐ 用 **AST 结构**证明调用点真的「问了判定 → 并据此返回」。

        ⚠ 前两版都被绕过：
          · v1「往后 2000 字符搜 `missing_mandatory`」→ 被**注释**喂绿（M9）；
          · v2 改扫 AST 但只查"文件里有没有这个词" → 判定抽成方法后，
            改调用点根本碰不到它，M9/M10 照样全绿。
        所以这版查的是**结构**：`_mac_config_blocker` 的返回值有没有被一个
        `if` 消费、且那个 `if` 体里有 `return`。
        """
        import ast
        import inspect

        from app.services.mimo_ota.executors import measure

        tree = ast.parse(inspect.getsource(measure))
        # ① 找到 `X = self._mac_config_blocker(...)` 里的 X
        var = None
        for n in ast.walk(tree):
            if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                    and isinstance(n.value.func, ast.Attribute)
                    and n.value.func.attr == "_mac_config_blocker"
                    and isinstance(n.targets[0], ast.Name)):
                var = n.targets[0].id
        assert var, (
            "调用点没有调用 `_mac_config_blocker` —— 配置结果又被丢掉了")
        # ② 那个变量必须被一个 if 消费，且 if 体里有 return
        ok = False
        for n in ast.walk(tree):
            if not isinstance(n, ast.If):
                continue
            names = {x.id for x in ast.walk(n.test) if isinstance(x, ast.Name)}
            if var in names and any(isinstance(b, ast.Return)
                                    for b in ast.walk(ast.Module(body=n.body,
                                                                 type_ignores=[]))):
                ok = True
        assert ok, (
            f"`{var}` 没有守住一个 return —— 报了失败仍会继续 start_signaling")

    def test_transport_error_is_reported_before_blaming_the_profile(self):
        """⭐ Codex #279 P2 —— 传输层炸了却报「profile 未定义」，
        会把操作员指向 P1-33 补命令，而真正要修的是 VISA 连接。

        两者可以同时成立（既有 profile 缺项、又炸了），所以两段都要说，
        但**先说真凶**。变异：把 `if err:` 那段删掉 → 红。
        """
        from app.services.mimo_ota.executors.measure import MeasureExecutor

        # ① 只有传输错误、profile 不缺
        only_err = MacThroughputConfigResult(
            applied=("PDSCH_SCHED_ALGO",), error="VisaIOError: VI_ERROR_CONN_LOST")
        msg = MeasureExecutor._mac_config_blocker(only_err)
        assert "下发过程中出错" in msg and "VI_ERROR_CONN_LOST" in msg
        assert "profile 未定义" not in msg, "没缺 profile 却怪 profile"
        assert "先排查仪器连接" in msg

        # ② 两者同时成立 —— 真凶在前，profile 缺项也要提但标明次序
        both = MacThroughputConfigResult(
            skipped=("TDD_PATTERN",), missing_mandatory=("TDD_PATTERN",),
            error="TimeoutError: VI_ERROR_TMO")
        msg2 = MeasureExecutor._mac_config_blocker(both)
        assert msg2.index("下发过程中出错") < msg2.index("本 profile 未定义"), (
            "profile 缺项排在传输错误前面 —— 排障会先走错方向")
        assert "先查上面那个错误" in msg2

    def test_measure_actually_reads_missing_mandatory(self):
        """⭐ 不变量门 —— 用 **AST** 判，不是搜源码文本。

        ⚠ 第一版写成"在调用点往后 2000 字符里搜 `missing_mandatory`"，
        **被上方注释里的同一个词喂绿**（变异 M9 删掉消费逻辑后照样通过）——
        跟今天 `"STOP" in detail` 那条恒真断言是同一个形态。
        **注释不进 AST**，所以改成扫 AST 节点，从根上堵掉。
        """
        import ast
        import inspect

        from app.services.mimo_ota.executors import measure

        tree = ast.parse(inspect.getsource(measure))
        hits = [
            n for n in ast.walk(tree)
            if (isinstance(n, ast.Attribute) and n.attr == "missing_mandatory")
            or (isinstance(n, ast.Constant) and n.value == "missing_mandatory")
        ]
        assert hits, (
            "调用点没有真正读取 `missing_mandatory`（AST 里找不到）—— "
            "返回值又被丢掉了，等于换个姿势继续在没配置过的链路上跑测试")

    def test_error_message_makes_no_claim_about_instrument_capability(self):
        """⭐ 措辞是**给现场看的判据**，而我们对仪器能力**两个方向都没证据**。

        本片连错两次才收敛到这里：
          ① 凭 profile 现状断言「IRAT **不支持**」；
          ② 照 NotebookLM 的**推断**改成「仪器**支持**、是我们没写」——
             它后来自己撤回，说那句「在手册原文里完全没有依据」。

        手册原件实查（单点权威）：这 11 条标 `NSA | SA`（不含 `IRAT`），
        **但我们 profile 里已定义、现场在用的 `BAND`/`DL:ARFCN`/`DL:BW`
        同样标 `NSA | SA`** —— 所以这个字段**答不了** TAP 可用性，
        标注既不证明支持也不证明不支持。且这批命令从未被真机普查过
        （`uxm_scpi_compatibility` 跳过 `None` 模板）。

        代价不对称：说"支持"而实际不支持 → 现场按错方向白烧时间；
        说"未经查证" → 零代价，普查一次即知。**所以门断言的是「不下结论」。**
        变异：把任一方向的结论写回消息 → 红。
        """
        import inspect

        from app.services.mimo_ota.executors import measure

        src = _strip_comments(inspect.getsource(measure))
        i = src.index("P1-32: 3GPP MAC 吞吐量配置未生效")
        msg = src[i:i + 1200]
        assert "profile 未定义" in msg, "没说清是 profile 缺项（这是唯一的事实）"
        assert "未经查证" in msg, "没标明仪器能力未经查证"
        # ⭐ 关键：**两个方向的结论都不许出现**
        for claim in ("不是仪器不支持", "仪器支持", "方言不支持", "仪器不支持"):
            assert claim not in msg.replace("「仪器不支持」或「仪器支持」", ""), (
                f"消息里对仪器能力下了结论: {claim!r} —— 我们两个方向都没证据")

    def test_start_signaling_is_not_reached_when_mandatory_missing(self):
        """⭐ **生效端** —— 光断言"返回 FAILED"不够，
        要证明 `start_signaling()` **根本没被调用**。
        上一版的病就是"报了失败还照样往下跑"。
        """
        import inspect

        from app.services.mimo_ota.executors import measure

        src = _strip_comments(inspect.getsource(measure))
        i = src.index("configure_mac_throughput_test(")
        j = src.index("await base_station.start_signaling()", i)
        between = src[i:j]
        assert "return StepExecutionResult" in between, (
            "FAILED 分支不在 start_signaling 之前 —— 报了失败仍会继续下发信令")
