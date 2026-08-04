"""P1-31 门 —— `uxm_kpi_readback` 诊断序列。

本序列的契约与别的序列**不同**，门也就守不同的东西：

  · 它是**只呈现不判定**的探针 —— 所以"元素个数不符"必须**照样跑完并标注**，
    不能当失败中止（个数不符恰恰是最要紧的发现）。
  · 它**绝不能传 expect** —— 拿期望值去比等于预设答案，那正是它要治的病
    （同 `propsim_f64_state_machine` 的禁令）。
  · 它**改仪器状态**（开累积 + 清零窗口），所以写过的必须在 `finally` 写回
    （同 `uxm_config_truth_probe` 的纪律），且 `safe_during_test=False`。
  · `raw` **逐字保留**仪器回复，不归一化（`protocol.py` 的字段约定）。
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.diagnostics.sequences import uxm_kpi_readback as seq
from app.hal.uxm_command_profiles import Uxm5GNRTestAppProfile


class _FakeBs:
    """假 baseStation：按命令片段查表回值，记录所有写命令与查询顺序。"""

    def __init__(self, responses: dict, profile=None, raise_on: str = "",
                 raise_on_write: str = ""):
        self._responses = responses
        self._profile = profile
        self._raise_on = raise_on
        self._raise_on_write = raise_on_write
        self.writes: list[str] = []
        self.queries: list[str] = []
        # _profile_for_driver 认这个属性
        self._cmds = profile

    def _query(self, cmd, **kw):          # sync —— 与真 UXM 契约一致
        self.queries.append(cmd)
        if self._raise_on and self._raise_on in cmd:
            raise TimeoutError("probe boom")
        for frag, resp in self._responses.items():
            if frag in cmd:
                return resp
        return ""

    def _write(self, cmd, **kw):
        self.writes.append(cmd)
        if self._raise_on_write and self._raise_on_write in cmd:
            raise OSError("write boom")
        return None


def _irat_profile():
    from app.hal.uxm_command_profiles import UxmLteNrIratProfile
    return UxmLteNrIratProfile


@pytest.fixture
def no_sleep(monkeypatch):
    """跳过真实等待 —— 只在**不断言时长**的用例上用。

    ⚠ `test_zero_is_honoured_not_replaced_by_default` **不能**用它：
    那条正是靠墙钟时间证明"传 0 没被换成 3"，patch 掉 sleep 就恒绿了
    （= 恒真断言）。
    """
    async def _instant(_s):
        return None
    monkeypatch.setattr("app.diagnostics.sequences.uxm_kpi_readback.asyncio.sleep",
                        _instant)


def _run(bs, params=None):
    # ⚠ 不能写 `params or {...}` —— **`{}` 也是 falsy**，测"键缺省走默认值"
    #   的用例会被悄悄换成带 window_s 的字典，永远测不到那条路径。
    #   跟被测代码里那个 `window_s or 3.0` 是同一个母题，同一次提交两处。
    if params is None:
        params = {"window_s": 0}
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}
    return asyncio.run(seq.run(MagicMock(), hal, params, log=lambda *_: None))


# ── 门① 元数据与安全性 ─────────────────────────────────────────

class TestMetadata:
    def test_not_safe_during_test(self):
        """⭐ 它发 `BTHRoughput:STATe ON` / `CSI:STARt` / **`CLEar`** ——
        `CLEar` 会清零正在跑的窗口。标成安全会让 GUI 告诉操作员"测试中可跑"，
        **跑一下就把正在测的 KPI 毁了**。

        变异：改成 `safe_during_test=True` → 红。
        """
        assert seq.metadata.safe_during_test is False

    def test_requires_base_station(self):
        assert seq.metadata.required_categories == ["baseStation"]

    def test_discovered_by_loader(self):
        from app.diagnostics import loader
        loader.reset_cache()
        assert "uxm_kpi_readback" in [s["key"] for s in loader.list_sequences()]


class TestNoExpectAnywhere:
    """⭐ 本序列**绝不能**拿期望值去比 —— 它问的正是"真机到底返回什么"。

    变异：给任一 `_probe` 传个 expect 并据此判失败 → 红。
    """

    def test_element_count_mismatch_still_succeeds_and_is_flagged(self):
        """个数不符是**最要紧的发现**，必须跑完并标注，不能当失败中止。"""
        bs = _FakeBs({"DL:THRoughput:OTA": "1,2,3"}, profile=_irat_profile())
        res = _run(bs)
        dl = [s for s in res.steps if s.label.startswith("①")][0]
        assert dl.success is True, "个数不符不该判失败 —— 那会让后面几项都不跑"
        assert "手册说 6 个" in dl.detail
        assert "错位" in dl.detail


# ── 门② 拒跑守门（不猜、不盲发） ────────────────────────────────

class TestRefusals:
    def test_no_driver(self):
        hal = MagicMock(); hal.drivers = {}
        res = asyncio.run(seq.run(MagicMock(), hal, {}, log=lambda *_: None))
        assert res.success is False

    def test_mock_driver_refused(self):
        from app.hal.base_station import MockBaseStation
        bs = MockBaseStation("bs-mock", {})
        hal = MagicMock(); hal.drivers = {"baseStation": bs}
        res = asyncio.run(seq.run(MagicMock(), hal, {}, log=lambda *_: None))
        assert res.success is False
        assert "mock" in res.summary.lower() or "Mock" in res.summary

    def test_wrong_dialect_refused_without_sending_anything(self):
        """⭐ 5G 方言没定义这批命令 —— 在它上面跑会全回 -113，
        于是得出"手册写法也不支持"的**错结论**。必须拒跑，**且一条都不发**。

        变异：去掉方言守门 → 本条红（会看到写命令）。
        """
        bs = _FakeBs({}, profile=Uxm5GNRTestAppProfile)
        res = _run(bs)
        assert res.success is False
        assert "方言" in res.summary
        assert bs.writes == [], "拒跑时不该发出任何写命令"
        assert bs.queries == [], "拒跑时不该发出任何查询"

    def test_bad_cell_param_refused(self):
        bs = _FakeBs({}, profile=_irat_profile())
        res = _run(bs, {"cell": "CELL0; DROP", "window_s": 0})
        assert res.success is False
        assert bs.writes == []


# ── 门③ 写过必须写回（uxm_config_truth_probe 的纪律） ───────────

class TestStateRestoredInFinally:
    """⭐ 序列开了测量累积就必须关回去 —— 绝不把仪器留在被本序列改过的状态。"""

    def test_state_restored_to_original(self):
        bs = _FakeBs({"BTHRoughput:STATe?": "0",
                      "MEASurement:REPort?": "0"}, profile=_irat_profile())
        _run(bs)
        joined = " | ".join(bs.writes)
        assert "BTHRoughput:STATe ON" in joined, "没开累积则所有 KPI 恒返 NaN"
        assert "BTHRoughput:STATe 0" in joined, "**没写回原值** —— 仪器被留在改过的状态"

    def test_restored_even_when_an_exception_escapes(self):
        """⭐ 中途抛出**逃出去的**异常，也必须走 finally 恢复。

        ⚠ 别用 `_probe` 里的查询来造异常 —— 它**自己 catch 了**，异常根本
        到不了外层，`finally` 也就没被考验（变异 M3 就是从这个缝钻过去的：
        把恢复段挪出 finally，原来的用例照样绿）。要用**没被包住**的调用，
        比如 CLEar 那条写命令。
        变异：把恢复段从 finally 挪成 else → 红。
        """
        # ⚠ 触发点选**没被 try 包住**的那条写命令。⑧ 的 CLEar 现在包了 try
        #   （内审 F8：不能让最后一步的异常带走前 7 步的证据），拿它当触发器
        #   就试不到 finally 了 —— 换成 P3 的 `MEASurement:REPort ON`。
        bs = _FakeBs({"BTHRoughput:STATe?": "0"}, profile=_irat_profile(),
                     raise_on_write="MEASurement:REPort ON")
        with pytest.raises(OSError):
            _run(bs)
        assert "BTHRoughput:STATe 0" in " | ".join(bs.writes), (
            "异常逃出后没走 finally 恢复 —— 仪器被留在开着累积的状态")

    def test_no_restore_when_original_unreadable(self):
        """读不到原值时**不猜一个写回去** —— 写 OFF 可能比留着更糟。
        必须显式报出来让人手动确认。"""
        bs = _FakeBs({}, profile=_irat_profile(), raise_on="BTHRoughput:STATe?")
        res = _run(bs)
        labels = [s.label for s in res.steps]
        assert any("读 BTHRoughput:STATe 原值" in l for l in labels)
        bad = [s for s in res.steps if "读 BTHRoughput:STATe 原值" in s.label][0]
        assert bad.success is False
        assert "不会写回" in bad.detail
        # ⭐ 关键：**真的没写回**，不是只报了一句。
        #   猜一个 OFF 写回去可能比留着更糟（原值可能本来就是 ON）。
        #   变异：`orig_state = orig_state or "OFF"` → 红。
        joined = " | ".join(bs.writes)
        assert "BTHRoughput:STATe OFF" not in joined
        assert "BTHRoughput:STATe 0" not in joined


# ── 门⑤ 内审 12 条 findings 的修复 ─────────────────────────────

class TestPrereqsAreVerifiedNotJustSent:
    """⭐ roadmap 第 ⑧ 项问的是「三条前置**真被接受**了吗」——
    只报"我发了什么"答不了（内审 F2/F4）。"""

    def test_csi_state_read_back_and_gates_success(self):
        """手册原文：`CSI:STARt` 在「已在跑」或「小区关闭」时**被忽略**。
        只发不回读就分不清"开成功"和"被静默忽略"，而 CQI/RI 全 NaN 时
        操作员会误判成"命令形式不对"。
        变异：删掉回读、把 success 写成常量 True → 红。"""
        bs = _FakeBs({"CSI:STATe?": "STOP",       # 发完仍是 STOP = 被忽略
                      "SYSTem:ERRor?": '0,"No error"'}, profile=_irat_profile())
        res = _run(bs)
        p2 = [x for x in res.steps if x.label.startswith("P2")][0]
        assert p2.success is False, "STARt 被静默忽略却报成功"
        assert "STOP" in p2.detail and "忽略" in p2.detail
        assert p2.raw == "STOP", "回读值要进 raw"

    def test_csi_meas_state_passes(self):
        bs = _FakeBs({"CSI:STATe?": "MEAS", "SYSTem:ERRor?": '0,"No error"'},
                     profile=_irat_profile())
        p2 = [x for x in _run(bs).steps if x.label.startswith("P2")][0]
        assert p2.success is True

    def test_prereq_success_derives_from_error_queue(self):
        """全被 -113 拒 → 步骤必须报失败，不能一律绿。
        变异：success 写回常量 True → 红。"""
        bs = _FakeBs({"SYSTem:ERRor?": '-113,"Undefined header"'},
                     profile=_irat_profile())
        res = _run(bs)
        p1 = [x for x in res.steps if x.label.startswith("P1")][0]
        assert p1.success is False
        assert res.success is False, "前置全被拒还报 success=True"


class TestErrorQueueHygiene:
    """⭐ 不清 stale + 一次只 pop 一条 → 把别人的旧错记到本序列头上，
    于是把**对的**命令记成"手册写法也不支持"（内审 F3）。"""

    def test_cls_sent_before_probing(self):
        bs = _FakeBs({}, profile=_irat_profile())
        _run(bs)
        assert "*CLS" in bs.writes, "跑前没清错误队列 —— stale 错会被记到本序列命令头上"
        assert bs.writes.index("*CLS") == 0, "*CLS 必须是第一条"

    def test_error_queue_drained_not_single_pop(self):
        """一条命令产生两个错误时，第二条不能串到下一步名下。"""
        seen = {"n": 0}

        class _MultiErr(_FakeBs):
            def _query(self, cmd, **kw):
                if "SYSTem:ERRor?" in cmd:
                    seen["n"] += 1
                    return ('-113,"A"' if seen["n"] % 3 == 1
                            else '-113,"B"' if seen["n"] % 3 == 2
                            else '0,"No error"')
                return super()._query(cmd, **kw)

        bs = _MultiErr({}, profile=_irat_profile())
        res = _run(bs)
        p1 = [x for x in res.steps if x.label.startswith("P1")][0]
        assert "||" in p1.detail, "只 pop 了一条 —— 剩下的会串到下一步"


class TestMissingCommandsAreLoud:
    """⭐ 方言缺命令时步骤**静默消失**，summary 仍"无失败步"，
    操作员按 roadmap 九项对应表以为都问过了（内审 F7）。"""

    def test_missing_command_emits_skipped_step_and_fails(self):
        class _PartialProfile(_irat_profile()):
            MEAS_CSI_RI = None
        bs = _FakeBs({}, profile=_PartialProfile)
        res = _run(bs)
        skipped = [x for x in res.steps if "SKIPPED" in x.label]
        assert skipped, "缺命令却没留任何痕迹"
        assert "MEAS_CSI_RI" in skipped[0].detail
        assert skipped[0].success is False
        assert res.success is False


class TestClearWindowVerdict:
    """⭐ progress 本来就是 0 时不能导出「CLEar 没生效」（内审 F6）——
    现场零流量正是最可能的首轮状态。"""

    def test_zero_progress_is_undecidable(self):
        bs = _FakeBs({"DL:THRoughput:OTA": "0,0,0,0,0,0"}, profile=_irat_profile())
        res = _run(bs)
        v = [x for x in res.steps if "结论" in x.label][0]
        assert "无法判定" in v.detail
        assert "没生效" not in v.detail

    def test_progress_drop_reads_as_consistent(self):
        calls = {"n": 0}

        class _Dropping(_FakeBs):
            def _query(self, cmd, **kw):
                if "DL:THRoughput:OTA" in cmd:
                    calls["n"] += 1
                    return ("5000,1,1,1,1,1" if calls["n"] <= 2
                            else "10,1,1,1,1,1")
                return super()._query(cmd, **kw)

        bs = _Dropping({}, profile=_irat_profile())
        v = [x for x in _run(bs).steps if "结论" in x.label][0]
        assert "变小了" in v.detail

    def test_each_read_has_its_own_raw(self):
        """`protocol.py` 约定 raw 原样存 —— 合成串违反它（内审 F9）。"""
        bs = _FakeBs({"DL:THRoughput:OTA": "7,1,1,1,1,1"}, profile=_irat_profile())
        res = _run(bs)
        a = [x for x in res.steps if x.label.startswith("⑧a")][0]
        c = [x for x in res.steps if x.label.startswith("⑧c")][0]
        assert a.raw == "7,1,1,1,1,1"
        assert c.raw == "7,1,1,1,1,1"
        assert "before=" not in (a.raw or "")


class TestNoSilentSkipOnRestore:
    """⭐ 恢复与否**都必须留一条步骤**，否则报告说假话（内审 F1）。"""

    def test_empty_original_still_emits_a_step(self):
        """原值回空串 → falsy → 早先整条恢复路径静默跳过，
        而 P1 的 detail 还写着"跑完写回"。变异：判据换回真值判断 → 红。"""
        bs = _FakeBs({"BTHRoughput:STATe?": ""}, profile=_irat_profile())
        res = _run(bs)
        r = [x for x in res.steps if x.label.startswith("R 写回 BTHRoughput:STATe")]
        assert r, "没有写回、也没有任何步骤说明 —— 这份现场记录在说假话"
        assert r[0].success is False
        assert "没有写回" in r[0].detail
        assert "BTHRoughput:STATe " not in " | ".join(
            w for w in bs.writes if w.endswith(" ")), "不该猜一个值写回去"

    def test_report_restore_is_symmetric_with_state(self):
        """两条同型路径不能两套标准（早先 REPort 读失败连步骤都不记）。"""
        bs = _FakeBs({"BTHRoughput:STATe?": "0", "MEASurement:REPort?": ""},
                     profile=_irat_profile())
        res = _run(bs)
        labels = [x.label for x in res.steps]
        assert any(l.startswith("R 写回 MEASurement:REPort") for l in labels)


class TestCsiRestoredOnlyWhenItWasStopped:
    """⭐ 代价不对称：无脑 STOP 会打断本来在跑的 CSI；不关则下次真实测试的
    `CSI:STARt` 被仪器**忽略**，CQI/RI 掺进本序列的样本（内审 F5）。"""

    def test_stops_when_originally_stopped(self):
        bs = _FakeBs({"CSI:STATe?": "STOP"}, profile=_irat_profile())
        _run(bs)
        assert any("CSI:STOP" in w for w in bs.writes)

    def test_does_not_stop_when_already_running(self):
        bs = _FakeBs({"CSI:STATe?": "MEAS"}, profile=_irat_profile())
        res = _run(bs)
        assert not any("CSI:STOP" in w for w in bs.writes), "打断了本来在跑的 CSI"
        r = [x for x in res.steps if "关回 CSI" in x.label][0]
        assert "不关" in r.detail


# ── 门④ 呈现质量：raw 逐字 + 候选读法并排 ───────────────────────

class TestWindowParam:
    """⭐ `0` / `None` / 键缺省是三件事。

    初版写 `params.get("window_s") or 3.0` —— **`0` 是 falsy**，操作员显式
    传 0 想跳过等待，会被静默换成 3.0（本文件的门就因此每个用例白等 6 秒，
    是它把这个 bug 撞出来的）。
    变异：改回 `or 3.0` → 红。
    """

    def test_zero_is_honoured_not_replaced_by_default(self):
        import time as _t
        bs = _FakeBs({}, profile=_irat_profile())
        t0 = _t.perf_counter()
        _run(bs, {"window_s": 0})
        assert _t.perf_counter() - t0 < 1.0, "显式传 0 却等了默认的 3 秒"

    def test_missing_key_uses_default(self, no_sleep):
        bs = _FakeBs({}, profile=_irat_profile())
        res = _run(bs, {})
        assert res.extra["window_s"] == 3.0

    def test_garbage_falls_back_to_default(self, no_sleep):
        bs = _FakeBs({}, profile=_irat_profile())
        assert _run(bs, {"window_s": "abc"}).extra["window_s"] == 3.0

    def test_negative_clamped_to_zero(self):
        bs = _FakeBs({}, profile=_irat_profile())
        assert _run(bs, {"window_s": -5}).extra["window_s"] == 0.0


class TestElementPositionsPreserved:
    """⭐ 空元素必须**占位**，否则后面所有下标左移一格。

    这条门 #275 在驱动侧有，序列侧一开始漏了（变异 M6 从这里钻过去）——
    而序列恰恰是**帮现场排查错位**的工具，自己错位就把人带沟里。
    变异：`if not t: continue`（丢位）→ 红。
    """

    def test_empty_element_keeps_position(self):
        bs = _FakeBs({"DL:THRoughput:OTA": "1000,,3.9e8,4.3e8,4.20e8,4.25e8"},
                     profile=_irat_profile())
        res = _run(bs)
        d = [s for s in res.steps if s.label.startswith("①")][0].detail
        assert "6 个元素" in d, "空元素被丢掉，个数少了一个"
        assert "average=idx4=420000000" in d, "下标左移，idx4 取到了错的元素"
        assert "[1]=<空>" in d, "空元素该显式标出来"


class TestPresentation:
    def test_raw_preserved_verbatim(self):
        """`protocol.py` 约定：raw **原样存**，不归一化 / 不去引号。"""
        weird = '  1000, 4.10e8 ,3.9e8,4.3e8,4.20e8,4.25e8  '
        bs = _FakeBs({"DL:THRoughput:OTA": weird}, profile=_irat_profile())
        res = _run(bs)
        dl = [s for s in res.steps if s.label.startswith("①")][0]
        assert dl.raw == weird, "raw 被动过 —— 它的价值就在保留仪器原样"

    def test_throughput_shows_both_unit_candidates(self):
        """单位 bps/Mbps 差 10⁶ —— 两个候选都要摆出来让人跟面板比。"""
        bs = _FakeBs({"DL:THRoughput:OTA": "1000,4.1e8,3.9e8,4.3e8,4.2e8,4.25e8"},
                     profile=_irat_profile())
        res = _run(bs)
        d = [s for s in res.steps if s.label.startswith("①")][0].detail
        assert "420" in d, "缺 bps→Mbps 的候选读数"
        # ⚠ 显示用 `.10g` 不是 `g` —— 6 位有效数字会把 420000000 显示成
        #   4.2e+08，跟面板逐位对不上（内审 F10）。断言的是**逐位可比的形式**。
        assert "420000000" in d, "缺'已是 Mbps'的候选读数（且必须逐位可比）"
        assert "4.2e+08" not in d, "又退回 6 位有效数字了"

    def test_cqi_shows_idx3_and_idx4_side_by_side(self):
        """取错一位会系统性乐观 —— max 与 average 必须并排。"""
        bs = _FakeBs({"CSI:CQI:STAT": "79200,1200,3,14,8.0,8"},
                     profile=_irat_profile())
        res = _run(bs)
        d = [s for s in res.steps if s.label.startswith("⑤")][0].detail
        assert "idx4(average)=8" in d
        assert "idx3(maximum)=14" in d

    def test_ri_shows_both_weightings(self):
        """bin 是码点还是层数，差一整个 rank —— 两种算法都要给。"""
        bs = _FakeBs({"CSI:RI:HIST": "0,30,70,0,0,0,0,0"}, profile=_irat_profile())
        res = _run(bs)
        d = [s for s in res.steps if s.label.startswith("⑥")][0].detail
        assert "2.70" in d, "缺'码点+1'算法的结果"
        assert "1.70" in d, "缺'bin 即 rank'算法的结果"

    def test_scpi_nan_flagged_not_treated_as_value(self):
        bs = _FakeBs({"DL:THRoughput:OTA": "0,9.91E+37,9.91E+37,9.91E+37,9.91E+37,0"},
                     profile=_irat_profile())
        res = _run(bs)
        d = [s for s in res.steps if s.label.startswith("①")][0].detail
        assert "NaN(9.91E+37)" in d

    def test_ue_report_states_the_156_rule(self):
        """RSRP 口径是本序列要定的核心问题之一 —— 判法必须写在步骤里，
        不能只留在 roadmap（现场看的是序列输出）。"""
        bs = _FakeBs({"MEASurement:JSON:REPort:FETCh": '{"a":1}'},
                     profile=_irat_profile())
        res = _run(bs)
        d = [s for s in res.steps if s.label.startswith("⑦")][0].detail
        # ⭐ 要的是**能照着做的判法**，不是出现过 156 这个数。
        #   变异 M12 删掉换算公式那句、只留"差 156 就是码点"，
        #   光断言 "156" in d 照样绿 —— 那种门只防"完全没写"。
        assert "rsrp-Result" in d, "缺 3GPP 字段名，现场不知道跟什么比"
        assert "− 156" in d or "- 156" in d, "缺换算公式"
        assert "相等就是 dBm" in d, "缺另一半判据（相等 → 已是工程量）"

    def test_summary_says_present_not_judge(self):
        bs = _FakeBs({}, profile=_irat_profile())
        res = _run(bs)
        assert "只呈现不判定" in res.summary
