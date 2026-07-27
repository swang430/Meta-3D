"""P1-19: UXM set_cell_config 编排正修的行为锁定。

2026-07-03 CAICT 现场实证驱动的五组行为:
  ① "键在但值 None" 视同缺失 (band=None 曾致 .upper() 崩, ARFCN 不下发);
  ② 小区 ACTive 时禁改带宽 (-221) → ON 态改 BW 走 OFF→配→ON 环绕;
  ③ IRAT 带宽值令牌形式 "BW100" + TDD 下 UL:BW 跟随 DL 跳过单独下发;
  ④ SSB/PointA 基线自动补 (目标 ARFCN 命中 EMQuest 基线才补, 严格合拍);
  ⑤ 写后回读对账 fail-loud (IRAT 默认开; 老 5G App 查询不支持默认关)。
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.hal.uxm_base_station import RealUxmDriver


@pytest.fixture
def driver_irat():
    return RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})


@pytest.fixture
def driver_5g():
    return RealUxmDriver("uxm-5g", {"ip": "10.0.0.1"})


def wire_echo_visa(driver, cell_active: bool = False, overrides: dict | None = None):
    """回显式 fake visa session: 配置查询回显最近一次对应写入的值。

    - ``*OPC?`` → "1"; ``...ACTive:STATe?`` → cell_active 初值 (写入 STATe 后跟随);
    - 其他 ``X?`` → 找最近一次 ``X <value>`` 写入回显 value, 没有则 "0";
    - overrides: {查询子串: 固定响应} 用于注入回读不一致。
    """
    sess = MagicMock()
    written: list[str] = []
    state = {"active": "1" if cell_active else "0"}

    def _write(cmd):
        written.append(cmd.strip())
        c = cmd.strip()
        if c.endswith("ACTive:STATe 1"):
            state["active"] = "1"
        elif c.endswith("ACTive:STATe 0"):
            state["active"] = "0"

    def _query(cmd, **_kw):
        c = cmd.strip()
        for frag, resp in (overrides or {}).items():
            if frag in c:
                return resp
        if c == "*OPC?":
            return "1"
        if c.endswith("ACTive:STATe?"):
            return state["active"]
        # P0-2 D3 二层闸: APPLY 后驱动会查协议栈状态 (BSE:STATus:NR5G:...?),
        # OFF/读不到会被如实判失败。fake 按真机健康形态回: 开关 ON → 协议栈
        # ON, 开关 OFF → OFF (跟随 state, 与 R2 "两者独立"的故障形态相反 —
        # 故障形态由 test_p02 的专门用例覆盖, 这里的测试对象是编排不是闸)。
        if c.startswith("BSE:STATus:NR5G"):
            return "ON" if state["active"] == "1" else "OFF"
        base = c.rstrip("?")
        for w in reversed(written):
            if w.startswith(base + " "):
                return w[len(base) + 1:]
        return "0"

    sess.write = MagicMock(side_effect=_write)
    sess.query = MagicMock(side_effect=_query)
    sess.timeout = 5000
    driver._visa_session = sess
    return sess, written


class TestNoneValueTolerance:
    @pytest.mark.asyncio
    async def test_band_none_falls_back_to_inference(self, driver_irat):
        """今日根因回归: band=None 不再 .upper() 崩, 走频率推断且 ARFCN 下发。"""
        _, written = wire_echo_visa(driver_irat)
        ok = await driver_irat.set_cell_config({
            "band": None,           # 显式 None — 曾致整个 set_cell_config 中止
            "duplex": None,
            "frequency_mhz": 3500.0,
            "bandwidth_mhz": 100,
        })
        assert ok is True
        assert any("DL:ARFCN" in w for w in written), written
        # 推断出的 band 真下发了 (3500 → N78)
        assert any("BAND N78" in w for w in written), written

    @pytest.mark.asyncio
    async def test_caller_config_not_mutated(self, driver_irat):
        wire_echo_visa(driver_irat)
        cfg = {"band": None, "frequency_mhz": 3500.0}
        await driver_irat.set_cell_config(cfg)
        assert cfg == {"band": None, "frequency_mhz": 3500.0}  # copy 语义


class TestBwTokenAndTddUlSkip:
    @pytest.mark.asyncio
    async def test_irat_tdd_bw_token_and_no_ul_bw(self, driver_irat):
        _, written = wire_echo_visa(driver_irat)
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 100, "duplex": "TDD",
        })
        assert ok is True
        assert any(w.endswith("DL:BW BW100") for w in written), written
        assert not any("UL:BW" in w for w in written), written  # TDD 跟随, 不单发

    @pytest.mark.asyncio
    async def test_irat_fdd_band_writes_ul_bw(self, driver_irat):
        _, written = wire_echo_visa(driver_irat)
        ok = await driver_irat.set_cell_config({
            "band": "N3", "arfcn": 368500, "bandwidth_mhz": 40, "duplex": "FDD",
        })
        assert ok is True
        assert any(w.endswith("UL:BW BW40") for w in written), written

    @pytest.mark.asyncio
    async def test_irat_tdd_inferred_from_band_baseline(self, driver_irat):
        """不显式给 duplex, 由 band 基线表 (N78=TDD) 推断跳 UL:BW。"""
        _, written = wire_echo_visa(driver_irat)
        ok = await driver_irat.set_cell_config({"band": "N78", "bandwidth_mhz": 100})
        assert ok is True
        assert not any("UL:BW" in w for w in written), written

    @pytest.mark.asyncio
    async def test_stale_tdd_duplex_not_reused_across_bands(self, driver_irat):
        """Codex #195 R3 P2: 前一调用的 TDD 缓存不得让换 band 后的未知 band 漏写 UL:BW。"""
        _, written = wire_echo_visa(driver_irat)
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 100, "duplex": "TDD",
        })
        assert ok is True
        written.clear()
        # N999 不在基线表且无显式 duplex → 全未知, 保守写 UL:BW (不复用 N78 的 TDD)
        ok = await driver_irat.set_cell_config({"band": "N999", "bandwidth_mhz": 40})
        assert ok is True
        assert any(w.endswith("UL:BW BW40") for w in written), written

    @pytest.mark.asyncio
    async def test_cached_duplex_still_reused_for_same_band(self, driver_irat):
        """同一 band 只改带宽时, 驱动状态级缓存仍生效 (TDD 继续跳 UL:BW)。"""
        _, written = wire_echo_visa(driver_irat)
        # N901 不在基线表 → 后续调用只能靠驱动状态级判定
        ok = await driver_irat.set_cell_config({
            "band": "N901", "bandwidth_mhz": 100, "duplex": "TDD",
        })
        assert ok is True
        written.clear()
        ok = await driver_irat.set_cell_config({"band": "N901", "bandwidth_mhz": 40})
        assert ok is True
        assert any(w.endswith("DL:BW BW40") for w in written), written
        assert not any("UL:BW" in w for w in written), written

    @pytest.mark.asyncio
    async def test_inferred_tdd_does_not_suppress_fdd_baseline(self, driver_irat):
        """Codex #202 R3: N3 DL 1842.5 不在推断 map (只录了 UL 段) → fallback
        填 TDD — 不得压制 FDD 基线表, UL:BW 必须照写。"""
        _, written = wire_echo_visa(driver_irat)
        ok = await driver_irat.set_cell_config({
            "band": "N3", "frequency_mhz": 1842.5, "arfcn": 368500,
            "bandwidth_mhz": 40,
        })
        assert ok is True
        assert any(w.endswith("UL:BW BW40") for w in written), written

    @pytest.mark.asyncio
    async def test_duplex_write_and_ulbw_decision_same_source(self, driver_5g):
        """Codex #204: 源头收敛 — DUPLex 写与 UL:BW 判定同源, N3 推断场景
        下发 DUPLex FDD (不再是矛盾的 TDD 写 + FDD 带宽行为)。"""
        _, written = wire_echo_visa(driver_5g)
        ok = await driver_5g.set_cell_config({
            "band": "N3", "frequency_mhz": 1842.5, "arfcn": 368500,
            "bandwidth_mhz": 40,
        })
        assert ok is True
        assert any(w.endswith("DUPLex FDD") for w in written), written
        assert not any(w.endswith("DUPLex TDD") for w in written), written

    @pytest.mark.asyncio
    async def test_null_duplex_without_frequency_converges_from_baseline(self, driver_5g):
        """Codex #202 R4: duplex=null 且无 frequency_mhz — 收敛不得只挂在频率
        推断分支下, band 基线要照样补 (否则 DUPLex 不下发, 仪器停留上个
        setup 的残留 TDD, 而 UL:BW 判定按 FDD, 判定与仪器实际不同源)。"""
        _, written = wire_echo_visa(driver_5g)
        ok = await driver_5g.set_cell_config({
            "band": "N3", "duplex": None, "bandwidth_mhz": 40,
        })
        assert ok is True
        assert any(w.endswith("DUPLex FDD") for w in written), written

    @pytest.mark.asyncio
    async def test_null_duplex_without_frequency_irat_writes_ulbw(self, driver_irat):
        """同场景 IRAT 侧: 判定按收敛后 FDD 写 UL:BW。"""
        _, written = wire_echo_visa(driver_irat)
        ok = await driver_irat.set_cell_config({
            "band": "N3", "duplex": None, "arfcn": 368500, "bandwidth_mhz": 40,
        })
        assert ok is True
        assert any(w.endswith("UL:BW BW40") for w in written), written

    @pytest.mark.asyncio
    async def test_explicit_user_duplex_still_first(self, driver_irat):
        """用户显式 duplex 仍是第一优先级 (高于基线表)。"""
        _, written = wire_echo_visa(driver_irat)
        # N3 基线是 FDD, 用户显式 TDD (非常规但显式即王) → 跳 UL:BW
        ok = await driver_irat.set_cell_config({
            "band": "N3", "arfcn": 368500, "bandwidth_mhz": 40, "duplex": "TDD",
        })
        assert ok is True
        assert not any("UL:BW" in w for w in written), written

    @pytest.mark.asyncio
    async def test_5g_profile_keeps_raw_bw_value(self, driver_5g):
        _, written = wire_echo_visa(driver_5g)
        ok = await driver_5g.set_cell_config({
            "band": "N78", "bandwidth_mhz": 100, "duplex": "TDD",
        })
        assert ok is True
        assert any(w.endswith("DL:BW 100") for w in written), written


class TestCellOnOffOrchestration:
    @pytest.mark.asyncio
    async def test_active_cell_bw_change_wraps_off_then_on(self, driver_irat):
        _, written = wire_echo_visa(driver_irat, cell_active=True)
        ok = await driver_irat.set_cell_config({"band": "N78", "bandwidth_mhz": 100})
        assert ok is True
        off_idx = next(i for i, w in enumerate(written) if w.endswith("ACTive:STATe 0"))
        bw_idx = next(i for i, w in enumerate(written) if "DL:BW" in w)
        on_idx = next(i for i, w in enumerate(written) if w.endswith("ACTive:STATe 1"))
        assert off_idx < bw_idx < on_idx, written  # OFF → 配 → ON 恢复原态

    @pytest.mark.asyncio
    async def test_inactive_cell_no_state_wrapping(self, driver_irat):
        _, written = wire_echo_visa(driver_irat, cell_active=False)
        ok = await driver_irat.set_cell_config({"band": "N78", "bandwidth_mhz": 100})
        assert ok is True
        assert not any("ACTive:STATe 0" in w or w.endswith("ACTive:STATe 1")
                       for w in written), written

    @pytest.mark.asyncio
    async def test_no_bw_change_no_state_wrap(self, driver_irat):
        """无 BW 改动 → 不做 OFF→ON 环绕 (DUT 不掉线)。

        P0-2 D2 后断言改钉**真实后果** (没有 ACTive:STATe 0/1 写入), 不再钉
        "零次开关探测"这个代理量 — 批次收尾的 APPLY 决策现在合法地探一次开关
        (只读, 不影响 DUT), 旧断言会把它误伤。"""
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        ok = await driver_irat.set_cell_config({"band": "N78", "arfcn": 636666})
        assert ok is True
        assert not any(
            "ACTive:STATe 0" in w or w.endswith("ACTive:STATe 1")
            for w in written
        ), written


class TestBwIdempotentSkip:
    """出发前 2026-07-20: BW 同值免重启 — 当前 BW 已等于目标值且载波身份
    未变 (Codex #214 P2) 则免 BW 写免 OFF→ON 环绕。

    动机: measure 的 cell_cfg 必带 bandwidth_mhz, 无此检查则小区 ON 时每次
    run 都 OFF→配→ON 重启, 已 attach 的 DUT 必掉线一次。
    """

    async def _warm_carrier(self, driver, written, band="N78", arfcn=636666,
                            bw=40, duplex=None):
        """预热载波记录 (Codex #214 P2: 捷径要求 band/ARFCN 与上次下发一致;
        记录冷 = 重载后首跑, 保守走环绕)。预热调用自身走环绕 (记录冷)。
        返回预热结束时 written 的长度 — 断言段用 written[idx:] 只看目标调用
        的 wire 行为 (不能 clear: written 同时是回显 fake 的数据源, 清了
        预读就读不到预热写入的 BW)。"""
        cfg = {"band": band, "arfcn": arfcn, "bandwidth_mhz": bw}
        if duplex:
            cfg["duplex"] = duplex
        assert await driver.set_cell_config(cfg) is True
        return len(written)

    @pytest.mark.asyncio
    async def test_same_bw_same_carrier_skips_wrap_and_write(self, driver_irat):
        """当前 BW40 == 目标 40 且载波未变 → 不 OFF/ON、不写 BW, 其余照发。"""
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        idx = await self._warm_carrier(driver_irat, written)  # 回显此后回 BW40
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 40, "arfcn": 636666,
        })
        assert ok is True
        tail = written[idx:]
        # 小区没被环绕重启 (DUT 不掉线的可观测契约)
        assert not any("ACTive:STATe 0" in w or w.endswith("ACTive:STATe 1")
                       for w in tail), tail
        # BW 写被剔除, 但 ARFCN 等其余参数照发
        assert not any("DL:BW BW40" in w for w in tail), tail
        assert any("DL:ARFCN 636666" in w for w in tail), tail
        # 写分支被跳过时缓存仍对齐 (状态一致性)
        assert driver_irat._bandwidth_mhz == 40

    @pytest.mark.asyncio
    async def test_cold_carrier_record_no_shortcut(self, driver_irat):
        """载波记录冷 (重载后首跑, _band=None) → 即使 BW 相同也保守走环绕。"""
        _, written = wire_echo_visa(
            driver_irat, cell_active=True, overrides={"DL:BW?": "BW40"}
        )
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 40, "arfcn": 636666,
        })
        assert ok is True
        assert any(w.endswith("ACTive:STATe 0") for w in written), written
        assert any("DL:BW BW40" in w for w in written), written

    @pytest.mark.asyncio
    async def test_carrier_change_same_bw_still_wraps(self, driver_irat):
        """Codex #214 P2: 同 BW 但换载波 (N78/636666 → N41/518598, 都 TDD
        BW40) → 不走捷径, 环绕 + BW 写照常 (换 band 可能复位 BW, 必须重写)。"""
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        idx = await self._warm_carrier(driver_irat, written)
        ok = await driver_irat.set_cell_config({
            "band": "N41", "bandwidth_mhz": 40, "arfcn": 518598,
        })
        assert ok is True
        tail = written[idx:]
        assert any(w.endswith("ACTive:STATe 0") for w in tail), tail
        assert any("DL:BW BW40" in w for w in tail), tail
        assert any("DL:ARFCN 518598" in w for w in tail), tail

    @pytest.mark.asyncio
    async def test_different_bw_still_wraps(self, driver_irat):
        """载波未变但 BW40 → 100 → 原 OFF→配→ON 环绕路径不变。"""
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        idx = await self._warm_carrier(driver_irat, written)  # 回显此后回 BW40
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 100, "arfcn": 636666,
        })
        assert ok is True
        tail = written[idx:]
        off_idx = next(i for i, w in enumerate(tail) if w.endswith("ACTive:STATe 0"))
        bw_idx = next(i for i, w in enumerate(tail) if "DL:BW BW100" in w)
        on_idx = next(i for i, w in enumerate(tail) if w.endswith("ACTive:STATe 1"))
        assert off_idx < bw_idx < on_idx, tail

    @pytest.mark.asyncio
    async def test_unparseable_preread_conservative_wrap(self, driver_irat):
        """载波已热但预读回不可解析文本 → 保守走原环绕路径 (不猜)。

        仅首次 (预读) 回 garbage, 写后回读对账走正常回显 — 隔离测预读自身
        的容错, 不连带触发 P1-19 对账 fail-loud。"""
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        idx = await self._warm_carrier(driver_irat, written)
        orig = sess.query.side_effect
        hits = {"n": 0}

        def _garbage_first_bw_query(cmd):
            if "DL:BW?" in cmd:
                hits["n"] += 1
                if hits["n"] == 1:
                    return "garbage"
            return orig(cmd)

        sess.query.side_effect = _garbage_first_bw_query
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 40, "arfcn": 636666,
        })
        assert ok is True
        tail = written[idx:]
        assert any(w.endswith("ACTive:STATe 0") for w in tail), tail
        assert any("DL:BW BW40" in w for w in tail), tail

    @pytest.mark.asyncio
    async def test_empty_preread_conservative_wrap(self, driver_irat):
        """载波已热但预读回空响应 → 保守走原环绕路径。"""
        sess, written = wire_echo_visa(
            driver_irat, cell_active=True, overrides={"DL:BW?": ""}
        )
        idx = await self._warm_carrier(driver_irat, written)  # 预热预读也回空→环绕, ok
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 40, "arfcn": 636666,
        })
        assert ok is True
        tail = written[idx:]
        assert any(w.endswith("ACTive:STATe 0") for w in tail), tail
        assert any("DL:BW BW40" in w for w in tail), tail

    @pytest.mark.asyncio
    async def test_preread_exception_conservative_wrap(self, driver_irat):
        """载波已热但预读抛异常 → 吞掉走原环绕路径, 不向 caller 裸抛。"""
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        idx = await self._warm_carrier(driver_irat, written)
        orig = sess.query.side_effect

        def _boom_on_bw_query(cmd):
            if "DL:BW?" in cmd:
                raise TimeoutError("preread timeout")
            return orig(cmd)

        sess.query.side_effect = _boom_on_bw_query
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 40, "arfcn": 636666,
        })
        assert ok is True
        tail = written[idx:]
        assert any(w.endswith("ACTive:STATe 0") for w in tail), tail
        assert any("DL:BW BW40" in w for w in tail), tail

    @pytest.mark.asyncio
    async def test_readback_gate_off_skips_preread(self, driver_irat):
        """门审 F1: readback_verify=False (等价 5G profile 无查询能力) →
        完全不发预读查询, 直接走原环绕路径 (不白等实证会超时的查询)。"""
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        idx = await self._warm_carrier(driver_irat, written)
        sess.query.reset_mock()  # 只统计目标调用的查询
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 40, "arfcn": 636666,
            "readback_verify": False,
        })
        assert ok is True
        queried = [c.args[0] for c in sess.query.call_args_list]
        assert not any("DL:BW?" in q for q in queried), queried  # 预读没发
        tail = written[idx:]
        assert any(w.endswith("ACTive:STATe 0") for w in tail), tail
        assert any("DL:BW BW40" in w for w in tail), tail

    @pytest.mark.asyncio
    async def test_fdd_band_never_takes_idempotent_shortcut(self, driver_irat):
        """门审 F3: FDD band 不走捷径 (剔键会连 UL:BW 写一起跳过, 预读只验
        DL, 判定与下发不同源) — 载波已热 + BW 相同也照走 OFF→配→ON,
        DL+UL 都写。"""
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        idx = await self._warm_carrier(
            driver_irat, written, band="N3", arfcn=368500, duplex="FDD"
        )
        ok = await driver_irat.set_cell_config({
            "band": "N3", "arfcn": 368500, "bandwidth_mhz": 40, "duplex": "FDD",
        })
        assert ok is True
        tail = written[idx:]
        # 关键契约: 捷径没走 (环绕 + DL/UL 写都发生)
        assert any(w.endswith("ACTive:STATe 0") for w in tail), tail
        assert any("DL:BW BW40" in w for w in tail), tail
        assert any("UL:BW BW40" in w for w in tail), tail


class TestSsbBaselineAutofill:
    @pytest.mark.asyncio
    async def test_5g_profile_autofills_ssb_on_baseline_hit(self, driver_5g):
        """目标 ARFCN 命中 N78 EMQuest 基线 (636666) → 自动补 SSB/PointA。"""
        _, written = wire_echo_visa(driver_5g)
        ok = await driver_5g.set_cell_config({
            "band": "N78", "arfcn": 636666, "bandwidth_mhz": 100, "duplex": "TDD",
        })
        assert ok is True
        assert any("SSB:NCD:ARFCn 635712" in w for w in written), written
        assert any("DL:POINta 632946" in w for w in written), written

    @pytest.mark.asyncio
    async def test_no_autofill_when_arfcn_off_baseline(self, driver_5g):
        """自定义频率 (640000 ≠ 基线 636666) 不乱补 — SSB 是 GSCN 栅格产物。"""
        _, written = wire_echo_visa(driver_5g)
        ok = await driver_5g.set_cell_config({
            "band": "N78", "arfcn": 640000, "bandwidth_mhz": 100, "duplex": "TDD",
        })
        assert ok is True
        assert not any("SSB:NCD" in w or "POINta" in w for w in written), written

    @pytest.mark.asyncio
    async def test_irat_autofill_skips_gracefully(self, driver_irat):
        """IRAT 的 SSB_ARFCN/CELL_DL_POINTA=None (-113 探明) → 命中基线也只跳过。"""
        _, written = wire_echo_visa(driver_irat)
        ok = await driver_irat.set_cell_config({
            "band": "N78", "arfcn": 636666, "bandwidth_mhz": 100,
        })
        assert ok is True
        assert not any("SSB" in w or "POINta" in w for w in written), written

    @pytest.mark.asyncio
    async def test_explicit_ssb_overrides_autofill(self, driver_5g):
        _, written = wire_echo_visa(driver_5g)
        ok = await driver_5g.set_cell_config({
            "band": "N78", "arfcn": 636666, "ssb_arfcn": 635808,
        })
        assert ok is True
        assert any("SSB:NCD:ARFCn 635808" in w for w in written), written
        assert not any("635712" in w for w in written), written


class TestReadbackVerify:
    @pytest.mark.asyncio
    async def test_irat_readback_mismatch_fails_loud(self, driver_irat):
        """回读 ARFCN 与下发不一致 (echo≠生效的真形态) → False + 不静默。"""
        wire_echo_visa(driver_irat, overrides={"DL:ARFCN?": "636666"})
        ok = await driver_irat.set_cell_config({
            "band": "N78", "arfcn": 640000, "bandwidth_mhz": 100,
        })
        assert ok is False

    @pytest.mark.asyncio
    async def test_irat_readback_consistent_passes(self, driver_irat):
        wire_echo_visa(driver_irat)  # 回显式: 回读=下发
        ok = await driver_irat.set_cell_config({
            "band": "N78", "arfcn": 636666, "bandwidth_mhz": 100,
            "dl_power_dbm": -46.0,
        })
        assert ok is True

    @pytest.mark.asyncio
    async def test_explicit_off_switch_skips_readback(self, driver_irat):
        sess, _ = wire_echo_visa(driver_irat, overrides={"DL:ARFCN?": "999999"})
        ok = await driver_irat.set_cell_config({
            "band": "N78", "arfcn": 636666, "readback_verify": False,
        })
        assert ok is True  # 显式关闭 → 即使回读值错也不拦 (bring-up 逃生口)

    @pytest.mark.asyncio
    async def test_5g_profile_readback_off_by_default(self, driver_5g):
        """老 App 配置查询不支持 (2026-05-27 实证) → 默认不回读不误伤。"""
        sess, _ = wire_echo_visa(driver_5g, overrides={"DL:ARFCN?": "999999"})
        ok = await driver_5g.set_cell_config({"band": "N78", "arfcn": 636666})
        assert ok is True
        queried = [c.args[0] for c in sess.query.call_args_list]
        assert not any("ARFCN?" in q for q in queried), queried


class TestCellRestoreOnFailurePath:
    """Codex #195 P1: OFF 之后的失败路径必须恢复原本 ON 的小区。"""

    @pytest.mark.asyncio
    async def test_write_exception_after_off_still_restores_on(self, driver_irat):
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        orig_side_effect = sess.write.side_effect

        def _boom_on_arfcn(cmd):
            orig_side_effect(cmd)
            if "DL:ARFCN" in cmd:
                raise RuntimeError("simulated VISA write failure")

        sess.write.side_effect = _boom_on_arfcn
        ok = await driver_irat.set_cell_config({"band": "N78", "bandwidth_mhz": 100})
        assert ok is False
        off_idx = next(i for i, w in enumerate(written) if w.endswith("ACTive:STATe 0"))
        on_idx = next(i for i, w in enumerate(written) if w.endswith("ACTive:STATe 1"))
        assert off_idx < on_idx, written  # finally 路径把小区恢复了

    @pytest.mark.asyncio
    async def test_readback_failure_after_off_still_restores_on(self, driver_irat):
        _, written = wire_echo_visa(
            driver_irat, cell_active=True, overrides={"DL:ARFCN?": "111111"})
        ok = await driver_irat.set_cell_config({
            "band": "N78", "arfcn": 636666, "bandwidth_mhz": 100,
        })
        assert ok is False  # 回读不一致 fail-loud
        assert any(w.endswith("ACTive:STATe 1") for w in written), written


class TestInst0Redirect:
    """Codex #195 P2: 显式绑定 inst0::INSTR (平台端点误配) 也应重定向 hislip2。"""

    @pytest.mark.asyncio
    async def test_explicit_inst0_binding_redirects_to_framework(self, monkeypatch):
        d = RealUxmDriver("uxm-inst0", {
            "ip": "10.0.0.9",
            "visa_resource": "TCPIP0::10.0.0.9::inst0::INSTR",
        })
        opened: list[str] = []

        def _make_session(resource):
            sess = MagicMock()
            sess.timeout = 5000
            if "inst0" in resource:
                sess.query = MagicMock(side_effect=lambda c: {
                    "*IDN?": "Keysight Technologies,E7515B Platform,MY123,1.0",
                }.get(c.strip(), "0"))
            else:
                sess.query = MagicMock(side_effect=lambda c: {
                    "*IDN?": "Keysight Technologies,E7515B TAF,MY123,1.0",
                    "SYSTem:APPLication:NAME?": "LTE_NR_IRAT",
                    "*OPC?": "1",
                }.get(c.strip(), "0"))
            sess.write = MagicMock()
            sess.close = MagicMock()
            return sess

        rm = MagicMock()
        rm.open_resource = MagicMock(side_effect=lambda r, **kw: (opened.append(r), _make_session(r))[1])
        monkeypatch.setattr("pyvisa.ResourceManager", MagicMock(return_value=rm))

        ok = await d.connect()
        assert ok is True
        # 第一开 inst0 (显式绑定), 识别 Platform 后第二开 hislip2
        assert any("inst0" in r for r in opened), opened
        assert any("hislip2" in r for r in opened), opened

    @pytest.mark.asyncio
    async def test_redirect_reuses_host_from_resource_str(self, monkeypatch):
        """Codex #195 R4 P2: 只给 visa_resource (无 ip) 时, 重定向 host 取自资源串。"""
        d = RealUxmDriver("uxm-inst0-noip", {
            "visa_resource": "TCPIP0::10.9.8.7::inst0::INSTR",
        })
        opened: list[str] = []

        def _make_session(resource):
            sess = MagicMock()
            sess.timeout = 5000
            if "inst0" in resource:
                sess.query = MagicMock(side_effect=lambda c: {
                    "*IDN?": "Keysight Technologies,E7515B Platform,MY123,1.0",
                }.get(c.strip(), "0"))
            else:
                sess.query = MagicMock(side_effect=lambda c: {
                    "*IDN?": "Keysight Technologies,E7515B TAF,MY123,1.0",
                    "SYSTem:APPLication:NAME?": "LTE_NR_IRAT",
                    "*OPC?": "1",
                }.get(c.strip(), "0"))
            sess.write = MagicMock()
            sess.close = MagicMock()
            return sess

        rm = MagicMock()
        rm.open_resource = MagicMock(side_effect=lambda r, **kw: (opened.append(r), _make_session(r))[1])
        monkeypatch.setattr("pyvisa.ResourceManager", MagicMock(return_value=rm))

        ok = await d.connect()
        assert ok is True
        redirects = [r for r in opened if "hislip2" in r]
        assert redirects == ["TCPIP::10.9.8.7::hislip2::INSTR"], opened

    @pytest.mark.asyncio
    async def test_explicit_non_inst0_binding_stays_pinned(self, monkeypatch):
        """显式非 inst0 绑定 (如直连 TAF 的 SOCKET) 仍然尊重, 不重定向。"""
        d = RealUxmDriver("uxm-pinned", {
            "ip": "10.0.0.9",
            "visa_resource": "TCPIP0::10.0.0.9::5125::SOCKET",
        })
        opened: list[str] = []
        sess = MagicMock()
        sess.timeout = 5000
        sess.query = MagicMock(side_effect=lambda c: {
            "*IDN?": "Keysight Technologies,E7515B Platform,MY123,1.0",
            "*OPC?": "1",
        }.get(c.strip(), "0"))
        sess.write = MagicMock()
        rm = MagicMock()
        rm.open_resource = MagicMock(side_effect=lambda r, **kw: (opened.append(r), sess)[1])
        monkeypatch.setattr("pyvisa.ResourceManager", MagicMock(return_value=rm))

        ok = await d.connect()
        assert ok is True
        assert not any("hislip2" in r for r in opened), opened  # 保持锁定

    @pytest.mark.asyncio
    async def test_uppercase_inst0_still_redirects(self, monkeypatch):
        """Codex #202 兜底 P2: 大写 INST0 (VISA 大小写不敏感的常见形式) 必须
        照样识别为 inst0 平台绑定并重定向 hislip2 —— 大小写敏感检查会误判成
        '显式非 inst0' 不重定向, NR 命令打到平台错树。"""
        d = RealUxmDriver("uxm-INST0", {
            "ip": "10.0.0.9",
            "visa_resource": "TCPIP0::10.0.0.9::INST0::INSTR",  # 大写
        })
        opened: list[str] = []

        def _make_session(resource):
            sess = MagicMock()
            sess.timeout = 5000
            if "INST0" in resource or "inst0" in resource:
                sess.query = MagicMock(side_effect=lambda c: {
                    "*IDN?": "Keysight Technologies,E7515B Platform,MY123,1.0",
                }.get(c.strip(), "0"))
            else:
                sess.query = MagicMock(side_effect=lambda c: {
                    "*IDN?": "Keysight Technologies,E7515B TAF,MY123,1.0",
                    "SYSTem:APPLication:NAME?": "LTE_NR_IRAT",
                    "*OPC?": "1",
                }.get(c.strip(), "0"))
            sess.write = MagicMock()
            sess.close = MagicMock()
            return sess

        rm = MagicMock()
        rm.open_resource = MagicMock(side_effect=lambda r, **kw: (opened.append(r), _make_session(r))[1])
        monkeypatch.setattr("pyvisa.ResourceManager", MagicMock(return_value=rm))

        ok = await d.connect()
        assert ok is True
        assert any("hislip2" in r for r in opened), opened  # 大写也重定向


class TestTextualCellStates:
    """Codex #195 复扫 P1: 5G 方言文本态 (IDLE/ATT/CONN) 也是活动态。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("state_text", ["IDLE", "ATT", "CONN", "ON"])
    async def test_textual_active_states_trigger_wrapping(self, driver_5g, state_text):
        _, written = wire_echo_visa(
            driver_5g, overrides={"ACTive:STATe?": state_text})
        ok = await driver_5g.set_cell_config({"band": "N78", "bandwidth_mhz": 100})
        assert ok is True
        # 5G profile 状态写是文本形式 (STATe OFF/ON), IRAT 是 0/1 — 兼容两形式
        assert any(w.endswith(("ACTive:STATe 0", "ACTive:STATe OFF"))
                   for w in written), (state_text, written)
        assert any(w.endswith(("ACTive:STATe 1", "ACTive:STATe ON"))
                   for w in written), (state_text, written)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("state_text", ["0", "OFF", ""])
    async def test_inactive_states_skip_wrapping(self, driver_5g, state_text):
        _, written = wire_echo_visa(
            driver_5g, overrides={"ACTive:STATe?": state_text})
        ok = await driver_5g.set_cell_config({"band": "N78", "bandwidth_mhz": 100})
        assert ok is True
        assert not any("ACTive:STATe 0" in w or "ACTive:STATe OFF" in w
                       for w in written), (state_text, written)

    @pytest.mark.asyncio
    async def test_off_write_failure_returns_false_not_raise(self, driver_irat):
        """Codex #195 复扫 P2: OFF 写失败走布尔契约, 不向 caller 裸抛。"""
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        orig = sess.write.side_effect

        def _boom_on_off(cmd):
            orig(cmd)
            if cmd.strip().endswith("ACTive:STATe 0"):
                raise RuntimeError("simulated session drop on deactivate")

        sess.write.side_effect = _boom_on_off
        ok = await driver_irat.set_cell_config({"band": "N78", "bandwidth_mhz": 100})
        assert ok is False  # 布尔契约, 无裸异常


class TestArfcnFallbackBaseline:
    """agent R6 F3: band fallback 接 P1-19 EMQuest 基线表 — 632628 是 3GPP
    例值非现场基线; custom 部署声明 (Phase 2h 旋钮, 原从未被消费) 压过基线。
    """

    @pytest.mark.asyncio
    async def test_n78_fallback_uses_emquest_baseline(self, driver_5g):
        """无显式 arfcn 的 N78 → 基线 636666 (非旧 632628), 且天然命中 5b
        合拍条件 → SSB/PointA 三件套自动补。"""
        _, written = wire_echo_visa(driver_5g)
        ok = await driver_5g.set_cell_config({"band": "N78", "bandwidth_mhz": 40})
        assert ok is True
        assert any(w.endswith("DL:ARFCN 636666") for w in written), written
        assert any("SSB:NCD:ARFCn 635712" in w for w in written), written

    @pytest.mark.asyncio
    async def test_fdd_band_fallback_from_baseline(self, driver_5g):
        """基线表覆盖旧 4-band MAP 之外的 band (N3 → 368500, 非退化 632628)。"""
        _, written = wire_echo_visa(driver_5g)
        ok = await driver_5g.set_cell_config({"band": "N3", "bandwidth_mhz": 20})
        assert ok is True
        assert any(w.endswith("DL:ARFCN 368500") for w in written), written
        assert not any("DL:ARFCN 632628" in w for w in written), written

    @pytest.mark.asyncio
    async def test_custom_arfcn_map_beats_baseline(self):
        """部署级 nr_band_arfcn_map 显式声明 > 基线; 偏离基线不乱补 SSB。"""
        drv = RealUxmDriver(
            "uxm-custom", {"ip": "10.0.0.3", "nr_band_arfcn_map": {"N78": 640000}}
        )
        _, written = wire_echo_visa(drv)
        ok = await drv.set_cell_config({"band": "N78", "bandwidth_mhz": 100})
        assert ok is True
        assert any(w.endswith("DL:ARFCN 640000") for w in written), written
        assert not any("SSB:NCD" in w for w in written), written  # 不合拍不补

    @pytest.mark.asyncio
    async def test_custom_map_lowercase_keys_normalized(self):
        """agent R6 复核 F2: 3GPP 惯用小写键 ("n78") 归一大写后仍生效 —
        self._band 恒大写, 不归一则部署声明静默失效落基线。"""
        drv = RealUxmDriver(
            "uxm-lc", {"ip": "10.0.0.4", "nr_band_arfcn_map": {"n78": 640000}}
        )
        _, written = wire_echo_visa(drv)
        ok = await drv.set_cell_config({"band": "n78", "bandwidth_mhz": 100})
        assert ok is True
        assert any(w.endswith("DL:ARFCN 640000") for w in written), written

    @pytest.mark.asyncio
    async def test_custom_map_empty_dict_not_treated_as_declaration(self):
        """agent R6 复核 F1: 空 dict (GUI 表单/JSONB 留空的现实形态) 不算
        custom 声明 — 否则粗值表被当"用户声明"压过基线, 632628 静默回归。"""
        drv = RealUxmDriver(
            "uxm-empty", {"ip": "10.0.0.5", "nr_band_arfcn_map": {}}
        )
        _, written = wire_echo_visa(drv)
        ok = await drv.set_cell_config({"band": "N78", "bandwidth_mhz": 40})
        assert ok is True
        assert any(w.endswith("DL:ARFCN 636666") for w in written), written  # 基线
        assert not any("DL:ARFCN 632628" in w for w in written), written

    @pytest.mark.asyncio
    async def test_custom_map_missing_band_falls_to_baseline(self):
        """agent R6 复核 F4: custom 提供但不含当前 band → 落基线, 不退化粗值。"""
        drv = RealUxmDriver(
            "uxm-miss", {"ip": "10.0.0.6", "nr_band_arfcn_map": {"N78": 640000}}
        )
        _, written = wire_echo_visa(drv)
        ok = await drv.set_cell_config({"band": "N3", "bandwidth_mhz": 20})
        assert ok is True
        assert any(w.endswith("DL:ARFCN 368500") for w in written), written  # N3 基线

    @pytest.mark.asyncio
    async def test_unknown_band_degrades_with_warning(self, driver_5g, monkeypatch):
        """全 miss (显式/custom/基线/粗值) → 632628 退化 + warning 提示错频。

        warning 断言用 monkeypatch logger 而非 caplog — 全量跑时前序测试污染
        logging 配置会让 caplog 捕空 (与 Discovered 登记的 2 个顺序耦合 flaky
        同病), monkeypatch 不受影响。"""
        from app.hal import uxm_base_station as uxm_mod

        warned: list = []
        monkeypatch.setattr(
            uxm_mod.logger, "warning",
            lambda msg, *a, **k: warned.append(str(msg)),
        )
        _, written = wire_echo_visa(driver_5g)
        ok = await driver_5g.set_cell_config({"band": "N99", "bandwidth_mhz": 100})
        assert ok is True
        assert any(w.endswith("DL:ARFCN 632628") for w in written), written
        assert any("无 ARFCN 来源" in m for m in warned), warned


class TestApplyTopologyProfileConsumesCellConfig:
    """agent R6 F1: apply_topology_profile 必须消费 set_cell_config 布尔契约
    — 半生效配置不许报 applied=True。"""

    def _any_profile(self):
        from app.hal.uxm_test_profiles import UxmTopologyProfile

        return UxmTopologyProfile(
            profile_id="t-any", name="t", description="", category="siso",
            band="N78", frequency_mhz=3549.99, bandwidth_mhz=40.0,
            compatible_test_apps=[],  # 兼容任何 Test App
        )

    @pytest.mark.asyncio
    async def test_apply_reports_false_when_cell_config_fails(
        self, driver_5g, monkeypatch
    ):
        monkeypatch.setattr(
            driver_5g, "set_cell_config", AsyncMock(return_value=False)
        )
        result = await driver_5g.apply_topology_profile(self._any_profile())
        assert result["applied"] is False
        assert result["reason"] == "cell_config_failed"

    @pytest.mark.asyncio
    async def test_apply_reports_true_on_success(self, driver_5g, monkeypatch):
        monkeypatch.setattr(
            driver_5g, "set_cell_config", AsyncMock(return_value=True)
        )
        result = await driver_5g.apply_topology_profile(self._any_profile())
        assert result["applied"] is True


class TestReadLiveFrequencyIdentity:
    """开关 1 (uxm_config_mode=inherit) 知情继承核对源: 从仪器读回实际
    ARFCN/BW 构造频率标识 (非下发记录)。"""

    @pytest.mark.asyncio
    async def test_reads_back_live_identity(self, driver_irat):
        """仪器当前态 (回显预写值) → 正确 identity, 与下发记录无关。"""
        _, written = wire_echo_visa(driver_irat)
        # 预写仪器态 (模拟 EMQuest 配的基线), 但不经 set_cell_config —
        # 下发记录保持冷 (get_frequency_identity 为 None)
        driver_irat._visa_session.write("BSE:CONFig:NR5G:CELL1:DL:ARFCN 636666")
        driver_irat._visa_session.write("BSE:CONFig:NR5G:CELL1:DL:BW BW40")
        assert driver_irat.get_frequency_identity() is None  # 下发记录冷
        ident = await driver_irat.read_live_frequency_identity()
        assert ident is not None
        assert ident.center_arfcn == 636666
        assert ident.bandwidth_mhz == 40.0

    @pytest.mark.asyncio
    async def test_readback_gate_off_returns_none(self, driver_5g):
        """5G_NR_Test profile (SUPPORTS_CONFIG_READBACK=False, 查询实证超时)
        → 不发查询直接 None。"""
        sess, _ = wire_echo_visa(driver_5g)
        assert await driver_5g.read_live_frequency_identity() is None
        queried = [c.args[0] for c in sess.query.call_args_list]
        assert not any("ARFCN" in q or "BW?" in q for q in queried), queried

    @pytest.mark.asyncio
    async def test_query_failure_returns_none(self, driver_irat):
        """查询抛异常 → None, 不裸抛 (一致性网按未报告跳过)。"""
        sess, _ = wire_echo_visa(driver_irat)
        sess.query.side_effect = TimeoutError("dead")
        assert await driver_irat.read_live_frequency_identity() is None

    @pytest.mark.asyncio
    async def test_empty_response_returns_none(self, driver_irat):
        """仪器回空 (未配置态) → None。"""
        _, _ = wire_echo_visa(
            driver_irat, overrides={"DL:ARFCN?": "", "DL:BW?": ""}
        )
        assert await driver_irat.read_live_frequency_identity() is None


class TestCellRestartOpcTimeout:
    """P2-1 收口 (2026-07-21 现场实证): 小区激活态改带宽触发 OFF→改→ON 环绕,
    ON 后 *OPC? 等小区重启需 10s+ → 切 VISA_TIMEOUT_CELL (30s), 默认 5s 必炸;
    finally 恢复原值。"""

    @pytest.mark.asyncio
    async def test_cell_restart_opc_uses_cell_timeout_and_restores(self, driver_irat):
        from app.hal.uxm_base_station import VISA_TIMEOUT_CELL

        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        opc_timeouts: list[int] = []
        base_query = sess.query.side_effect

        def _q(cmd, **_kw):
            if cmd.strip() == "*OPC?":
                opc_timeouts.append(sess.timeout)
            return base_query(cmd)

        sess.query = MagicMock(side_effect=_q)

        # 小区 ON 态改带宽 → cell_was_on 触发 OFF → 改 → ON → *OPC?(CELL 超时)
        ok = await driver_irat.set_cell_config({
            "band": "N78", "bandwidth_mhz": 40, "duplex": "TDD",
        })
        assert ok is True
        assert any(w.endswith("ACTive:STATe 0") for w in written), written  # 确有环绕
        assert VISA_TIMEOUT_CELL in opc_timeouts, opc_timeouts  # *OPC? 用了 30s
        assert sess.timeout == 5000  # finally 恢复原值
