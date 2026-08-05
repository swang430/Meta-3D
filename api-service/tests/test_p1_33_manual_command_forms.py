"""P1-33 门 —— 按手册补齐 IRAT 的 MAC 配置命令 + 值形态转换 + APPLY 前置。

本片的全部风险都在**值形态**上：旧写法发的是裸值（`4` / `16` / `"5MS"` /
`"ALL"` / `"DDDSU"`），而手册要的是枚举 token（`N4` / `MS5` / `P4`）、
整数 PRB 数、以及**六个数**的 TDD。发错形态跟没发是一样的后果（配置不生效），
但**更难发现** —— 命令名对得上，看日志像配上了。

⚠️ 另一半是「禁盲试」：5G profile 里那批 MAC 命令**手册 0 命中**（编的），
本片全部置 `None`。门要守住它们**不许再出现**。
"""
from __future__ import annotations

import asyncio
import glob
import io
import os
import re

import pytest

from app.hal.uxm_base_station import (
    MacThroughputConfigResult,
    RealUxmDriver,
    _CSIRS_NPORTS_VALUES,
    _HARQ_MAXTRANS_VALUES,
    _HARQ_PROCESSES_VALUES,
    _TDD_PERIOD_TOKENS,
    _enum_token,
    _tdd_slots_from_pattern,
)
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)
from tests.test_uxm_kpi_readback import _stub_io

_MANUAL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Instrument_API_Doc", "Keysight UXM NR SCPI")


def _drv(profile=UxmLteNrIratProfile, responses=None):
    d = RealUxmDriver("uxm-1", {"resource": "TCPIP0::x::inst0::INSTR"})
    d._cmds = profile
    d._connected = True
    resp = {"*OPC?": "1", "NUM:PRBS": "273", "SYSTem:ERRor": '0,"No error"',
            "SYST:ERR": '0,"No error"',
            # TDD STATE 回读 —— 不桩则走「回读失败」分支（Codex #281 P1）
            "TDDPATtern:STATE": "1",
            # 生效端 SCS（MU0=15kHz）—— 校验打在它上面，不是 TestCase 请求值
            "TDDPATtern:SUBCarrier:SPACing": "MU0"}
    resp.update(responses or {})
    return d, _stub_io(d, resp)


def _run(profile=UxmLteNrIratProfile, responses=None, **kw):
    # ⚠ TDD 要校验 SCS 一致性（Codex #281 P1）——`DDDSU`(5 slot)+`5MS`
    #   只在 **15kHz** 下自洽。夹具不传就走"不校验就不发"，测不到本门要测的。
    kw.setdefault("scs_khz", 15)
    d, writes = _drv(profile, responses)
    res = asyncio.run(d.configure_mac_throughput_test(**kw))
    return res, writes


def _cell_of(profile=UxmLteNrIratProfile):
    """驱动**实际用的**小区名 —— 别拿 `PRIMARY_CELL` 猜（它只是 profile 的声明，
    驱动实例的 `_cell_id` 才是真发出去的那个）。"""
    d, _ = _drv(profile)
    return d._cell_id


# ── 门① 值形态转换助手（纯函数，真值表）──────────────────────

class TestValueShapeHelpers:
    @pytest.mark.parametrize("val,expect", [
        (4, "N4"), (16, "N16"), (1, "N1"), (28, "N28"),
        (9, None), (0, None), (100, None),        # 不在手册枚举里
    ])
    def test_harq_maxtrans_token(self, val, expect):
        assert _enum_token("N", val, _HARQ_MAXTRANS_VALUES) == expect

    @pytest.mark.parametrize("val,expect", [
        (2, "P2"), (4, "P4"), (8, "P8"), (32, "P32"),
        (6, None), (3, None), (64, None),
    ])
    def test_csirs_ports_token(self, val, expect):
        assert _enum_token("P", val, _CSIRS_NPORTS_VALUES) == expect

    def test_no_nearest_fallback(self):
        """⭐ 不在枚举里就返回 None —— **绝不就近取一个**。

        「6 端口不支持就发 8」看着体贴，实际是**静默改了测试条件**：
        操作员以为测的是 6 端口。同 memory「路径 B 绝不用默认 fallback 静默兜底」。
        变异：`return f"{prefix}{value}"` 无条件返回 → 红。
        """
        assert _enum_token("P", 6, _CSIRS_NPORTS_VALUES) is None
        assert _enum_token("N", 9, _HARQ_MAXTRANS_VALUES) is None

    @pytest.mark.parametrize("pat,expect", [
        ("DDDSU", (3, 1)), ("DDDDDDDSUU", (7, 2)), ("DU", (1, 1)),
        ("dddsu", (3, 1)),                        # 大小写不敏感
        ("DDXU", None), ("", None), (None, None), ("DDD SU", None),
    ])
    def test_tdd_pattern_to_slots(self, pat, expect):
        assert _tdd_slots_from_pattern(pat) == expect

    def test_period_tokens_cover_the_manual_enum(self):
        """⭐ 手册 Range: MS0P5|MS0P625|MS1|MS1P25|MS2|MS2P5|MS3|MS4|MS5|MS10。
        少一个就会把合法配置判成"翻不了"而整组不发。"""
        assert set(_TDD_PERIOD_TOKENS.values()) == {
            "MS0P5", "MS0P625", "MS1", "MS1P25", "MS2",
            "MS2P5", "MS3", "MS4", "MS5", "MS10"}


# ── 门② 生效端：真发出去的是手册形态 ─────────────────────────

class TestWireFormIsTheManualForm:
    """⭐ 断言**真发出去的整串**，不是"返回值好看"。

    发错形态跟没发一样（配置不生效），但更难发现 —— 命令名对得上。
    """

    def test_every_value_shape_conversion_reaches_the_wire(self):
        _, writes = _run(mimo_layers=2, mcs=28, enable_amc=False,
                         tdd_pattern="DDDSU", tdd_period="5MS",
                         harq_max_trans=4, harq_processes=16)
        P = UxmLteNrIratProfile
        _CELL = _cell_of()
        c = {"cell": _CELL, "bwp": "BWP0"}
        cases = [
            (f"{P.PDSCH_SCHED_ALGO} FULL_TPUT", "Full Buffer 的 token 是 FULL_TPUT"),
            (f"{P.PDSCH_AMC_ENABLE.format(**c)} FIXed", "关 AMC = 资源策略 FIXed"),
            (f"{P.PUSCH_AMC_ENABLE.format(**c)} ON", "UL 固定 MCS 开关语义反过来"),
            (f"{P.PDSCH_MCS} 28", "固定 MCS"),
            (f"{P.PDSCH_RB_ALLOC} 273", '"ALL" → 整数 PRB 数'),
            (f"{P.TDD_PERIOD.format(cell=_CELL)} MS5", '"5MS" → MS5'),
            (f"{P.TDD_DL_SLOTS.format(cell=_CELL)} 3", "DDDSU 的 3 个 D"),
            (f"{P.TDD_UL_SLOTS.format(cell=_CELL)} 1", "DDDSU 的 1 个 U"),
            (f"{P.TDD_DL_SYMBOLS.format(cell=_CELL)} 6", "S 槽 DL 符号数"),
            (f"{P.TDD_UL_SYMBOLS.format(cell=_CELL)} 4", "S 槽 UL 符号数"),
            (f"{P.HARQ_MAX_TRANS.format(cell=_CELL)} N4", "4 → N4"),
            (f"{P.HARQ_PROCESSES.format(cell=_CELL)} N16", "16 → N16"),
            (f"{P.CSIRS_PORTS.format(cell=_CELL)} P4", "2 层 → P4"),
        ]
        for expect, why in cases:
            assert expect in writes, f"{why} —— 没发出 {expect!r}"

    def test_no_bare_value_reaches_the_wire(self):
        """⭐ 反向：**裸值一条都不许出现**。
        正向断言只证明对的发了，证明不了错的没发（两者可以并存）。"""
        _, writes = _run(mimo_layers=2, harq_max_trans=4, harq_processes=16)
        P, _CELL = UxmLteNrIratProfile, _cell_of()
        for tpl, bare in (
            (P.HARQ_MAX_TRANS, "4"), (P.HARQ_PROCESSES, "16"),
            (P.CSIRS_PORTS, "4"), (P.TDD_PERIOD, "5MS"),
        ):
            bad = f"{tpl.format(cell=_CELL)} {bare}"
            assert bad not in writes, f"发出了旧的裸值形态: {bad!r}"

    def test_apply_is_sent_after_the_config_writes(self):
        """⭐ 手册：小区 ON 时不发 APPLY，上面全部只进缓存**不进协议栈**。
        顺序才是判据 —— APPLY 发在配置之前等于没发。"""
        _, writes = _run(mimo_layers=2)
        P = UxmLteNrIratProfile
        qapply = [i for i, w in enumerate(writes) if P.QCONFIG_APPLY_ALL in w]
        gapply = [i for i, w in enumerate(writes) if w.strip() == P.CONFIG_APPLY]
        qcfg = [i for i, w in enumerate(writes) if "QCONFig:SCENario" in w
                or "QCONFig:DL:MCS" in w or "QCONFig:DL:NUM:PRBs" in w]
        amc = [i for i, w in enumerate(writes) if "RRESource:APOLicy" in w]
        tdd = [i for i, w in enumerate(writes) if "TDDPATtern" in w]
        assert qapply, "没发 Quick Config 自己的 apply —— 三条核心参数只是暂存值"
        assert gapply, "没发通用 APPLY —— 小区缓存配置不进协议栈"
        # ⭐ Quick Config 的 apply 要在它那三条**之后**、slot 级 AMC **之前** ——
        #   手册：应用场景会把当前 scheduler 配置完全抹掉并替换（内审 F2）。
        assert qcfg and qapply[0] > max(qcfg), "Quick Config apply 发早了"
        assert amc and qapply[0] < min(amc), (
            "Quick Config apply 发在 AMC 之后 —— 会把刚配好的 AMC 抹掉")
        # 通用 APPLY 收尾，在所有配置写入之后
        assert gapply[-1] > max(tdd), "通用 APPLY 发在配置之前 —— 等于没发"


# ── 门③ 不猜：翻不了就不发 ───────────────────────────────────

class TestRefusesToGuess:
    def test_illegal_tdd_pattern_skips_the_whole_group(self):
        """`"DDXU"` 翻不成手册形态 → **整组不发**，不猜。"""
        res, writes = _run(mimo_layers=2, tdd_pattern="DDXU")
        assert "TDD_DL_SLOTS" in res.missing_mandatory
        assert not any("TDDPATtern" in w for w in writes), "翻不了却发了"
        assert res.ok is False

    def test_unsupported_period_skips_the_whole_group(self):
        res, writes = _run(mimo_layers=2, tdd_period="7MS")
        assert "TDD_PERIOD" in res.missing_mandatory
        assert not any("TDDPATtern" in w for w in writes)

    def test_harq_value_outside_manual_enum_is_not_rounded(self):
        """9 不在手册枚举里 → 不发，**不就近取 8 或 10**。"""
        res, writes = _run(mimo_layers=2, harq_max_trans=9)
        assert "HARQ_MAX_TRANS" in res.skipped
        P, _CELL = UxmLteNrIratProfile, _cell_of()
        assert not any(P.HARQ_MAX_TRANS.format(cell=_CELL) in w
                       for w in writes)

    def test_prb_unreadable_does_not_fall_back_to_273(self):
        """⭐ `"ALL"` 要问仪器本 BWP 的 PRB 数；**读不到就不猜**。

        退回手册默认 273 会在窄带宽小区上发一个超出上限的值 ——
        看着配上了，实际被拒或被截断。
        """
        res, writes = _run(responses={"NUM:PRBS": "<no data>"}, mimo_layers=2)
        assert "PDSCH_RB_ALLOC" in res.missing_mandatory
        assert not any(UxmLteNrIratProfile.PDSCH_RB_ALLOC in w for w in writes)
        assert res.ok is False


# ── 门④ 被拒 ≠ 没定义 ────────────────────────────────────────

class TestRejectedIsItsOwnCategory:
    """⭐ 「我们发了、它不认」跟「profile 没定义」是两回事 ——
    前者正是「IRAT 认不认这批手册命令」的**实测答案**。"""

    def test_instrument_rejection_lands_in_rejected_not_skipped(self):
        res, _ = _run(responses={"SYSTem:ERRor": '-113,"Undefined header"',
                                 "SYST:ERR": '-113,"Undefined header"'},
                      mimo_layers=2)
        assert res.rejected, "被拒的命令没记名 —— 现场拿不到实测答案"
        assert res.skipped == (), "被拒被误记成 profile 没定义"
        assert res.ok is False, "有命令被拒却报 ok"

    def test_no_equivalent_is_reported_and_not_a_profile_gap(self):
        """⛔ 统计窗口手册里没有对应命令 —— 既不是 profile 缺项也不是被拒。"""
        res, _ = _run(mimo_layers=2)
        assert res.no_equivalent == ("MEAS_TPUT_STAT_COUNT",)
        assert "MEAS_TPUT_STAT_COUNT" not in res.missing_mandatory
        assert "MEAS_TPUT_STAT_COUNT" not in res.skipped
        assert res.ok is True, "手册没有对应命令不该让整件事失败"


# ── 门⑤ 禁盲试：编出来的命令不许再出现 ───────────────────────

class TestNoFabricatedCommands:
    """⭐ 逐条 grep 厂商手册原件 —— 手册 0 命中的命令**一条都不许留在 profile 里**。

    这批曾经在 5G profile 里，从没在真机上工作过（发出去等 -113）。
    """

    _FABRICATED = ("PDSCH:SchedAlgoritm", "PDSCH:AMC:ENABle", "PUSCH:AMC:ENABle",
                   "PDSCH:RB:ALLocation", "CSIRS:PORTs", "HARQ:MaxTrans",
                   "BTHRoughput:DL:TSTatistics:COUNt")

    @pytest.mark.parametrize("profile", [UxmLteNrIratProfile,
                                         Uxm5GNRTestAppProfile],
                             ids=["IRAT", "5G_NR"])
    def test_no_profile_still_defines_them(self, profile):
        live = [
            f"{k}={v}" for k in dir(profile)
            if not k.startswith("_") and isinstance((v := getattr(profile, k, None)), str)
            for frag in self._FABRICATED if frag in v
        ]
        assert live == [], f"profile 仍定义着手册里不存在的命令: {live}"

    @pytest.mark.skipif(not glob.glob(os.path.join(_MANUAL_DIR, "*.md")),
                        reason="厂商手册原件不在这台机器上（未随仓库分发）")
    def test_every_mac_command_is_findable_in_the_manual(self):
        """⭐ **不变量门** —— IRAT 上每条 MAC 配置命令都必须能在手册原件里指到。

        这是「禁盲试」唯一能机械检查的形态：新加一条编的命令 → 红。
        （手册文件不在时跳过 —— 它不随仓库分发，不能让门在别的机器上假红。）
        """
        text = "".join(
            io.open(f, encoding="utf-8", errors="replace").read()
            for f in sorted(glob.glob(os.path.join(_MANUAL_DIR, "*.md"))))

        def shape(cmd: str):
            """归一化成段序列：占位符与**索引/技术维度的具体取值**统一成 `*`。

            手册写 `<cell>` / `<cri>` / `<celltype>`，我们写 `{cell}` / `CRI0` /
            `NR5G` —— 不归一化就必然对不上，而"对不上"会被误读成"这条命令是编的"。
            """
            out = []
            for seg in cmd.split(":"):
                seg = seg.strip()
                if not seg:
                    continue
                if ("<" in seg or "{" in seg or "[" in seg
                        or re.fullmatch(r"(CRI|FC|SC|BWP|CELL)\d*", seg, re.I)):
                    # ⚠ **技术名（NR5G/LTE/NBIot/SLINk）绝不归一** ——
                    #   归一了就等于放行「拿 LTE-only 的命令改个技术名冒充
                    #   NR5G」，而 `BTHRoughput:LENGth` 正好是这种（内审 F7）。
                    out.append("*")
                else:
                    out.append(seg.upper().rstrip("?"))
            return tuple(out)

        def variants(cmd: str):
            """展开手册的**可选节点** `X[:<y>]` —— 那段可有可无，两种都算合法。

            不展开的话，我们写 `...:UL:IMCS:FIXed`（省掉可选的 `<ultype>`）
            会被判成"手册里没有"，而那是**正确的 SCPI 写法**。
            """
            groups = re.findall(r"\[:[^\]]*\]", cmd)
            outs = {cmd}
            for g in groups:
                outs |= {c.replace(g, "") for c in outs}
                outs |= {c.replace(g, ":" + g[2:-1]) for c in outs}
            # ⚠ `<celltype>` 是**技术名的 band 占位符**，展开成它的具体取值 ——
            #   而不是把技术名归一成 `*`。区别要紧：`BSE:CONFig:<celltype>:APPLY`
            #   合法地涵盖 NR5G；但 `BSE:MEASure:LTE:<cell>:BTHRoughput:LENGth`
            #   里的 `LTE` 是**字面量**，把它换成 NR5G 就是编命令（内审 F7）。
            if "<celltype>" in cmd:
                outs |= {c.replace("<celltype>", t)
                         for c in set(outs) for t in ("LTE", "NR5G", "SL", "NBIot")}
            return outs

        manual = set()
        for m in re.finditer(r"\*\*SCPI(?: variant #\d)?\*\*:\s*`([^`]+)`", text):
            for v in variants(m.group(1)):
                manual.add(shape(v))
        missing = []
        # ⚠ 遍历范围不能只取两张分级表 —— `PHY_DL_BWP_NUM_PRBS` 不在表里，
        #   曾是这道门的盲区（内审 F7）。改成"本片涉及的全部 MAC 命令属性"。
        names = (list(RealUxmDriver.MAC_CFG_MANDATORY)
                 + list(RealUxmDriver.MAC_CFG_OPTIONAL)
                 + ["PHY_DL_BWP_NUM_PRBS"])
        for name in names:
            tpl = getattr(UxmLteNrIratProfile, name, None)
            if not tpl:
                continue
            if shape(tpl) not in manual:
                missing.append(f"{name} → {tpl}")
        assert missing == [], "这些命令在手册原件里指不到（禁盲试）:\n" + "\n".join(missing)


# ── 门⑥ 内审 R1 修复各自的门 ──────────────────────────────────

class TestReviewFixes:
    def test_baseline_errors_are_not_blamed_on_the_first_group(self):
        """⭐ 内审 F3 —— 进函数前队列里的 stale 错误，不能记到第一组头上。

        不清基线的话，`set_cell_config` 刚跑完留下的错误会让
        `PDSCH_SCHED_ALGO` 被误报成"被 IRAT 拒了" —— 而那正是本片要产出的
        实测答案，第一条就成伪证。
        """
        seen = {"n": 0}

        class _StaleOnce:
            """只有**第一次**读错误队列时吐一条 stale 错误。"""
            def __init__(self, inner):
                self._inner = inner

        d, writes = _drv()
        orig = d._do_query

        def _q(cmd, **kw):
            if "ERR" in cmd.upper():
                seen["n"] += 1
                return '-224,"stale from previous step"' if seen["n"] == 1 else '0,"No error"'
            return orig(cmd, **kw)

        d._do_query = _q
        res = asyncio.run(
            d.configure_mac_throughput_test(mimo_layers=2, scs_khz=15))
        assert res.rejected == (), (
            f"上一步的残留错误被记成本次被拒: {res.rejected}")
        assert res.ok is True

    def test_invalid_tdd_pattern_is_caught_by_state_readback(self):
        """⭐ 内审 F5 —— 手册：pattern 无效时**不报错**，只是 STATE 保持 OFF。
        所以「写了」不等于「配上了」，必须回读。"""
        res, _ = _run(responses={"TDDPATtern:STATE": "0"}, mimo_layers=2)
        assert any("TDD" in r for r in res.rejected), (
            "STATE 回读是 OFF（pattern 被判无效）却没记进 rejected —— "
            "手册说这种情形不产生 SCPI 错误，光看错误队列看不出来")
        assert res.ok is False

    def test_state_readback_on_means_accepted(self):
        """反向 —— 回读 ON 就不该记 rejected，否则上一条门用恒红实现也能过。"""
        res, _ = _run(responses={"TDDPATtern:STATE": "1"}, mimo_layers=2)
        assert not any("TDD" in r for r in res.rejected)

    def test_template_with_leftover_placeholder_is_not_sent(self):
        """⭐ 内审 F8 —— 零 fmt 时旧实现直接返回模板，含 `{cell}` 就把花括号
        **原样发到线上**还报 ok。视同未定义。"""
        class _Placeholder(UxmLteNrIratProfile):
            PDSCH_SCHED_ALGO = "BSE:CONFig:NR5G:{cell}:SCHeduling:QCONFig:SCENario"

        res, writes = _run(_Placeholder, mimo_layers=2)
        assert not any("{" in w for w in writes), (
            f"把带占位符的残缺串发出去了: {[w for w in writes if '{' in w]}")
        assert "PDSCH_SCHED_ALGO" in res.missing_mandatory

    def test_rejected_has_its_own_operator_message(self):
        """⭐ 内审 F4 —— 「哪几组被拒」是本片的核心产出，
        不能落进「驱动报告配置失败：（无详情）」。"""
        from app.services.mimo_ota.executors.measure import MeasureExecutor

        msg = MeasureExecutor._mac_config_blocker(
            MacThroughputConfigResult(applied=("A",), rejected=("AMC", "TDD")))
        assert "被仪器拒" in msg and "AMC" in msg and "TDD" in msg
        assert "无详情" not in msg
        assert "本片要现场问的" in msg, "没说清这就是现场要的实测答案"


# ── 门⑦ Codex #281 两条 P1 ───────────────────────────────────

class TestScsConsistency:
    """⭐ 手册把 **Subcarrier spacing of DL and UL BW parts** 列为
    `TDDPATtern:STATE` 的 Dependencies —— pattern 的**含义依赖 SCS**。"""

    def test_default_repo_config_is_caught(self):
        """⭐ 仓库默认 `DDDSU` + `5MS` + `scs=30` **对不上**：
        30kHz 下 5 个 slot = 2.5ms，而周期要 5ms（10 slot）——
        照发不会被拒，只会静默变成「3 DL + 1 UL + 6 flexible」，
        **测的是另一个配置**。静默测错的量 > 显式失败，所以不发。
        """
        res, writes = _run(mimo_layers=2, tdd_pattern="DDDSU",
                           tdd_period="5MS", scs_khz=30)
        assert "TDD_DL_SLOTS" in res.missing_mandatory
        assert not any("TDDPATtern" in w for w in writes), "对不上却照发了"
        assert res.ok is False

    def test_consistent_combination_is_sent(self):
        """反向 —— 自洽就得发，否则上一条门用恒不发也能过。
        生效端 MU1=30kHz，`DDDSU`(5 slot)×0.5ms=2.5ms 与 `2.5MS` 对得上。"""
        res, writes = _run(responses={"TDDPATtern:SUBCarrier:SPACing": "MU1"},
                           mimo_layers=2, tdd_pattern="DDDSU",
                           tdd_period="2.5MS", scs_khz=30)
        assert "TDD_DL_SLOTS" not in res.missing_mandatory
        assert any("TDDPATtern:DLSLots" in w for w in writes)

    def test_request_scs_absent_still_validated_against_live(self):
        """⭐ TestCase 没给 SCS **不等于**没法校验 —— 生效端读得到就按它校验。

        （Codex #281 R2 之前这里是"请求值缺省就不发"；现在权威源是仪器，
        请求值只当**交叉校验**用。真正该拒的是"生效端读不到"，
        由 `test_unreadable_live_scs_refuses_to_send` 守。）
        """
        res, writes = _run(mimo_layers=2, scs_khz=None)
        assert "TDD_DL_SLOTS" not in res.missing_mandatory
        assert any("TDDPATtern:DLSLots" in w for w in writes)


class TestStateReadbackFailureIsNotSilentlyAccepted:
    def test_unreadable_state_counts_as_rejected(self):
        """⭐ Codex #281 P1 —— 回读是发现「pattern 被静默判无效」的**唯一**手段；
        这条手段不可用 = 等于没检查过，**不能当没问题**。
        变异：`if not st:` 那格删掉（回到 `if st and ...`）→ 红。
        """
        res, _ = _run(responses={"TDDPATtern:STATE": ""}, mimo_layers=2)
        assert any("回读失败" in r for r in res.rejected), (
            "STATE 读不到却静默放过 —— ok 会保持 True，调用方照常往下测")
        assert res.ok is False


# ── 门⑧ Codex #281 R2 三条 P1 ────────────────────────────────

class TestScsMustComeFromTheInstrument:
    """⭐ 入参 `scs_khz` 只是 TestCase 的**请求值** —— IRAT 上 `CELL_SCS`
    未定义（只进缓存不下发）、inherit 模式整段跳过，仪器可能在别的 SCS 上。
    拿请求值算 slot 时长，会把错的组合判成"自洽"（Codex #281 R2 P1）。"""

    def test_live_scs_disagreeing_with_request_fails_loud(self):
        """请求 15kHz、仪器生效 30kHz（MU1）→ **不拿任一方去校验**。"""
        res, writes = _run(responses={"TDDPATtern:SUBCarrier:SPACing": "MU1"},
                           mimo_layers=2, scs_khz=15)
        assert "TDD_DL_SLOTS" in res.missing_mandatory
        assert not any("TDDPATtern:DLSLots" in w for w in writes)

    def test_unreadable_live_scs_refuses_to_send(self):
        res, writes = _run(responses={"TDDPATtern:SUBCarrier:SPACing": ""},
                           mimo_layers=2, scs_khz=15)
        assert "TDD_PERIOD" in res.missing_mandatory
        assert not any("TDDPATtern:DLSLots" in w for w in writes)

    def test_validation_uses_the_live_value(self):
        """⭐ 生效端是 15kHz（MU0）时，`DDDSU`+`5MS` 自洽 → 照发。
        反向配对上面两条，防它们用"恒不发"实现糊过去。"""
        res, writes = _run(responses={"TDDPATtern:SUBCarrier:SPACing": "MU0"},
                           mimo_layers=2, scs_khz=15)
        assert "TDD_DL_SLOTS" not in res.missing_mandatory
        assert any("TDDPATtern:DLSLots" in w for w in writes)


class TestPatternOrderingMustBeEncodable:
    """⭐ 六个数只能表达 `D…D [S] U…U`。只数个数会把 `DUS` 放过 ——
    翻出来等于 `DSU`，仪器接受、STATE 保持 ON，**静默跑了另一个 pattern**。"""

    @pytest.mark.parametrize("pat,ok", [
        ("DDDSU", True), ("DDDDDDDSUU", True), ("DU", True), ("DDD", True),
        ("DUS", False), ("UDDS", False), ("SDU", False), ("DSUD", False),
    ])
    def test_only_canonical_order_is_accepted(self, pat, ok):
        assert (_tdd_slots_from_pattern(pat) is not None) is ok, (
            f"{pat!r} 的排布六个数{'能' if ok else '**不能**'}复现")

    def test_non_canonical_pattern_is_not_sent(self):
        res, writes = _run(mimo_layers=2, tdd_pattern="DUS", tdd_period="1.5MS")
        assert "TDD_DL_SLOTS" in res.missing_mandatory
        assert not any("TDDPATtern:DLSLots" in w for w in writes)


class TestExplicitCsiRsPortsWins:
    """⭐ 端口数可以**故意**大于层数。按层数推会把显式 8 端口静默降成 P4
    —— 我删 `set_cell_config` 那段时把这个覆盖丢了（Codex #281 R2 P1）。"""

    def test_explicit_value_overrides_the_layer_derivation(self):
        _, writes = _run(mimo_layers=2, csi_rs_ports=8)
        P, C = UxmLteNrIratProfile, _cell_of()
        assert f"{P.CSIRS_PORTS.format(cell=C)} P8" in writes, (
            "显式 8 端口被按层数推成 P4 —— 静默改了测试条件")

    def test_falls_back_to_layer_derivation_when_absent(self):
        _, writes = _run(mimo_layers=2)
        P, C = UxmLteNrIratProfile, _cell_of()
        assert f"{P.CSIRS_PORTS.format(cell=C)} P4" in writes

    def test_caller_passes_the_explicit_value(self):
        """不变量门：调用点必须把 `csi_rs_ports` 传下去，否则驱动侧支持等于零。"""
        import ast
        import inspect

        from app.services.mimo_ota.executors import measure

        tree = ast.parse(inspect.getsource(measure))
        assert any(
            isinstance(n, ast.keyword) and n.arg == "csi_rs_ports"
            for n in ast.walk(tree)), (
            "调用点没传 csi_rs_ports —— TestCase 的显式覆盖到不了驱动")
