"""UXM KPI 回读门 — 命令、下标、单位、NaN 哨兵、前置序列。

背景（2026-08-03）：`get_throughput_metrics()` 的 8 个字段在真机上**没有一个
是真的**。31 个 `scpi.log*` 里按 `query` 配平的实证：

  · `BTHRoughput:DL:TSTatistics:JSON?` 回的是 **HARQ 重传统计**
    （`{"CellIndex":0,"ProgressCount":1000,"Tx1Info":{"Counts":{"Ack":1240,…`），
    里面没有任何吞吐量字段 —— 我们当吞吐量解析 → 恒 0.0
  · `DL:BLER:STATistical:ALL?` 回 `IDLE,UNKN,0,0`（Early Pass/Fail 状态机）
    —— 我们 `float("IDLE")` → ValueError → 恒 0.0
  · `CSI:CQI:STATistics?` 回 `7.92E+04,…` —— idx0 是**首个 CSI 样本的绝对
    子帧号**（不是 CQI 也不是样本数，样本数在 idx1），我们当 CQI 上报
    → **79200**（比 0 更糟，是个假的大数）；CQI 均值在 **idx4**，
    idx3 是 maximum
  · `CSI:RI:HISTogram?` 的 8 个 bin 是 3GPP **上报码点** 0..7，
    rank = 码点 + 1 —— 这一条**原代码本来是对的**
  · `UEReport:RSRP|SINR:STATistics?` **手册里没有这两条命令**
  · UL 那两条：一条发过 1 次零回音，一条从没发过

命令形式 / 元素含义 / 单位 / 前置条件以 UXM 手册为准 —— **CQI/RI 两项的
逐元素布局取自仓库内的厂商 SCPI Reference 原文**
（`Instrument_API_Doc/Keysight UXM NR SCPI/UXM5G_SCPI_02_NR_PHY_Measurements.md`），
其余取自 NotebookLM notebook 236d9621。见 `docs/design/uxm-kpi-readback-fix.md`。

⚠ 这些门只证**解析与下发是按手册来的**，**不证真机接受这些命令** ——
后者必须现场走诊断序列验（`uxm_kpi_readback`，单独一片）。
"""
from __future__ import annotations

import asyncio

import pytest

from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import UxmLteNrIratProfile


@pytest.fixture
def drv():
    return RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})


def _stub_io(driver, responses: dict, trace: list | None = None):
    """在 **`_do_query` / `_do_write`** 层打桩，返回记录下来的写命令列表。

    ⚠ **必须桩在 `_do_*` 上，不能桩 `_query`/`_write`** —— UXM 的
    `_do_query`/`_do_write` 是**同步 `def`**（F64 才是 `async def`）。
    早先版本把 `_query` 换成 `async def`，等于**在 mock 里改掉了 sync/async
    契约**：生产代码里那几个 `await self._query(...)` 会去 await 一个 `str`
    抛 TypeError、被 `except Exception` 吞掉，8 个 KPI 全落回默认值，
    而门**全绿**。桩在 `_do_*` 上则由真代码决定契约。
    仓库既有的 `tests/test_uxm_cell_config_orchestration.py` 就是这个先例。

    `trace` 传入时按发生顺序记 `("W", cmd)` / `("Q", cmd)`，供时序断言用。
    """
    writes: list[str] = []

    def _do_q(cmd, **kw):
        if trace is not None:
            trace.append(("Q", cmd))
        for frag, resp in responses.items():
            if frag in cmd:
                return resp
        return ""

    def _do_w(cmd, **kw):
        writes.append(cmd)
        if trace is not None:
            trace.append(("W", cmd))
        return None

    driver._do_query = _do_q    # type: ignore[assignment]
    driver._do_write = _do_w    # type: ignore[assignment]
    return writes


# ── 门① 命令表必须是手册那条（不变量） ─────────────────────────

class TestCommandTableMatchesManual:
    """变异：把任一条改回旧的无前缀 / 旧命令 → 红。"""

    def test_kpi_commands_are_bse_rooted(self):
        """IRAT Test App 的命令全部根在 BSE: 下。原来 CQI/RI/RSRP/SINR/UL
        继承的是基类的无前缀形式 → undefined header → 零回音。"""
        p = UxmLteNrIratProfile
        for name in (
            "MEAS_TPUT_DL_OTA", "MEAS_TPUT_UL_OTA",
            "MEAS_BLER_DL", "MEAS_BLER_UL",
            "MEAS_CSI_START", "MEAS_CSI_CQI", "MEAS_CSI_RI",
            "MEAS_BTHROUGHPUT_STATE", "MEAS_BTHROUGHPUT_CLEAR",
            "MEAS_UE_REPORT_STATE", "MEAS_UE_REPORT_JSON",
        ):
            val = getattr(p, name)
            assert val, f"{name} 未定义"
            assert val.startswith("BSE:"), f"{name} 缺 BSE: 前缀 → undefined header"

    def test_throughput_command_is_ota_not_retransmit_stats(self):
        """吞吐量必须读 THRoughput:OTA，不是 TSTatistics（那是重传统计）。"""
        assert UxmLteNrIratProfile.MEAS_TPUT_DL_OTA == (
            "BSE:MEASure:NR5G:BTHRoughput:DL:THRoughput:OTA:{cell}?"
        )
        assert "TSTatistics" not in UxmLteNrIratProfile.MEAS_TPUT_DL_OTA

    def test_commands_absent_from_manual_are_none(self):
        """手册里查不到的命令必须显式 None —— 让驱动跳过而不是盲发。"""
        p = UxmLteNrIratProfile
        for name in (
            "MEAS_BTHROUGHPUT_DL_START",   # TSTatistics:STARt 手册无
            "MEAS_BTHROUGHPUT_DL_STOP",
            "MEAS_BTHROUGHPUT_DL_BLER",    # BLER:STATistical 是 Early Pass/Fail
            "MEAS_TPUT_UL_JSON",           # UL:TSTatistics 手册无
            "MEAS_TPUT_UL_BLER",
            "MEAS_UE_RSRP",                # UEReport:*:STATistics 手册无
            "MEAS_UE_SINR",
        ):
            assert getattr(p, name) is None, f"{name} 应为 None（手册里没有这条命令）"


class TestMonitoringStateGate:
    """后台监控不得在小区 OFF 时轮询 KPI/JSON 报告。"""

    def test_get_metrics_skips_kpi_queries_when_cell_is_off(self, drv):
        trace: list[tuple[str, str]] = []
        _stub_io(drv, {"BSE:STATus:NR5G:CELL1?": "OFF"}, trace)

        result = asyncio.run(drv.get_metrics())

        queries = [cmd for op, cmd in trace if op == "Q"]
        assert queries == ["BSE:STATus:NR5G:CELL1?"], queries
        assert result.metrics["cell_state"] == "OFF"
        assert result.metrics["dl_throughput_mbps"] is None
        assert result.metrics["kpi_valid"]["dl_throughput"] is False

    def test_get_metrics_reads_kpis_when_cell_is_connected(self, drv):
        trace: list[tuple[str, str]] = []
        _stub_io(drv, {
            "BSE:STATus:NR5G:CELL1?": "CONNected",
            "DL:THRoughput:OTA": "1,2e6,2e6,2e6,2e6,2e6",
        }, trace)

        result = asyncio.run(drv.get_metrics())

        queries = [cmd for op, cmd in trace if op == "Q"]
        assert "BSE:MEASure:NR5G:BTHRoughput:DL:THRoughput:OTA:CELL1?" in queries
        assert result.metrics["cell_state"] == "CONN"
        assert result.metrics["dl_throughput_mbps"] == pytest.approx(2.0)


class TestSyncContractNotViolated:
    """⭐ UXM 的 `_do_query`/`_do_write` 是**同步 def**（F64 才是 async）。

    在 `uxm_base_station.py` 里写 `await self._query(...)` 会去 await 一个
    `str` → TypeError → 被 `except Exception` 吞成一行 warning → **该字段
    静默落回默认值**。2026-08-03 我按 F64 的形状写了 UXM，8 个 KPI 全废，
    而当时的门因为把 `_query` 桩成 async 而**全绿** —— 内审 F1 用真契约
    探针才抓出来。

    这条是**源码级不变量门**：本文件里不允许 await 这两个模板方法。
    变异：任意加一个 `await self._query(` → 红。
    """

    def test_no_await_on_sync_template_methods(self):
        import inspect
        from app.hal import uxm_base_station as mod

        src = inspect.getsource(mod)
        for bad in ("await self._query(", "await self._write("):
            assert bad not in src, (
                f"uxm_base_station.py 里出现 `{bad}` —— UXM 的 _do_* 是同步 def，"
                f"await 一个 str 会抛 TypeError 并被 except 吞掉"
            )

    def test_do_query_is_sync_def(self):
        """契约本身：是同步就该是同步，改成 async 要连带改所有调用点。"""
        import inspect
        assert not inspect.iscoroutinefunction(RealUxmDriver._do_query)
        assert not inspect.iscoroutinefunction(RealUxmDriver._do_write)


# ── 门② 取值下标与单位（行为） ──────────────────────────────────

class TestKpiParsing:

    def test_dl_throughput_takes_average_and_converts_bps(self, drv):
        """6 doubles = {progress, current, min, max, average, scheduled}，单位 bps。
        变异：下标改成 1（current）或去掉 /1e6 → 红。"""
        _stub_io(drv, {
            "DL:THRoughput:OTA": "1000,4.10e8,3.9e8,4.3e8,4.20e8,4.25e8",
        })
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.dl_throughput_mbps == pytest.approx(420.0), "结论值应取 average(idx4)"
        assert m.dl_throughput_current_mbps == pytest.approx(410.0), "current 取 idx1"

    def test_ul_throughput_same_shape(self, drv):
        _stub_io(drv, {"UL:THRoughput:OTA": "500,9.0e7,8e7,1e8,9.5e7,9.6e7"})
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.ul_throughput_mbps == pytest.approx(95.0)
        assert m.ul_throughput_current_mbps == pytest.approx(90.0)

    def test_dl_bler_takes_pdsch_bler_ratio_idx8(self, drv):
        """10 doubles，idx8 = pdschBlerRatio。变异：取 idx4(nack-ratio) → 红。"""
        _stub_io(drv, {
            "DL:BLER:": "1000,900,0.9,90,0.09,10,0.01,95,0.0950,0.905",
        })
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.dl_bler == pytest.approx(0.0950)

    def test_ul_bler_takes_nack_ratio_idx4(self, drv):
        """6 doubles，idx4 = nack-ratio。"""
        _stub_io(drv, {"UL:BLER:": "800,760,0.95,40,0.0500,0"})
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.ul_bler == pytest.approx(0.05)

    def test_cqi_takes_average_idx4(self, drv):
        """⭐ 厂商手册: result[0]=绝对子帧号 [1]=count [2]=min [3]=max
        [4]=average [5]=median。取 **idx4**。

        测试数据刻意让 **idx0/idx3/idx4 三者两两不同**：
        取 idx0 → 79200（真机曾这样上报）；取 idx3 → 14（系统性乐观）；
        只有 idx4 → 8。变异：下标改成 0 或 3 → 红。
        （早先版本数据是 `…,9.6,10,0`，round(9.6)==10==idx4，
        idx3/idx4 不可区分 —— 内审变异 M-A 正是从这个缝里钻过去的。）
        """
        _stub_io(drv, {"CSI:CQI:STAT": "7.92E+04,1200,3,14,8.0,8"})
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.cqi == 8, "应取 average(idx4)=8.0"
        assert m.cqi != 14, "idx3 是 maximum，取它会系统性乐观"
        assert m.cqi != 79200, "idx0 是绝对子帧号"

    def test_ri_histogram_bins_are_codepoints_rank_is_plus_one(self, drv):
        """⭐ 8 个 bin 是 3GPP **上报码点** 0..7，rank = 码点 + 1。

        手册把它与 "CQI value (0..15)" 并列写成 "RI value (0..7)" —— CQI
        0..15 是码点，RI 同理。而 `rank_indicator` 全仓契约是**层数**。
        变异：权重改成 i → 本条红（会算出 2 而不是 3）。
        """
        # 码点 2（= rank 3）出现 100 次
        _stub_io(drv, {"CSI:RI:HIST": "0,0,100,0,0,0,0,0"})
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.rank_indicator == 3

    def test_ri_mixed_histogram(self, drv):
        # 码点1(rank2)×30 + 码点2(rank3)×70 → (2*30+3*70)/100 = 2.7 → 3
        _stub_io(drv, {"CSI:RI:HIST": "0,30,70,0,0,0,0,0"})
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.rank_indicator == 3

    def test_rank_indicator_never_below_one(self, drv):
        """⭐ 不变量：rank 0 物理上不存在。全部落 bin0 也必须报 rank 1。

        变异：权重改成 i → 本条红（会算出 0），而 analysis.py 拿它跟
        min_avg_rank_indicator(1.8) 比 → 真跑 rank 1 的 DUT 报 0，必 FAIL。
        """
        _stub_io(drv, {"CSI:RI:HIST": "1000,0,0,0,0,0,0,0"})
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.rank_indicator >= 1
        assert m.rank_indicator == 1


# ── 门③ SCPI NaN 哨兵（行为） ───────────────────────────────────

class TestScpiNanSentinel:
    """9.91E+37 是 SCPI 的 NaN。变异：去掉哨兵 → 吞吐量会变成 9.91e31 Mbps。"""

    def test_nan_does_not_become_a_value(self, drv):
        _stub_io(drv, {
            "DL:THRoughput:OTA": "0,9.91E+37,9.91E+37,9.91E+37,9.91E+37,9.91E+37",
            "CSI:CQI:STAT": "9.91E+37,9.91E+37,9.91E+37,9.91E+37,9.91E+37,9.91E+37",
        })
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.dl_throughput_mbps is None, "NaN 应保留为缺测，不能冒充 0 Mbps"
        assert m.cqi == 0

    def test_literal_nan_token_also_rejected(self, drv):
        """仪器也可能回字面 `NaN` 而不是 9.91E+37。
        内审变异 M-C（去掉 `v != v` 判据）从这个缝钻过去过。"""
        _stub_io(drv, {"DL:THRoughput:OTA": "1000,NaN,NaN,NaN,NaN,NaN"})
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.dl_throughput_mbps is None
        assert m.dl_throughput_current_mbps is None

    def test_all_nan_ri_histogram_does_not_divide_by_zero(self, drv):
        _stub_io(drv, {"CSI:RI:HIST": ",".join(["9.91E+37"] * 8)})
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.rank_indicator == 1        # 构造默认，未被写坏

    def test_kpi_valid_flags_distinguish_zero_from_missing(self, drv, caplog):
        """⭐「测出来是 0」和「根本没读到」在日志里必须长得不一样
        （P1-30 同一个母题）。变异：去掉 kpi_valid → 红。"""
        import logging
        _stub_io(drv, {
            "DL:THRoughput:OTA": "1000,0,0,0,0,0",          # 真的测出 0
            "UL:THRoughput:OTA": "0,9.91E+37,9.91E+37,9.91E+37,9.91E+37,0",
        })
        with caplog.at_level(logging.INFO, logger="app.measurement.throughput"):
            asyncio.run(drv.get_throughput_metrics())
        rec = [r for r in caplog.records
               if r.name == "app.measurement.throughput"][0]
        assert rec.kpi_valid["dl_throughput"] is True, "真测出 0 应标 valid"
        assert rec.kpi_valid["ul_throughput"] is False, "NaN 应标 invalid"
        assert "ul_throughput" in rec.kpi_missing


# ── 门④ 前置序列（行为） ────────────────────────────────────────

class TestParseDoublesKeepsPositions:
    """⭐ 空元素必须**占位**，否则后面所有下标左移一位。
    内审 F4 实证：`"1000,,3.9e8,4.3e8,4.20e8,4.25e8"` 丢位后
    `_pick(...,4)` 取到 4.25e8（current-scheduled）而不是 4.20e8（average）。
    变异：空 token 改回 `continue` → 红。"""

    def test_empty_element_keeps_position(self, drv):
        _stub_io(drv, {"DL:THRoughput:OTA": "1000,,3.9e8,4.3e8,4.20e8,4.25e8"})
        m = asyncio.run(drv.get_throughput_metrics())
        assert m.dl_throughput_mbps == pytest.approx(420.0), "空元素丢位导致下标左移"

    def test_non_numeric_element_keeps_position(self, drv):
        vals = RealUxmDriver._parse_doubles("IDLE,UNKN,0,0")
        assert vals == [None, None, 0.0, 0.0]


class TestMeasurementPrerequisites:
    """不开累积，所有 KPI 查询恒返 9.91E+37 —— 手册明确。
    变异：删掉 _enable_kpi_measurements 调用 → 红。"""

    def test_enable_sends_all_three_prerequisites(self, drv):
        writes = _stub_io(drv, {})
        asyncio.run(drv._enable_kpi_measurements("CELL1"))
        joined = " | ".join(writes)
        assert "BSE:MEASure:NR5G:BTHRoughput:STATe ON" in joined, "缺全局吞吐量/BLER 累积"
        assert "BSE:MEASure:NR5G:CELL1:CSI:STARt" in joined, "缺 CSI 累积"
        assert "BSE:CONFig:MEASurement:REPort ON" in joined, "缺 UE 测量报告队列"

    def test_configure_actually_sends_them(self, drv):
        """⭐ 生效端门：断言 `configure_mac_throughput_test()` **真的发了**前置，
        而不是只测 helper 本身。

        变异实证：把 `configure_mac_throughput_test` 里那句
        `await self._enable_kpi_measurements(cell)` 删掉，上面那条只调 helper
        的门**全绿** —— 门锁在了 helper 上，不在调用点上。这是今晚第三次
        踩同一个母题（P1-30 内审 F1 / Codex #273 P2 都是它）。

        变异：删掉调用点、或把它挪回函数末尾 → 本条红。

        ⚠ 断言的是「前置**发出去了**」，不是「函数返回成功」——
        `configure_mac_throughput_test()` 在 IRAT 方言上那 11 条命令
        （PDSCH_*/TDD_*/HARQ_*/CSIRS_PORTS/MEAS_TPUT_STAT_COUNT）
        **11/11 都是 None**。
        **P1-32 已把它们改成 `_cmd()` graceful-skip**（不再抛 AttributeError，
        改为返回 `MacThroughputConfigResult` 并由调用方中止），
        但前置仍必须排在它们**之前** —— 否则本片的修复在真正用的那个方言上是死的。
        """
        writes = _stub_io(drv, {"*OPC?": "1"})
        asyncio.run(drv.configure_mac_throughput_test(mimo_layers=2))
        joined = " | ".join(writes)
        assert "BTHRoughput:STATe ON" in joined, (
            "configure_mac_throughput_test 没发全局吞吐量/BLER 累积 —— "
            "后面所有 KPI 查询会恒返 9.91E+37"
        )
        assert "CSI:STARt" in joined, "没发 CSI 累积 → CQI/RI 读不到"
        assert "MEASurement:REPort ON" in joined, "没开 UE 测量报告队列 → RSRP/SINR 读不到"

    def test_one_failure_does_not_block_the_other_two(self, drv):
        """三条互相独立 —— 一条挂了不该让另外两组 KPI 也读不到。"""
        writes: list[str] = []

        def _do_w(cmd, **kw):       # sync —— 与真 _do_write 契约一致
            if "BTHRoughput:STATe" in cmd:
                raise OSError("boom")
            writes.append(cmd)

        drv._do_write = _do_w       # type: ignore[assignment]
        asyncio.run(drv._enable_kpi_measurements("CELL1"))
        joined = " | ".join(writes)
        assert "CSI:STARt" in joined
        assert "MEASurement:REPort ON" in joined


class TestWindowUsesClearNotNonexistentStartStop:
    """`TSTatistics:STARt|STOP` 手册里不存在；圈窗口用 BTHRoughput:CLEar。
    变异：改回 START/STOP → 红。"""

    def test_window_sends_clear_before_reading(self, drv):
        """⭐ 断言的是**时序**不只是"发过" —— CLEar 必须在第一条读之前。

        内审变异 M-D 实证：把 CLEar 挪到 `get_throughput_metrics()` **之后**，
        只判 "in writes" 的旧断言**全绿**，而真机上每个窗口读的都是**上一个
        窗口**的累积值，per-sample std/mean 全错位一格 —— 这个函数存在的
        理由被打掉了。「门锁的是 helper，不是生效端」的时序版本。
        """
        trace: list = []
        _stub_io(drv, {"THRoughput:OTA": "1,0,0,0,0,0"}, trace=trace)
        asyncio.run(drv.measure_throughput_window(0.0))

        clear_at = next((i for i, (k, c) in enumerate(trace)
                         if k == "W" and "BTHRoughput:CLEar" in c), None)
        read_at = next((i for i, (k, c) in enumerate(trace)
                        if k == "Q" and "THRoughput:OTA" in c), None)
        assert clear_at is not None, "没发 BTHRoughput:CLEar"
        assert read_at is not None, "没读 OTA 吞吐量"
        assert clear_at < read_at, (
            f"CLEar 排在读之后（clear@{clear_at} vs read@{read_at}）—— "
            "读到的会是上一个窗口的累积值"
        )
        joined = " | ".join(c for k, c in trace)
        assert "TSTatistics:STARt" not in joined
        assert "TSTatistics:STOP" not in joined


# ── 门⑤ UE L3 测量报告解析（行为） ──────────────────────────────

class TestUeMeasurementReportParsing:

    def test_extracts_rsrp_and_sinr(self):
        raw = ('{"NumberOfReportsExtracted":1,"MeasurementReports":'
               '[{"CellReports":[{"RSRP":-85.5,"RSRQ":-11.0,"SINR":18.25}]}]}')
        rsrp, sinr = RealUxmDriver._parse_ue_measurement_report(raw)
        assert rsrp == pytest.approx(-85.5)
        assert sinr == pytest.approx(18.25)

    def test_scpi_quoted_and_escaped_payload(self):
        """SCPI 会把整串加引号、内部引号双写 —— 手册明说。"""
        raw = '"{""MeasurementReports"":[{""CellReports"":[{""RSRP"":-90.0}]}]}"'
        rsrp, sinr = RealUxmDriver._parse_ue_measurement_report(raw)
        assert rsrp == pytest.approx(-90.0)
        assert sinr is None

    def test_nan_string_is_not_a_value(self):
        """手册示例里 RSRP 常常是字符串 "NaN" —— 那是没数据，不是 0。"""
        raw = '{"MeasurementReports":[{"CellReports":[{"RSRP":"NaN","SINR":"NaN"}]}]}'
        assert RealUxmDriver._parse_ue_measurement_report(raw) == (None, None)

    def test_empty_and_malformed_are_safe(self):
        for raw in ("", "   ", "not json", "{}", '{"MeasurementReports":[]}'):
            assert RealUxmDriver._parse_ue_measurement_report(raw) == (None, None)

    def test_takes_latest_report(self):
        raw = ('{"MeasurementReports":['
               '{"CellReports":[{"RSRP":-100.0}]},'
               '{"CellReports":[{"RSRP":-80.0}]}]}')
        rsrp, _ = RealUxmDriver._parse_ue_measurement_report(raw)
        assert rsrp == pytest.approx(-80.0), "应取最新那份报告"


class TestUnverifiedUnitsNotClaimedAsEngineering:
    """⭐ 手册**没说明** L3 报告里 RSRP/SINR 的口径（原始码点还是 dBm/dB）——
    NotebookLM 三次明确回"手册未说明"，未做推断。

    所以既不能按 3GPP 通式自己换算（盲试），也不能原样写进名为 `_dbm` /
    `_db` 的字段（假数据冒充真数据，正是本片要治的病）。只把原样值留进
    证据（`measurement.log` 的 `kpi_raw_unverified`），结论字段保持"未读到"。

    变异：把 `raw_unverified["rsrp_raw"]` 改回 `metrics.rsrp_dbm = rsrp` → 红。
    """

    def test_rsrp_goes_to_raw_bucket_not_dbm_field(self, drv, caplog):
        import logging
        payload = ('{"MeasurementReports":[{"CellReports":'
                   '[{"RSRP":72.0,"SINR":31.0}]}]}')
        _stub_io(drv, {"MEASurement:JSON:REPort:FETCh": payload})
        with caplog.at_level(logging.INFO, logger="app.measurement.throughput"):
            m = asyncio.run(drv.get_throughput_metrics())

        assert m.rsrp_dbm == -999.0, (
            "72.0 口径未知（3GPP rsrp-Result 码点 72 = -84 dBm；也可能已是 dBm）"
            "—— 不能当 dBm 写进结论字段"
        )
        assert m.sinr_db == -999.0
        rec = [r for r in caplog.records
               if r.name == "app.measurement.throughput"][0]
        assert rec.kpi_raw_unverified["rsrp_raw"] == 72.0, "原样值必须留进证据"
        assert rec.kpi_raw_unverified["sinr_raw"] == 31.0
        assert rec.kpi_valid["rsrp"] is False, "口径未确认 = 没读到，不是读到了"


class TestUndefinedCommandsAreSkippedNotSent:
    """方言里为 None 的命令必须跳过，不能盲发（F64 禁盲试同源纪律）。"""

    def test_no_query_for_none_commands(self, drv):
        sent: list[str] = []

        def _do_q(cmd, **kw):       # sync —— 与真 _do_query 契约一致
            sent.append(cmd)
            return ""

        def _do_w(cmd, **kw):
            return None

        drv._do_query = _do_q       # type: ignore[assignment]
        drv._do_write = _do_w       # type: ignore[assignment]
        asyncio.run(drv.get_throughput_metrics())
        joined = " | ".join(sent)
        assert "UEReport:RSRP" not in joined
        assert "UEReport:SINR" not in joined
        assert "UL:TSTatistics" not in joined
        assert "BLER:STATistical" not in joined
