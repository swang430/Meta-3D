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
        """个数不符是**最要紧的发现**，必须跑完并标注，不能当失败中止。

        ⚠ 必须把 `SYSTem:ERRor?` 也桩上 —— 探针的 success 现在取自错误队列
        （Codex #277 P1），不桩就成了"队列读不出来"那条路径，
        这门测的就不再是"个数不符"了。真仪器一定会回 `0,"No error"`。
        """
        bs = _FakeBs({"DL:THRoughput:OTA": "1,2,3",
                      "SYSTem:ERRor?": '0,"No error"'}, profile=_irat_profile())
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
        # ⚠ 必须桩 `SYSTem:ERRor?` —— 原值可不可信现在取自错误队列（内审 F1），
        #   不桩就成了"队列读不出来"→ 不写回，测的就不是本门要测的东西了。
        bs = _FakeBs({"BTHRoughput:STATe?": "0",
                      "MEASurement:REPort?": "0",
                      "SYSTem:ERRor?": '0,"No error"'}, profile=_irat_profile())
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
        bs = _FakeBs({"BTHRoughput:STATe?": "0",
                      "SYSTem:ERRor?": '0,"No error"'}, profile=_irat_profile(),
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


class _DirtyAfter(_FakeBs):
    """在指定命令之后，让**下一次**读错误队列吐一条错误。

    这才是真 SCPI 仪器的样子：命令被拒时 `_write` / `_query` 本身**不一定报错**
    （write 返回只代表传输成功），拒绝是从 `SYSTem:ERRor?` 回来的。
    `_FakeBs` 的 `raise_on` 造不出这种形态，所以 Codex #277 那两条 P1
    在原来的门下全绿。
    """

    def __init__(self, responses, *, dirty_after, err='-113,"Undefined header"',
                 nth=None, **kw):
        super().__init__(responses, **kw)
        self._dirty_after = dirty_after
        self._err = err
        # ⚠ `nth` 不是可有可无的花样（内审 F2）：同一条命令被发两次时
        #   （`CSI:STATe?` 一前一后夹着 `CSI:STARt`），不区分第几次就只能
        #   证明"某处接了错误队列"，**证明不了接的是自己那条** ——
        #   而"错误归属"恰恰是本 PR 的主语。把两条线接反照样全绿。
        self._nth = nth
        self._hits = 0
        self._pending: list[str] = []

    def _arm(self, cmd):
        # 先 arm 再交给 super —— super 可能抛异常（命令头不认识时读超时），
        # 而那正是最要紧的一格：**异常抛了，错误还留在队列里**。
        if self._dirty_after in cmd:
            self._hits += 1
            if self._nth is None or self._hits == self._nth:
                self._pending.append(self._err)

    def _query(self, cmd, **kw):
        if "SYSTem:ERRor" in cmd:
            self.queries.append(cmd)
            return self._pending.pop(0) if self._pending else '0,"No error"'
        self._arm(cmd)
        return super()._query(cmd, **kw)

    def _write(self, cmd, **kw):
        self._arm(cmd)
        return super()._write(cmd, **kw)


def _nested_source(name: str) -> str:
    """抠出 `run()` 里某个嵌套函数的源码 —— 不变量门要按**函数**数排空次数，
    按「行窗口」数会被『同一站点另一条路径排空了』蒙混过去（M24 实证）。"""
    import inspect

    lines = inspect.getsource(seq).splitlines()
    start = next(i for i, l in enumerate(lines)
                 if l.strip().startswith((f"async def {name}(", f"def {name}(")))
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
    return "\n".join(body)


class TestErrorAttributionBoundary:
    """⭐ Codex #277 P1：**每条命令的错误必须记在它自己名下**。

    不排空 → 错误漂到下一条命令头上 → 把**对的**命令记成"手册写法也不支持"，
    现场据此把它从驱动里删掉。这正是本文件 docstring 点名要防的病，
    内审 F3 只修了「跑前 *CLS」和「排空不是只 pop 一条」两处，
    **没扫命令与命令之间的边界**。
    """

    def test_speculative_state_query_error_does_not_condemn_the_ON_write(self):
        """`BTHRoughput:STATe?` 是**手册未说明**的投机形式，最可能被拒 →
        `-113` 留在队列 → 紧跟着**受支持**的 `... ON` 读到它、被报成"被拒"。
        变异：把 `_read_orig` 里的排空删掉 → 红。"""
        bs = _DirtyAfter({}, profile=_irat_profile(),
                         dirty_after="BTHRoughput:STATe?",
                         raise_on="BTHRoughput:STATe?")
        res = _run(bs)
        p0 = [s for s in res.steps if "读 BTHRoughput:STATe 原值" in s.label][0]
        p1 = [s for s in res.steps if s.label.startswith("P1")][0]
        assert "-113" in p0.detail, "错误没记在产生它的那条投机查询名下"
        assert "-113" not in p1.detail, (
            "投机查询的 -113 漂到了受支持的 `... ON` 头上")
        assert p1.success is True, (
            "`... ON` 没被拒却报成被拒 —— 现场会据此判定该命令不可用")

    def test_probe_error_does_not_drift_to_the_clear_step(self):
        """①-⑦ 任一条被拒，错误一路攒到 ⑧b，把 `CLEar` 记成"不支持"。
        变异：把 `_probe` 两条路径的排空删掉 → 红。"""
        bs = _DirtyAfter({"BTHRoughput:STATe?": "0"}, profile=_irat_profile(),
                         dirty_after="DL:BLER", raise_on="DL:BLER")
        res = _run(bs)
        bler = [s for s in res.steps if s.label.startswith("③")][0]
        clear = [s for s in res.steps if s.label.startswith("⑧b")][0]
        assert "-113" in bler.detail, "错误没记在产生它的那条查询名下"
        assert "-113" not in clear.detail, "错误漂到了 CLEar 头上"
        assert clear.success is True, "CLEar 没被拒却被记成被拒"

    def test_csi_state_readback_errors_are_kept_off_the_start_command(self):
        """`CSI:STATe?` 一前一后夹着 `CSI:STARt`：前一次不排空错误算到
        STARt 头上，后一次不排空则漂到 P3 的 `REPort ON` 头上。"""
        bs = _DirtyAfter({"BTHRoughput:STATe?": "0"}, profile=_irat_profile(),
                         dirty_after="CSI:STATe?", raise_on="CSI:STATe?")
        res = _run(bs)
        p2 = [s for s in res.steps if s.label.startswith("P2")][0]
        p3 = [s for s in res.steps if s.label.startswith("P3")][0]
        assert "-113" not in p3.detail, "回读的错误漂到了 P3 的 `REPort ON` 头上"
        assert p3.success is True
        # STARt 自己的队列干净 —— detail 要把三段分开记，不能糊成一坨
        assert "STARt 自己的" in p2.detail

    def test_probe_that_answers_but_queues_an_error_is_red(self):
        """⭐ 查询**回了值**、仪器却同时把它记进错误队列 —— 真机上会发生
        （设置冲突 -221、`-420 Query UNTERMINATED` 之类，照样吐数据）。
        这条读法不成立，必须报红；错误也不能漂到下一条探针。

        上面几条走的都是**查询抛异常**那条路径，覆盖不到这里 ——
        变异 M24（成功路径假装队列干净）就是从这个缝钻过去的。
        """
        bs = _DirtyAfter({"DL:BLER": "1,2,3,4,5,6,7,8,9,10"},
                         profile=_irat_profile(), dirty_after="DL:BLER")
        res = _run(bs)
        dl = [s for s in res.steps if s.label.startswith("③")][0]
        ul = [s for s in res.steps if s.label.startswith("④")][0]
        assert dl.success is False, "回了值但被记进错误队列，这条读法不成立"
        assert "-113" in dl.detail
        assert dl.raw == "1,2,3,4,5,6,7,8,9,10", "报红也必须照常呈现原始回复"
        assert ul.success is True and "-113" not in ul.detail, "错误漂到了下一条探针"

    def test_probe_drains_on_both_of_its_exits(self):
        """⭐ **不变量门（数量对等）** —— `_probe` 有两条出口（查询成功 /
        查询抛异常），**每条都要排空**。

        ⚠️ 这条是补 `test_every_command_site_drains_its_own_error_queue` 的洞：
        那条按「`await _q(` 往下 7 行内有没有 `_err()`」判，而 `_probe` 的
        异常路径那次排空正好落在窗口里 —— **成功路径丢了排空它照样绿**
        （M24 实证）。判定器长得像不变量门，实际强度只到"这个站点至少有
        一条路径排空过"。
        """
        body = _nested_source("_probe")
        n = body.count("await _err()")
        assert n == 2, (
            f"`_probe` 两条出口各要排空一次，实际 {n} 次 —— "
            "少一条时那条路径的错误会漂到下一条探针名下")

    def test_read_orig_drains_on_all_of_its_exits(self):
        """同上，`_read_orig` 三条出口（抛异常 / 回空串 / 读到值）——
        异常那条自己排，另两条共用 try 之后那一次，共 2 次。"""
        body = _nested_source("_read_orig")
        n = body.count("await _err()")
        assert n == 2, f"`_read_orig` 排空 {n} 次，应为 2"

    def test_dirty_queue_makes_the_original_value_untrusted_and_unwritten(self):
        """⭐ 内审 F1 —— 读**回了值**不等于这个值可信，而它是要**写回仪器**的。

        队列脏时若照写，可能把本来 ON 的悄悄关掉，且全程报绿 ——
        操作员不会再手动确认。同一个 docstring 上面就写着"读不到就不能猜一个
        值写回去"，拿不可信的值写回是同一件事的变体，而且更糟。
        变异：这条判据换回常量 True → 红。
        """
        bs = _DirtyAfter({"BTHRoughput:STATe?": "1"}, profile=_irat_profile(),
                         dirty_after="BTHRoughput:STATe?")
        res = _run(bs)
        p0 = [s for s in res.steps if "读 BTHRoughput:STATe 原值" in s.label][0]
        assert p0.success is False, "队列脏却把原值当真值用"
        assert "不可信" in p0.detail and "手动确认" in p0.detail
        assert p0.raw == "1", "报红也要照常呈现读到的值"
        # ⭐ 关键在生效端：**真的没写回**，不是只报了一句
        assert "BTHRoughput:STATe 1" not in " | ".join(bs.writes), (
            "拿不可信的值写回了仪器 —— 可能把本来 ON 的悄悄关掉")
        r = [s for s in res.steps
             if s.label.startswith("R 写回 BTHRoughput:STATe")][0]
        assert r.success is False and "没有写回" in r.detail

    def test_ue_report_that_answers_but_queues_an_error_is_red(self):
        """⑦ 是唯一手写的查询站点，母题 B 在这里也得有门（内审 F3）——
        上一版只有"抛异常"那条路径的门，success 换回常量 True 照样全绿。"""
        bs = _DirtyAfter({"JSON:REPort:FETCh": '{"rsrp": 60}'},
                         profile=_irat_profile(),
                         dirty_after="JSON:REPort:FETCh")
        rep = [s for s in _run(bs).steps if s.label.startswith("⑦")][0]
        assert rep.success is False, "回了值但被记进错误队列，这条读法不成立"
        assert rep.raw == '{"rsrp": 60}', "报红也要照常呈现原始 JSON"

    def test_clear_exception_error_does_not_drift_to_the_next_read(self):
        """⑧b 写 `CLEar` 抛异常那条路径不排空 → 错误漂到 ⑧c，
        把**对的** DL 吞吐量查询记成红（内审 F2）。"""
        bs = _DirtyAfter({"BTHRoughput:STATe?": "0"}, profile=_irat_profile(),
                         dirty_after="BTHRoughput:CLEar",
                         raise_on_write="BTHRoughput:CLEar")
        res = _run(bs)
        b = [s for s in res.steps if s.label.startswith("⑧b")][0]
        c = [s for s in res.steps if s.label.startswith("⑧c")][0]
        assert "-113" in b.detail, "CLEar 自己的错误没记在自己名下"
        assert "-113" not in c.detail, "漂到了 ⑧c，会把对的查询判成不支持"
        assert c.success is True

    def test_undrained_queue_is_announced_not_silently_truncated(self):
        """`_err()` 撞满 16 条上界 = 队列**没排空**，剩下的会漂到下一条命令
        名下 —— 必须说出来并判红，不能悄悄返回一串看着挺全的错误（内审 F5）。"""
        class _Flood(_FakeBs):
            def _query(self, cmd, **kw):
                if "SYSTem:ERRor?" in cmd:
                    return '-113,"Undefined header"'      # 永远吐，不见 No error
                return super()._query(cmd, **kw)

        res = _run(_Flood({}, profile=_irat_profile()))
        p1 = [s for s in res.steps if s.label.startswith("P1")][0]
        assert "队列未排空" in p1.detail, "撞上界了却不声张"
        assert p1.success is False

    def test_dirty_csi_state_read_never_triggers_a_stop(self):
        """⭐ Codex #277 R2 —— 队列脏时读回的 `STOP` **不可信**，
        照它发 `CSI:STOP` 会**打断本来就在跑的测量**。

        代价不对称：误当 STOP → 打断别人；误当"在跑" → 只是不关，
        而"不关"那条本序列已明写请手动 STOP。所以脏就按读不到处理。
        变异：去掉这条判据 → 红（会看到 CSI:STOP 被发出去）。
        """
        # `nth=1` = 只弄脏**开跑前**那次回读（err_pre）—— 不加它，两条线接反
        #   照样全绿（内审 F2）。真机上错误异步入队、晚到一拍是常态。
        bs = _DirtyAfter({"CSI:STATe?": "STOP", "BTHRoughput:STATe?": "0"},
                         profile=_irat_profile(), dirty_after="CSI:STATe?",
                         nth=1)
        res = _run(bs)
        assert not any("CSI:STOP" in w for w in bs.writes), (
            "拿脏队列下读到的 STOP 去关 CSI —— 可能打断别人正在跑的测量")
        r = [s for s in res.steps if s.label.startswith("R 关回 CSI")][0]
        # ⭐ 内审 F1：**证据不能删** —— 仪器答的是 STOP，记录里就得留着 STOP，
        #    不能因为"不可信"就写成 None（同文件 `_read_orig` 就是保住值的）。
        # ⚠ 断言必须钉在**被回显的那个 token** 上（`repr` 带引号）——
        #   写成 `"STOP" in r.detail` 是**恒真**的：detail 里还有"不敢发 STOP"、
        #   "请手动 STOP"，招牌断言被旁边的文字替着绿（变异 M42 实证）。
        assert repr("STOP") in r.detail, "把仪器真答过的 STOP 从记录里删掉了"
        assert "不可信" in r.detail
        # ⭐ 内审 F3：这一格里仪器很可能本来就是 STOP、被本序列开着走了，
        #    报绿会让下面那句"请手动 STOP"挂在 ✅ 上，没人会去做。
        assert r.success is False, "没关也不确定该不该关，却报绿"
        assert "手动 STOP" in r.detail

    def test_dirty_csi_readback_cannot_declare_start_effective(self):
        """回读自己的队列脏 = 这个 MEAS 不可信，不能据此宣布 `CSI:STARt` 生效
        —— 而"证明前置真生效"正是这一步存在的意义。"""
        # `nth=2` = 只弄脏**开跑后**那次回读（err_post）
        bs = _DirtyAfter({"CSI:STATe?": "MEAS", "BTHRoughput:STATe?": "0"},
                         profile=_irat_profile(), dirty_after="CSI:STATe?",
                         nth=2)
        p2 = [s for s in _run(bs).steps if s.label.startswith("P2")][0]
        assert p2.success is False, "回读不可信却宣布 STARt 生效了"
        # ⭐ 内审 F6：红了要给**对得上**的理由 —— 回读明明是 MEAS，
        #    却写"不是 MEAS/WAIT 才会被忽略"，现场拿不到"为什么红"。
        assert "回读自己的队列脏" in p2.detail
        assert "不是 MEAS/WAIT 就说明" not in p2.detail, (
            "回读是 MEAS 却说「不是 MEAS/WAIT」—— 解释当场自相矛盾")

    def test_csi_state_helper_drains_its_single_exit(self):
        body = _nested_source("_csi_state")
        n = body.count("await _err()")
        assert n == 1, f"`_csi_state` 唯一出口要排空一次，实际 {n} 次"

    def test_ue_report_query_failure_does_not_drift_to_the_next_step(self):
        """⑦ 是唯一**手写**的查询站点（不走 `_probe`），两条路径都得自己排空。
        它抛异常那条没门守时，错误会漂到 ⑧a 头上（变异 M32）。"""
        bs = _DirtyAfter({"BTHRoughput:STATe?": "0"}, profile=_irat_profile(),
                         dirty_after="JSON:REPort:FETCh",
                         raise_on="JSON:REPort:FETCh")
        res = _run(bs)
        rep = [s for s in res.steps if s.label.startswith("⑦")][0]
        nxt = [s for s in res.steps if s.label.startswith("⑧a")][0]
        assert "-113" in rep.detail, "错误没记在 ⑦ 自己名下"
        assert "-113" not in nxt.detail, "⑦ 的错误漂到了 ⑧a 头上"
        assert nxt.success is True

    def test_every_command_site_drains_its_own_error_queue(self):
        """⭐ **不变量门** —— 从代码派生的恒成立关系，防「新站点漏做」。

        上面三条是行为门，只钉住今天存在的那几条命令；这条钉住的是
        「以后再加一条 `_q` / `_w` 也得排空」。Codex 这两条 P1 就是
        新站点漏做的形态 —— 母题早在内审 F3 修过，只是没扫到别的站点。
        """
        import inspect
        import re as _re

        lines = inspect.getsource(seq).splitlines()
        offenders = []
        for i, line in enumerate(lines):
            if not _re.search(r"await _q\(|await _w\(", line):
                continue
            if "SYSTem:ERRor" in line:          # `_err` 自己那条，排除
                continue
            if "await _err()" not in "\n".join(lines[i:i + 7]):
                offenders.append((i + 1, line.strip()))
        assert not offenders, (
            "这些命令站点发完没排空错误队列，错误会漂到下一条命令名下:\n"
            + "\n".join(f"  L{n} {s}" for n, s in offenders))


class TestWriteAcceptanceIsVerified:
    """⭐ Codex #277 P1：SCPI 里 `_write` 返回**只代表传输成功**。

    命令被不被接受是从 `SYSTem:ERRor?` 回来的 —— 步骤 success 写死 True
    就等于替仪器宣布"接受了"。内审 F4 修了 P1/P3 两处，
    **恢复段的两处镜像我没扫到**，报"已恢复"而实际没恢复比不恢复更糟：
    操作员不会再去手动确认，累积开着直接污染下一次测试。
    """

    # (弄脏哪条写命令, 该由哪一步背, 需要的额外回值)
    # ⚠ `*CLS` **必须在表里**（内审 F4）—— 上一版把它从不变量门里排除掉，
    #   而它恰好就是唯一没人验证接受与否的那条写命令：洞正开在缺口上。
    _WRITES = [
        ("*CLS", "P0 清空错误队列", {}),
        ("BTHRoughput:STATe ON", "P1", {}),
        ("CSI:STARt", "P2", {"CSI:STATe?": "MEAS"}),
        ("MEASurement:REPort ON", "P3", {}),
        ("BTHRoughput:CLEar", "⑧b", {}),
        ("BTHRoughput:STATe 0", "R 写回 BTHRoughput:STATe",
         {"BTHRoughput:STATe?": "0"}),
        ("MEASurement:REPort 0", "R 写回 MEASurement:REPort",
         {"MEASurement:REPort?": "0"}),
        ("CSI:STOP", "R 关回 CSI 累积", {"CSI:STATe?": "STOP"}),
    ]

    @pytest.mark.parametrize("frag,prefix,extra", _WRITES,
                             ids=[w[1] for w in _WRITES])
    def test_rejected_write_is_reported_red(self, frag, prefix, extra):
        bs = _DirtyAfter(dict(extra), profile=_irat_profile(), dirty_after=frag)
        res = _run(bs)
        step = [s for s in res.steps if s.label.startswith(prefix)][0]
        assert step.success is False, (
            f"`{frag}` 被仪器拒了，`{prefix}` 却报成功 —— "
            "write 返回只代表传输成功")
        assert "-113" in step.detail, "拒绝理由没进 detail，操作员看不到"

    def test_failed_restore_tells_the_operator_to_fix_it_by_hand(self):
        """报红还不够 —— 累积被留在 ON 会污染**下一次**测试，
        必须明说要手动关。变异：去掉这句提示 → 红。"""
        bs = _DirtyAfter({"BTHRoughput:STATe?": "0"}, profile=_irat_profile(),
                         dirty_after="BTHRoughput:STATe 0")
        res = _run(bs)
        r = [s for s in res.steps
             if s.label.startswith("R 写回 BTHRoughput:STATe")][0]
        assert "手动" in r.detail and "污染" in r.detail
        assert res.success is False, "恢复没生效，整轮却报 success=True"

    def test_write_count_matches_the_number_of_verifiable_steps(self):
        """⭐ **不变量门（数量对等）** —— 序列发出去的写命令，每一条都必须
        有一步能因它被拒而变红。少一条 = 那条命令的接受与否无人验证。"""
        # ⚠ 必须桩错误队列（内审 F5）—— 不桩则三条恢复写命令根本不发出去，
        #   这道"每条写命令都要有人验"的门只能看到 5/8 个站点，
        #   以后在恢复段加写命令它看不见。
        bs = _FakeBs({"BTHRoughput:STATe?": "0", "MEASurement:REPort?": "0",
                      "CSI:STATe?": "STOP", "SYSTem:ERRor?": '0,"No error"'},
                     profile=_irat_profile())
        _run(bs)
        assert len(bs.writes) >= 8, (
            f"夹具只走到 {len(bs.writes)} 条写命令，覆盖不到申报的 "
            f"{len(self._WRITES)} 个站点：{bs.writes}")
        covered = {frag for frag, _, _ in self._WRITES}
        uncovered = [w for w in bs.writes
                     if not any(f in w for f in covered)]
        assert not uncovered, (
            f"这些写命令没有任何一步验证它被没被接受: {uncovered}")

    def test_cls_failure_is_not_reported_as_a_clean_sweep(self):
        """`*CLS` 没发出去时，此后所有错误归属都不可信 —— 记录必须说出来，
        不能写"已发 `*CLS` 并排空"还报绿（内审 F4）。"""
        bs = _FakeBs({}, profile=_irat_profile(), raise_on_write="*CLS")
        res = _run(bs)
        p0 = [s for s in res.steps if s.label.startswith("P0 清空")][0]
        assert p0.success is False
        assert "没发出去" in p0.detail and "不可信" in p0.detail


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
        # ⭐ 反向配对上面那条"判不了必须红"（内审 F6）—— 少了这句，
        #   那条门用一个恒红的实现就能糊过去，而恒红不算门。
        assert v.success is True, "真判出来了却报红"

    def test_verdict_step_is_red_when_it_could_not_decide(self):
        """⭐ 内审 F6 —— verdict 自己写着"本次无法判定"，步骤却报绿、
        summary 还说"无失败步"。一个自称判不了的结论不能算通过。"""
        bs = _FakeBs({"DL:THRoughput:OTA": "0,0,0,0,0,0",
                      "SYSTem:ERRor?": '0,"No error"'}, profile=_irat_profile())
        res = _run(bs)
        v = [s for s in res.steps if s.label.startswith("⑧ CLEar")][0]
        assert "无法判定" in v.detail
        assert v.success is False, "自称无法判定却报绿"

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
        # ⚠ 必须桩 `SYSTem:ERRor?` —— 这个 STOP 可不可信现在取自它自己的错误
        #   队列（Codex #277 R2），不桩就走进"读不到"分支，测的就不是本门的事了。
        bs = _FakeBs({"CSI:STATe?": "STOP", "SYSTem:ERRor?": '0,"No error"'},
                     profile=_irat_profile())
        _run(bs)
        assert any("CSI:STOP" in w for w in bs.writes)

    def test_does_not_stop_when_already_running(self):
        # ⚠ 跟上面那条一起补桩（内审 F4）—— 只补一条时本门走的是
        #   "队列读不出来→按读不到处理"分支，**根本到不了"已在跑所以不关"**，
        #   任何回读值都绿（实测 STOP/MEAS/空串全绿）= 恒真门。
        bs = _FakeBs({"CSI:STATe?": "MEAS", "SYSTem:ERRor?": '0,"No error"'},
                     profile=_irat_profile())
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
