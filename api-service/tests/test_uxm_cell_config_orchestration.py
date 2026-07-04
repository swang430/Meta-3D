"""P1-19: UXM set_cell_config 编排正修的行为锁定。

2026-07-03 CAICT 现场实证驱动的五组行为:
  ① "键在但值 None" 视同缺失 (band=None 曾致 .upper() 崩, ARFCN 不下发);
  ② 小区 ACTive 时禁改带宽 (-221) → ON 态改 BW 走 OFF→配→ON 环绕;
  ③ IRAT 带宽值令牌形式 "BW100" + TDD 下 UL:BW 跟随 DL 跳过单独下发;
  ④ SSB/PointA 基线自动补 (目标 ARFCN 命中 EMQuest 基线才补, 严格合拍);
  ⑤ 写后回读对账 fail-loud (IRAT 默认开; 老 5G App 查询不支持默认关)。
"""
from unittest.mock import MagicMock

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

    def _query(cmd):
        c = cmd.strip()
        for frag, resp in (overrides or {}).items():
            if frag in c:
                return resp
        if c == "*OPC?":
            return "1"
        if c.endswith("ACTive:STATe?"):
            return state["active"]
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
    async def test_no_bw_change_no_state_probe(self, driver_irat):
        sess, written = wire_echo_visa(driver_irat, cell_active=True)
        ok = await driver_irat.set_cell_config({"band": "N78", "arfcn": 636666})
        assert ok is True
        queried = [c.args[0] for c in sess.query.call_args_list]
        assert not any("ACTive:STATe?" in q for q in queried), queried


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
