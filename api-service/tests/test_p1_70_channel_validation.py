"""P1-70 行为门：信道验证第一激活批（temporal + doppler）。

守什么（对应 P1-69 设计稿 §1/§4/§7）：
1. FSVA 真驱动 measure_pdp / measure_doppler_spectrum 的返回契约
   （signal_analyzer.py docstring：等长、最强径/峰 0 dB、轴由实际采样率派生）、
   fail-loud（错误队列非空 / 解析不出 → RuntimeError 不落半截数据）、
   wire 门（发出的每条 SCPI ⊆ 手册核过的白名单）、finally 复原
   （TRAC:IQ:STAT OFF 恒发、超时恒恢复）；
2. Keysight X 系列两方法 NotImplementedError 且消息指路 FSVA（假手册申报）；
3. channel_calibration temporal/doppler 端点 use_mock 真透传 + 缺省 True
   （照 test_p1_68 的 _capture 形态：测「字段到了 service」，不测「schema 有字段」）；
4. Orchestrator ×2（/plan、/execute）use_mock 透传 + 缺省 True；
5. phase 只读 ×3 去死参回归（构造不再收到显式 use_mock，端点仍 200）；
6. 诊断序列 rs_fsva_iq_capability：mock/未加载拒绝、只读零写入、
   四态 verdict（SUCCESS/被拒也是答案、BLOCKER、ABORTED）。

驱动假会话照 tests/test_p1_67 的 _FakeUxmSession 形态（真实生效端 = 发到
会话上的命令与手册格式的回复，不钉内部状态）。

变异清单（内存快照还原实跑，结果见 PR/报告）：
- M1 temporal 端点换回硬编码 use_mock=True → 门 3 红；
- M2 orchestrator /execute 换回硬编码 True → 门 4 红；
- M3 驱动吞错误队列（_assert_error_queue_clean 改 return）→ 门 1 fail-loud 红；
- M4 PDP 不归一化 → 门 1 0 dB 契约红；
- M5 序列偷发写命令 → 门 6 零写入红；
- M6 phase 端点加回 use_mock=True 死参 → 门 5 红。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.hal.rs_fsva import FsvaScpi, RealRsFsvaDriver
from app.main import app

# ── DB 隔离（照 test_p1_68 骨架：module 级 SQLite override） ──────────────
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSessionLocal = sessionmaker(bind=_engine)


def _override_get_db():
    db = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True, scope="module")
def _install_get_db_override():
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _tables():
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════
# 门 1：FSVA 驱动 TRACe:IQ 采集
# ═══════════════════════════════════════════════════════════════════════

# 手册核过的 wire 白名单（R&S FSVA/FSV 1176.7510.02─13；页码见 rs_fsva.py
# FsvaScpi 常量注释）。驱动在 measure_pdp / measure_doppler_spectrum 期间
# 发出的每条命令都必须落在这些前缀里。
_WIRE_WHITELIST = (
    "SENSe:FREQuency:CENTer ",       # p809
    "TRACe:IQ:STATe ON",             # p895
    "TRACe:IQ:STATe OFF",            # p895
    "TRACe:IQ:SET NORM,10MHz,",      # p904（占位值照 p897 例）
    "TRACe:IQ:SRATe?",               # p906（查询形推断，错误队列核对）
    "TRACe:IQ:DATA:FORMat IQBLock",  # p897-898
    "FORMat:DATA ASCii",             # p933
    "TRACe:IQ:DATA?",                # p897
    "SYST:ERR?",                     # p969
)


class _FakeFsvaSession:
    """回复表 + IQ 数据合成的假 VISA 会话（真实生效端 = 收到的命令序列）。

    TRACe:IQ:DATA? 按**最后一条 TRAC:IQ:SET 的样本数**合成 2N 个 CSV 值
    （I 块在前 Q 块在后，IQBLock 排列 —— 手册样例程序 p1036-1037 的形态）。
    """

    def __init__(
        self,
        srate_reply: str,
        scenario=None,
        err_replies: Optional[List[str]] = None,
        data_override: Optional[str] = None,
    ):
        self.written: List[str] = []
        self.queried: List[str] = []
        self.ops: List[str] = []
        self.timeout = 15000
        self.data_query_timeouts: List[int] = []
        self._srate_reply = srate_reply
        self._scenario = scenario
        self._err_replies = list(err_replies or [])
        self._data_override = data_override

    def write(self, cmd: str) -> None:
        c = cmd.strip()
        self.written.append(c)
        self.ops.append(c)

    def _last_set_num_samples(self) -> int:
        sets = [c for c in self.written if c.startswith("TRACe:IQ:SET ")]
        assert sets, "TRACe:IQ:DATA? 之前没有 TRAC:IQ:SET"
        return int(sets[-1].split(",")[-1])

    def query(self, cmd: str) -> str:
        c = cmd.strip()
        self.queried.append(c)
        self.ops.append(c)
        if c == "SYST:ERR?":
            return self._err_replies.pop(0) if self._err_replies else '0,"No error"'
        if c == FsvaScpi.IQ_SRATE_QUERY:
            return self._srate_reply
        if c == FsvaScpi.IQ_DATA_QUERY:
            self.data_query_timeouts.append(self.timeout)
            if self._data_override is not None:
                return self._data_override
            fs = float(self._srate_reply)
            n = self._last_set_num_samples()
            x = self._scenario(fs, n)
            return ",".join(
                f"{v:.9g}" for v in np.concatenate([x.real, x.imag])
            )
        raise AssertionError(f"驱动发了脚本外查询: {c!r}")


def _mk_driver(sess: _FakeFsvaSession) -> RealRsFsvaDriver:
    d = RealRsFsvaDriver("sa-fsva-1", {"ip": "192.168.100.50"})
    d._visa_session = sess
    return d


def _two_tap_scenario(fs: float, n: int) -> np.ndarray:
    """两径信道：h = [1, 0×15, 0.5]（第二径 +16 样本 = 500 ns @32 MHz），
    激励为复白噪声。该估计器给出的是时延自相关（延迟差谱，见驱动 docstring）：
    |r(16)|/r(0) = |h₀h₁|/(|h₀|²+|h₁|²) = 0.5/1.25 = 0.4 → -3.98 dB。"""
    rng = np.random.default_rng(42)
    s = (rng.standard_normal(n + 16) + 1j * rng.standard_normal(n + 16)) / np.sqrt(2)
    return s[16:16 + n] + 0.5 * s[0:n]


def _tone_scenario(fs: float, n: int) -> np.ndarray:
    """+25 Hz 复单音（多普勒谱峰应落在 +25 Hz）+ 少量噪声。"""
    rng = np.random.default_rng(7)
    t = np.arange(n) / fs
    return (np.exp(2j * np.pi * 25.0 * t)
            + 0.01 * (rng.standard_normal(n) + 1j * rng.standard_normal(n)))


def _assert_wire_whitelisted(sess: _FakeFsvaSession) -> None:
    for cmd in sess.ops:
        assert any(cmd.startswith(p) for p in _WIRE_WHITELIST), (
            f"发出了白名单外的 SCPI（手册未核过）: {cmd!r}"
        )


class TestFsvaMeasurePdp:
    def test_contract_lengths_normalization_and_delay_axis(self):
        sess = _FakeFsvaSession("32000000", scenario=_two_tap_scenario)
        d = _mk_driver(sess)
        delays, power_db = asyncio.run(
            d.measure_pdp(3.5e9, max_delay_ns=2000.0, resolution_ns=10.0)
        )
        # 等长
        assert len(delays) == len(power_db)
        # 时延轴由**实际**采样率派生：32 MHz → 31.25 ns/bin，64 bins 盖 2000 ns
        assert delays[0] == 0.0
        assert delays[1] == pytest.approx(31.25)
        assert len(delays) == 64
        # 最强径 0 dB（接口契约），且在 lag 0（自相关性质）
        assert max(power_db) == pytest.approx(0.0, abs=1e-9)
        assert power_db[0] == pytest.approx(0.0, abs=1e-9)
        # 第二径：+16 bin = 500 ns，理论 -3.98 dB（延迟差谱电平，见 scenario 注释）
        assert delays[16] == pytest.approx(500.0)
        assert -5.0 < power_db[16] < -3.0, (
            f"500 ns 径应约 -3.98 dB，实得 {power_db[16]:.2f}"
        )
        _assert_wire_whitelisted(sess)
        # finally 复原：STAT OFF 已发、超时已恢复、采集期超时被放大
        assert FsvaScpi.IQ_STATE_OFF in sess.written
        assert sess.timeout == 15000
        assert sess.data_query_timeouts and sess.data_query_timeouts[0] >= 15000

    def test_center_freq_and_manual_ordering_sent(self):
        sess = _FakeFsvaSession("32000000", scenario=_two_tap_scenario)
        d = _mk_driver(sess)
        asyncio.run(d.measure_pdp(3.5e9))
        assert "SENSe:FREQuency:CENTer 3500000000.0" in sess.written
        # 样例程序 p1036 注释：STAT ON 必须先于 SET
        idx_on = sess.ops.index(FsvaScpi.IQ_STATE_ON)
        idx_set = next(i for i, c in enumerate(sess.ops)
                       if c.startswith("TRACe:IQ:SET "))
        assert idx_on < idx_set

    def test_error_queue_dirty_raises_and_still_restores(self):
        sess = _FakeFsvaSession(
            "32000000", scenario=_two_tap_scenario,
            err_replies=['-113,"Undefined header"'],
        )
        d = _mk_driver(sess)
        with pytest.raises(RuntimeError, match="错误队列非空"):
            asyncio.run(d.measure_pdp(3.5e9))
        # fail-loud 路径也要复原
        assert FsvaScpi.IQ_STATE_OFF in sess.written
        assert sess.timeout == 15000

    def test_unparsable_data_raises(self):
        sess = _FakeFsvaSession("32000000", data_override="abc,def")
        d = _mk_driver(sess)
        with pytest.raises(RuntimeError, match="非数值"):
            asyncio.run(d.measure_pdp(3.5e9))
        assert FsvaScpi.IQ_STATE_OFF in sess.written

    def test_wrong_value_count_raises(self):
        sess = _FakeFsvaSession("32000000", data_override="1.0,2.0,3.0")
        d = _mk_driver(sess)
        with pytest.raises(RuntimeError, match="2×"):
            asyncio.run(d.measure_pdp(3.5e9))

    def test_degenerate_sample_rate_fails_loud(self):
        # 实际速率低到时延窗内不足两个 bin：1 kHz → 1e6 ns/bin ≫ 2000 ns 窗
        sess = _FakeFsvaSession("1000", scenario=_two_tap_scenario)
        d = _mk_driver(sess)
        with pytest.raises(RuntimeError, match="不足两个 bin"):
            asyncio.run(d.measure_pdp(3.5e9))
        assert FsvaScpi.IQ_STATE_OFF in sess.written

    def test_not_connected_raises(self):
        d = RealRsFsvaDriver("sa-fsva-nc", {"ip": "192.168.100.50"})
        with pytest.raises(RuntimeError, match="Not connected"):
            asyncio.run(d.measure_pdp(3.5e9))

    def test_bad_args_rejected(self):
        sess = _FakeFsvaSession("32000000", scenario=_two_tap_scenario)
        d = _mk_driver(sess)
        with pytest.raises(ValueError):
            asyncio.run(d.measure_pdp(3.5e9, max_delay_ns=-1.0))
        assert sess.ops == [], "参数校验失败不该碰仪器"


class TestFsvaMeasureDopplerSpectrum:
    def test_contract_symmetric_axis_peak_at_tone(self):
        sess = _FakeFsvaSession("400", scenario=_tone_scenario)
        d = _mk_driver(sess)
        freqs, power_db = asyncio.run(
            d.measure_doppler_spectrum(3.5e9, max_doppler_hz=100.0, num_bins=64)
        )
        assert len(freqs) == 64 and len(power_db) == 64
        assert freqs[0] == pytest.approx(-100.0)
        assert freqs[-1] == pytest.approx(100.0)
        # 峰 0 dB（接口契约）且落在 +25 Hz（±1 bin 间距）
        assert max(power_db) == pytest.approx(0.0, abs=1e-9)
        peak_freq = freqs[int(np.argmax(power_db))]
        bin_spacing = 200.0 / 63
        assert abs(peak_freq - 25.0) <= bin_spacing * 1.001, (
            f"谱峰应在 +25 Hz，实得 {peak_freq:.2f} Hz"
        )
        _assert_wire_whitelisted(sess)
        assert FsvaScpi.IQ_STATE_OFF in sess.written
        assert sess.timeout == 15000
        # 长采集：6144 样本 @400 Hz ≈ 15.4 s → 超时必须被放大过
        assert sess.data_query_timeouts[0] > 15000

    def test_sample_rate_cannot_cover_span_fails_loud(self):
        # 仪器夹到 100 Hz < 2×max_doppler(200 Hz) → 网格盖不住 ±100 Hz
        sess = _FakeFsvaSession("100", scenario=_tone_scenario)
        d = _mk_driver(sess)
        with pytest.raises(RuntimeError, match="盖不住"):
            asyncio.run(d.measure_doppler_spectrum(3.5e9, max_doppler_hz=100.0,
                                                   num_bins=64))
        assert FsvaScpi.IQ_STATE_OFF in sess.written

    def test_error_queue_dirty_raises(self):
        sess = _FakeFsvaSession("400", scenario=_tone_scenario,
                                err_replies=['-200,"Execution error"'])
        d = _mk_driver(sess)
        with pytest.raises(RuntimeError, match="错误队列非空"):
            asyncio.run(d.measure_doppler_spectrum(3.5e9, max_doppler_hz=100.0,
                                                   num_bins=64))

    def test_bad_args_rejected(self):
        sess = _FakeFsvaSession("400", scenario=_tone_scenario)
        d = _mk_driver(sess)
        with pytest.raises(ValueError):
            asyncio.run(d.measure_doppler_spectrum(3.5e9, max_doppler_hz=0.0))
        with pytest.raises(ValueError):
            asyncio.run(d.measure_doppler_spectrum(3.5e9, num_bins=1))
        assert sess.ops == []


# ═══════════════════════════════════════════════════════════════════════
# 门 2：Keysight X 系列显式未实现 + 指路
# ═══════════════════════════════════════════════════════════════════════

class TestKeysightXSeriesNotImplemented:
    def _mk(self):
        from app.hal.keysight_x_series_sa import RealKeysightXSeriesSaDriver
        return RealKeysightXSeriesSaDriver("sa-x-1", {"ip": "192.168.100.60"})

    def test_measure_pdp_not_implemented_points_to_fsva(self):
        d = self._mk()
        with pytest.raises(NotImplementedError) as ei:
            asyncio.run(d.measure_pdp(3.5e9))
        msg = str(ei.value)
        assert "FSVA3000" in msg and "RealRsFsvaDriver" in msg
        assert "假文件" in msg, "消息必须申报本地 X 系列手册系假文件"

    def test_measure_doppler_not_implemented_points_to_fsva(self):
        d = self._mk()
        with pytest.raises(NotImplementedError) as ei:
            asyncio.run(d.measure_doppler_spectrum(3.5e9))
        msg = str(ei.value)
        assert "FSVA3000" in msg and "真手册" in msg


# ═══════════════════════════════════════════════════════════════════════
# 门 3：channel_calibration temporal/doppler use_mock 真透传 + 缺省 True
# ═══════════════════════════════════════════════════════════════════════

class _FakeCal:
    id = uuid.uuid4()


def _capture_channel_service(monkeypatch, captured: List[Any]):
    import app.api.channel_calibration as api_mod

    class _Stub:
        def __init__(self, db):
            pass

        async def run_temporal_calibration(self, **kw):
            captured.append(kw.get("use_mock", "MISSING"))
            return _FakeCal()

        async def run_doppler_calibration(self, **kw):
            captured.append(kw.get("use_mock", "MISSING"))
            return _FakeCal()

    monkeypatch.setattr(api_mod, "ChannelCalibrationService", _Stub)


def _temporal_payload(**extra) -> Dict[str, Any]:
    body = {
        "scenario": {"type": "UMa", "condition": "NLOS", "fc_ghz": 3.5},
        "calibrated_by": "p1-70-gate",
    }
    body.update(extra)
    return body


class TestChannelCalibrationUseMockReachesService:
    def test_temporal_passes_explicit_false(self, monkeypatch):
        captured: List[Any] = []
        _capture_channel_service(monkeypatch, captured)
        r = client.post("/api/v1/calibration/channel/temporal/start",
                        json=_temporal_payload(use_mock=False))
        assert r.status_code == 202, r.text
        assert captured == [False], "request.use_mock=False 未到达 service"

    def test_temporal_defaults_to_mock(self, monkeypatch):
        captured: List[Any] = []
        _capture_channel_service(monkeypatch, captured)
        r = client.post("/api/v1/calibration/channel/temporal/start",
                        json=_temporal_payload())
        assert r.status_code == 202, r.text
        assert captured == [True], "缺省必须是 True（向后兼容）"

    def test_doppler_passes_explicit_false(self, monkeypatch):
        captured: List[Any] = []
        _capture_channel_service(monkeypatch, captured)
        r = client.post("/api/v1/calibration/channel/doppler/start",
                        json={"velocity_kmh": 30.0, "fc_ghz": 3.5,
                              "calibrated_by": "p1-70-gate",
                              "use_mock": False})
        assert r.status_code == 202, r.text
        assert captured == [False], "doppler 未透传 use_mock"

    def test_doppler_defaults_to_mock(self, monkeypatch):
        captured: List[Any] = []
        _capture_channel_service(monkeypatch, captured)
        r = client.post("/api/v1/calibration/channel/doppler/start",
                        json={"velocity_kmh": 30.0, "fc_ghz": 3.5,
                              "calibrated_by": "p1-70-gate"})
        assert r.status_code == 202, r.text
        assert captured == [True], "doppler 缺省必须 True（向后兼容）"


# ═══════════════════════════════════════════════════════════════════════
# 门 4：Orchestrator ×2 use_mock 透传 + 缺省 True
# ═══════════════════════════════════════════════════════════════════════

def _capture_orchestrator(monkeypatch, captured: List[Any]):
    import app.api.path_loss_calibration as api_mod

    class _Stub:
        def __init__(self, db, use_mock=True):
            captured.append(use_mock)

        def get_calibration_plan(self, chamber_id, frequency_mhz,
                                 force_recalibrate=False):
            return {"chamber_id": str(chamber_id), "items_to_calibrate": []}

        async def execute_calibration_plan(self, **kw):
            return {"chamber_id": str(kw.get("chamber_id"))}

    monkeypatch.setattr(api_mod, "CalibrationOrchestrator", _Stub)


class TestOrchestratorUseMockReachesConstructor:
    def test_plan_passes_explicit_false(self, monkeypatch):
        captured: List[Any] = []
        _capture_orchestrator(monkeypatch, captured)
        r = client.get(
            f"/api/v1/calibration/orchestrator/plan/{uuid.uuid4()}",
            params={"use_mock": "false"},
        )
        assert r.status_code == 200, r.text
        assert captured == [False], "/plan 未把 use_mock 传进 Orchestrator 构造"

    def test_plan_defaults_to_mock(self, monkeypatch):
        captured: List[Any] = []
        _capture_orchestrator(monkeypatch, captured)
        r = client.get(f"/api/v1/calibration/orchestrator/plan/{uuid.uuid4()}")
        assert r.status_code == 200, r.text
        assert captured == [True], "/plan 缺省必须 True（向后兼容）"

    def test_execute_passes_explicit_false(self, monkeypatch):
        captured: List[Any] = []
        _capture_orchestrator(monkeypatch, captured)
        r = client.post(
            f"/api/v1/calibration/orchestrator/execute/{uuid.uuid4()}",
            params={"calibrated_by": "p1-70-gate", "use_mock": "false"},
        )
        assert r.status_code == 200, r.text
        assert captured == [False], "/execute 未把 use_mock 传进 Orchestrator 构造"

    def test_execute_defaults_to_mock(self, monkeypatch):
        captured: List[Any] = []
        _capture_orchestrator(monkeypatch, captured)
        r = client.post(
            f"/api/v1/calibration/orchestrator/execute/{uuid.uuid4()}",
            params={"calibrated_by": "p1-70-gate"},
        )
        assert r.status_code == 200, r.text
        assert captured == [True], "/execute 缺省必须 True（向后兼容）"


# ═══════════════════════════════════════════════════════════════════════
# 门 5：phase 只读 ×3 去死参回归
# ═══════════════════════════════════════════════════════════════════════

def _capture_phase_service(monkeypatch, explicit_use_mock: List[Any]):
    import app.api.path_loss_calibration as api_mod

    class _Status:
        def to_dict(self):
            return {"coherence": "stub"}

    class _Stub:
        def __init__(self, db, *args, **kwargs):
            # 记录站点是否仍显式传 use_mock（死参）；默认构造 = 干净
            explicit_use_mock.append(bool(args) or ("use_mock" in kwargs))

        def get_phase_coherence_status(self, chamber_id):
            return _Status()

        def calculate_phase_compensation(self, chamber_id, frequency_mhz):
            return []

        async def verify_phase_coherence(self, chamber_id, frequency_mhz):
            return {"verified": True}

    monkeypatch.setattr(api_mod, "PhaseCalibrationService", _Stub)


class TestPhaseReadOnlyEndpointsDropDeadParam:
    def test_coherence_get(self, monkeypatch):
        explicit: List[Any] = []
        _capture_phase_service(monkeypatch, explicit)
        r = client.get(f"/api/v1/calibration/phase/coherence/{uuid.uuid4()}")
        assert r.status_code == 200, r.text
        assert explicit == [False], "coherence 站点仍显式传 use_mock 死参"

    def test_compensation_get(self, monkeypatch):
        explicit: List[Any] = []
        _capture_phase_service(monkeypatch, explicit)
        r = client.get(f"/api/v1/calibration/phase/compensation/{uuid.uuid4()}")
        assert r.status_code == 200, r.text
        assert explicit == [False], "compensation 站点仍显式传 use_mock 死参"

    def test_verify_post(self, monkeypatch):
        explicit: List[Any] = []
        _capture_phase_service(monkeypatch, explicit)
        r = client.post("/api/v1/calibration/phase/verify",
                        params={"chamber_id": str(uuid.uuid4())})
        assert r.status_code == 200, r.text
        assert explicit == [False], "verify 站点仍显式传 use_mock 死参"


# ═══════════════════════════════════════════════════════════════════════
# 门 6：诊断序列 rs_fsva_iq_capability
# ═══════════════════════════════════════════════════════════════════════

from unittest.mock import MagicMock  # noqa: E402

from app.diagnostics.sequences import rs_fsva_iq_capability as seq  # noqa: E402

_FSVA_IDN = "Rohde&Schwarz,FSVA3000,1330.5000K05/101025,4.10"

_CAP_REPLIES = {
    "*IDN?": _FSVA_IDN,
    "TRACe:IQ:STATe?": "0",
    "TRACe:IQ:SRATe?": "32000000",
    "TRACe:IQ:BWIDth?": "25600000",
    "TRACe:IQ:RLENgth?": "691",
}


class _ScriptedSa:
    def __init__(self, replies: Dict[str, str], *, err_replies=None,
                 raise_for=()):
        self._replies = dict(replies)
        self._err_replies = list(err_replies or [])
        self._raise_for = set(raise_for)
        self.queries: List[str] = []

    def _query(self, cmd: str) -> str:
        self.queries.append(cmd)
        if cmd in self._raise_for:
            raise TimeoutError(f"VI_ERROR_TMO on {cmd}")
        if cmd == "SYST:ERR?":
            return self._err_replies.pop(0) if self._err_replies else '0,"No error"'
        if cmd not in self._replies:
            raise AssertionError(f"序列发了脚本外命令: {cmd!r}")
        return self._replies[cmd]


class MockSignalAnalyzer:
    def _query(self, cmd):  # pragma: no cover
        raise AssertionError("mock 驱动不该被查询")


def _run_seq(sa, params=None):
    hal = MagicMock()
    hal.drivers = {"signalAnalyzer": sa}
    return asyncio.run(seq.run(MagicMock(), hal, params or {},
                               log=lambda *_: None))


def _assert_read_only(sa: _ScriptedSa) -> None:
    """零写入门：序列发的每条命令都必须是查询（以 ? 结尾的命令头）。"""
    for cmd in sa.queries:
        assert cmd.split(" ", 1)[0].endswith("?"), f"序列发了写命令: {cmd!r}"


class TestFsvaIqCapabilitySequence:
    def test_metadata(self):
        assert seq.metadata.required_categories == ["signalAnalyzer"]
        assert seq.metadata.safe_during_test is False

    def test_driver_not_loaded_refused(self):
        hal = MagicMock()
        hal.drivers = {}
        result = asyncio.run(seq.run(MagicMock(), hal, {}, log=lambda *_: None))
        assert result.success is False
        assert "未加载 signalAnalyzer" in result.summary

    def test_mock_driver_refused(self):
        result = _run_seq(MockSignalAnalyzer())
        assert result.success is False
        assert "mock" in result.summary

    def test_all_supported_is_success_and_read_only(self):
        sa = _ScriptedSa(dict(_CAP_REPLIES))
        result = _run_seq(sa)
        assert result.extra["verdict"] == "SUCCESS"
        assert result.success is True
        caps = result.extra["capabilities"]
        assert set(caps) == {"TRACe:IQ:STATe?", "TRACe:IQ:SRATe?",
                             "TRACe:IQ:BWIDth?", "TRACe:IQ:RLENgth?"}
        assert all(v["supported"] is True for v in caps.values())
        # 原始回复归档在 raw / extra
        assert caps["TRACe:IQ:SRATe?"]["raw"] == "32000000"
        _assert_read_only(sa)

    def test_rejected_query_form_is_an_answer_not_a_failure(self):
        # SRATe?（推断查询形）被真机拒：STATe? 后队列干净，SRATe? 后回 -113
        sa = _ScriptedSa(dict(_CAP_REPLIES), err_replies=[
            '0,"No error"',                # STATe? 后
            '-113,"Undefined header"',     # SRATe? 后（第 1 条）
            '0,"No error"',                # SRATe? 后（排水到 0）
        ])
        result = _run_seq(sa)
        assert result.extra["verdict"] == "SUCCESS", result.summary
        caps = result.extra["capabilities"]
        assert caps["TRACe:IQ:SRATe?"]["supported"] is False
        assert any("-113" in e for e in caps["TRACe:IQ:SRATe?"]["errors"])
        assert caps["TRACe:IQ:BWIDth?"]["supported"] is True
        assert "被拒 1 条" in result.summary
        _assert_read_only(sa)

    def test_timeout_is_blocker(self):
        sa = _ScriptedSa(dict(_CAP_REPLIES), raise_for={"TRACe:IQ:BWIDth?"})
        result = _run_seq(sa)
        assert result.extra["verdict"] == "BLOCKER"
        assert result.success is False
        assert "TRACe:IQ:BWIDth?" in result.summary

    def test_identity_gate_aborts_before_capability_queries(self):
        sa = _ScriptedSa({"*IDN?": "Keysight Technologies,N9040B,US00000,1.0"})
        result = _run_seq(sa)
        assert result.extra["verdict"] == "ABORTED"
        assert result.success is False
        assert sa.queries == ["*IDN?"], "身份门未过不得再发能力查询"

    def test_residue_makes_undetermined(self):
        # 能力查询各自队列干净，但收尾排水读到残留
        sa = _ScriptedSa(dict(_CAP_REPLIES), err_replies=[
            '0,"No error"', '0,"No error"', '0,"No error"', '0,"No error"',
            '-300,"Device error"', '0,"No error"',   # 收尾残留
        ])
        result = _run_seq(sa)
        assert result.extra["verdict"] == "UNDETERMINED"
        assert result.success is False


# ══ 内审修复门（F1 / F2 / F4）═══════════════════════════════════════════════

class TestDopplerAxisAlignment:
    """内审 F1：doppler real 分支的测量轴必须与参考网格完全同一，
    落库测量轴必须来自驱动返回值（真实生效端）。"""

    @pytest.mark.asyncio
    async def test_service_requests_reference_grid_span_and_persists_measured_axis(
        self, monkeypatch
    ):
        from app.services import channel_calibration_service as mod

        captured = {}

        class _AxisSa:
            async def measure_doppler_spectrum(self, center_freq_hz,
                                               max_doppler_hz, num_bins):
                captured["max_doppler_hz"] = max_doppler_hz
                captured["num_bins"] = num_bins
                # 轴带 0.999 因子模拟仪器夹取后的实际网格 —— 让「落库轴
                # 来自驱动返回值」与「借参考轴」数值可区分（MF2 变异在此红）
                freq = np.linspace(-max_doppler_hz * 0.999,
                                   max_doppler_hz * 0.999, num_bins)
                power = np.linspace(0.0, -30.0, num_bins)
                return freq.tolist(), power.tolist()

        class _Hal:
            drivers = {"signalAnalyzer": _AxisSa()}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service", lambda: _Hal())

        db = MagicMock()
        svc = mod.ChannelCalibrationService(db)
        cal = await svc.run_doppler_calibration(
            velocity_kmh=30.0, fc_ghz=3.5, use_mock=False)

        fd = mod.calculate_doppler_shift(30.0, 3.5)
        # 轴同网格：请求跨度 = 1.1*fd（与参考 linspace(-1.1fd, 1.1fd, 512) 同）
        assert captured["max_doppler_hz"] == pytest.approx(fd * 1.1), \
            "max_doppler_hz 必须是 1.1*fd —— 否则测量轴与参考轴错配、完美信道恒判 fail"
        assert captured["num_bins"] == 512
        # 落库测量轴 = 驱动返回轴（数值上与参考网格一致）
        meas_axis = cal.measured_spectrum["frequency_bins_hz"]
        assert meas_axis[0] == pytest.approx(-fd * 1.1 * 0.999), \
            "落库测量轴必须是驱动返回值（真实生效端），不得借参考轴"
        assert meas_axis[-1] == pytest.approx(fd * 1.1 * 0.999)


class TestTemporalSampleRateWithinManualRange:
    """内审 F4：temporal real 请求采样率必须 ≤ 手册基础范围 45 MHz
    （1176.7510.02─13；超范围行为未载，赌不得）。"""

    @pytest.mark.asyncio
    async def test_requested_resolution_keeps_fs_within_45mhz(self, monkeypatch):
        from app.services import channel_calibration_service as mod

        captured = {}

        class _CapturedStop(Exception):
            pass

        class _PdpSa:
            async def measure_pdp(self, center_freq_hz, max_delay_ns,
                                  resolution_ns):
                captured["resolution_ns"] = resolution_ns
                raise _CapturedStop()  # 门主题=请求参数，短路下游流程

        class _Hal:
            drivers = {"signalAnalyzer": _PdpSa()}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service", lambda: _Hal())

        db = MagicMock()
        svc = mod.ChannelCalibrationService(db)
        with pytest.raises(_CapturedStop):
            await svc.run_temporal_calibration(
                scenario_type='UMa', scenario_condition='NLOS',
                fc_ghz=3.5, use_mock=False)
        fs_mhz = 1e3 / captured["resolution_ns"]
        assert fs_mhz <= 45.0, \
            f"请求采样率 {fs_mhz} MHz 超手册基础范围 45 MHz（F4）"


class TestCaptureConcurrencyMutex:
    """内审 F2：采集事务持锁期间，其它线程的单条查询不得插进 IQ 命令序列。"""

    def test_concurrent_query_does_not_interleave_capture(self):
        import threading as _th
        sess = _FakeFsvaSession(srate_reply="32000000",
                                scenario=_two_tap_scenario)
        d = _mk_driver(sess)
        started = _th.Event()
        release = _th.Event()
        orig_q = d._query

        def _slow_q(cmd, **kw):
            r = orig_q(cmd, **kw)
            if cmd.strip() == FsvaScpi.IQ_DATA_QUERY:
                # 挂在命令返回**之后**（_do_query 的锁已释放）——此刻只有
                # 事务级 wrapper 锁还持着；去掉 wrapper（MF4 变异）探针
                # 立即插入，本门变红。
                started.set()
                release.wait(timeout=5)
            return r

        d._query = _slow_q

        def _capture():
            try:
                d._measure_pdp_sync(3.5e9, 2000.0, 31.25)
            except Exception:
                pass  # 数据契约不是本门主题，互斥才是

        t1 = _th.Thread(target=_capture)
        t1.start()
        assert started.wait(timeout=5), "采集未走到 DATA? 步骤"
        # 采集持锁挂起中：读/写探针必须**立即失败**（复核 F1 fail-fast，
        # 不冻结、不插队）——去掉事务 wrapper（MF4 变异）时命令间隙锁全空，
        # 探针会成功，本门变红。
        probe_results = {}

        def _probe():
            try:
                orig_q("SYST:ERR?")  # 绕过 slow 包装，直接走基类锁路径
                probe_results["query"] = "ok"
            except RuntimeError as e:
                probe_results["query"] = str(e)
            try:
                d._write("INIT:CONT OFF")  # 写路径锁门（复核 F3）
                probe_results["write"] = "ok"
            except RuntimeError as e:
                probe_results["write"] = str(e)

        t2 = _th.Thread(target=_probe)
        t2.start()
        t2.join(timeout=5)
        assert "独占" in probe_results.get("query", "ok"), \
            "采集事务持锁期间读探针未被 fail-fast 拒绝"
        assert "独占" in probe_results.get("write", "ok"), \
            "采集事务持锁期间写探针未被 fail-fast 拒绝 —— _do_write 锁缺失"
        release.set()
        t1.join(timeout=10)
        # 采集结束后同样调用必须成功（锁已释放）
        orig_q("SYST:ERR?")
        # wire 门：探针命令没进过采集序列
        assert "INIT:CONT OFF" not in sess.written, \
            "被拒的写探针不该到达仪器"


class TestToThreadEventLoopLiveness:
    """复核 F3：async 壳必须真的走 to_thread —— 采集挂起期间事件循环
    仍能推进（MV-A 变异：去掉 to_thread 直接同步调用，在这红）。"""

    @pytest.mark.asyncio
    async def test_event_loop_alive_during_capture(self):
        import time as _time
        sess = _FakeFsvaSession(srate_reply="32000000",
                                scenario=_two_tap_scenario)
        d = _mk_driver(sess)
        orig_q = d._query

        ticks = []
        window = {}

        def _slow_q2(cmd, **kw):
            r = orig_q(cmd, **kw)
            if cmd.strip() == FsvaScpi.IQ_DATA_QUERY:
                window["before"] = len(ticks)
                _time.sleep(0.4)  # 模拟长采集（同步侧挂起窗口）
                window["after"] = len(ticks)
            return r

        d._query = _slow_q2

        async def _tick():
            for _ in range(20):
                ticks.append(1)
                await asyncio.sleep(0.03)

        results = await asyncio.gather(
            d.measure_pdp(3.5e9, 2000.0, 31.25), _tick(),
            return_exceptions=True)
        assert not isinstance(results[0], Exception), results[0]
        # 判据打在挂起窗口**期间**的 tick 增量：to_thread 下事件循环另一
        # 线程照常推进（增量 > 0）；同步直调（MV-A 变异）时事件循环被冻，
        # 窗口内增量恒 0 —— 首版断言只数总量，采集后补跑照样凑满，是假门。
        assert window.get("after", 0) - window.get("before", 0) > 0, \
            "采集挂起窗口内事件循环零推进 —— to_thread 缺失"
