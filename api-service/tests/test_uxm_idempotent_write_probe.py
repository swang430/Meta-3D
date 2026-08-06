"""P1-46: UXM ON 态同值写诊断剧本的安全门与证据边界。"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.diagnostics import loader
from app.diagnostics.sequences import uxm_idempotent_write_probe as seq
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)


class _IratProfileWithSentinelErr(UxmLteNrIratProfile):
    """让测试能发现实现是否硬编码了 SYST:ERR?。"""

    ERR = "SENTINEL:ERR?"


class _FakeBs:
    def __init__(self, *, profile=UxmLteNrIratProfile, switch="1",
                 band="N78", status="CONNected", status_after=None,
                 status_sequence=None, raise_on_status_call=None,
                 band_sequence=None, raise_on_band_call=None,
                 raise_on_write=None, err='0,"No error"', clock=None,
                 err_delay_s=0):
        self._cmds = profile
        self._responses = {
            profile.ERR: list(err) if isinstance(err, (list, tuple)) else [err]
        }
        self._status_query = None
        self._status_calls = 0
        self._raise_on_status_call = raise_on_status_call
        self._band_query = None
        self._band_calls = 0
        self._raise_on_band_call = raise_on_band_call
        self._raise_on_write = raise_on_write
        self._clock = clock
        self._err_delay_s = err_delay_s
        if profile.CELL_STATE_QUERY:
            self._responses[profile.CELL_STATE_QUERY.format(
                cell=profile.PRIMARY_CELL)] = [switch]
        if profile.CELL_BAND:
            self._band_query = profile.CELL_BAND.format(
                cell=profile.PRIMARY_CELL) + "?"
            self._responses[self._band_query] = (
                list(band_sequence) if band_sequence is not None else [band, band]
            )
        if profile.CELL_STATUS_QUERY:
            self._status_query = profile.CELL_STATUS_QUERY.format(
                cell=profile.PRIMARY_CELL)
            self._responses[self._status_query] = (
                list(status_sequence) if status_sequence is not None else
                [status, status if status_after is None else status_after]
            )
        self.ops: list[tuple[str, str]] = []

    def _query(self, cmd):
        self.ops.append(("Q", cmd))
        if cmd == self._cmds.ERR and self._clock is not None:
            self._clock.advance(self._err_delay_s)
        if cmd == self._status_query:
            self._status_calls += 1
            if self._status_calls == self._raise_on_status_call:
                raise TimeoutError("status timeout")
        if cmd == self._band_query:
            self._band_calls += 1
            if self._band_calls == self._raise_on_band_call:
                raise TimeoutError("band timeout")
        values = self._responses.get(cmd, [""])
        return values.pop(0) if len(values) > 1 else values[0]

    def _write(self, cmd):
        self.ops.append(("W", cmd))
        if self._raise_on_write is not None:
            raise self._raise_on_write


def _run(bs, params=None):
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}
    return asyncio.run(seq.run(
        MagicMock(), hal, params or {}, log=lambda *_: None,
    ))


class _FakeClock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    clock = _FakeClock()

    async def _advance(seconds):
        clock.advance(seconds)

    monkeypatch.setattr(seq.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(seq.asyncio, "sleep", _advance)
    return clock


def test_loader_discovers_sequence_and_marks_it_unsafe():
    loader.reset_cache()
    entries = {item["key"]: item for item in loader.list_sequences()}
    assert "uxm_idempotent_write_probe" in entries
    assert entries["uxm_idempotent_write_probe"]["safe_during_test"] is False
    assert entries["uxm_idempotent_write_probe"]["required_categories"] == ["baseStation"]


def test_connected_on_cell_writes_same_band_then_collects_raw_observations():
    """mock 只证明剧本顺序/分支，不证明真机接受或业务闭环。"""
    bs = _FakeBs(profile=_IratProfileWithSentinelErr)

    result = _run(bs, {"stability_window_s": 2, "poll_interval_s": 1})

    cell = _IratProfileWithSentinelErr.PRIMARY_CELL
    band = _IratProfileWithSentinelErr.CELL_BAND.format(cell=cell)
    expected = [
        ("Q", "SENTINEL:ERR?"),
        ("Q", _IratProfileWithSentinelErr.CELL_STATE_QUERY.format(cell=cell)),
        ("Q", band + "?"),
        ("Q", _IratProfileWithSentinelErr.CELL_STATUS_QUERY.format(cell=cell)),
        ("Q", "SENTINEL:ERR?"),
        ("W", band + " N78"),
        ("Q", "SENTINEL:ERR?"),
        ("Q", _IratProfileWithSentinelErr.CELL_STATUS_QUERY.format(cell=cell)),
        ("Q", _IratProfileWithSentinelErr.CELL_STATUS_QUERY.format(cell=cell)),
        ("Q", _IratProfileWithSentinelErr.CELL_STATUS_QUERY.format(cell=cell)),
        ("Q", band + "?"),
    ]
    assert bs.ops == expected
    assert all(step.success for step in result.steps), "剧本执行步骤可成功"
    assert result.success is False, "缺 IRAT 手册适用范围时绝不能正式判绿"
    assert result.extra["formal_verdict"] in {"unknown", "unverified"}
    assert result.extra["command_evidence"]["classification"] == "unverified"
    assert result.extra["command_evidence"]["scope"] == "manual_scope_mismatch"
    assert result.extra["command_evidence"]["manual_nr_band_range"] == "not_specified"
    assert result.extra["command_evidence"]["accepted_band_shape_basis"] == "production-driver"
    assert result.extra["coverage"]["band"]["covered"] is True
    assert result.extra["coverage"]["duplex"]["covered"] is False
    assert "生产驱动未使用" in result.extra["coverage"]["duplex"]["reason"]
    assert all("DUPLEX" not in cmd.upper() for _, cmd in bs.ops)
    assert result.extra["observation_window"]["mode"] == "bounded_stability"
    assert result.extra["observation_window"]["planned_samples"] == 3
    assert result.extra["observation_window"]["completed_samples"] == 3
    assert result.extra["observation_window"]["stable"] is True
    assert result.extra["observation_window"]["actual_elapsed_s"] == 2
    assert [s["actual_elapsed_s"] for s in
            result.extra["observation_window"]["samples"]] == [0, 1, 2]
    assert [s.raw for s in result.steps if s.raw is not None] == [
        '0,"No error"', "1", "N78", "CONNected",
        '0,"No error"', '0,"No error"',
        "CONNected", "CONNected", "CONNected", "N78",
    ]


@pytest.mark.parametrize("status", [
    "OFF", "ON", "IDLE", "", "ATT", "ATTACHED", "AGGR", "AGGREGATED",
    "ACT", "ACTIVATED",
])
def test_non_connected_protocol_state_never_writes(status):
    bs = _FakeBs(status=status)

    result = _run(bs)

    assert result.success is False
    assert not any(kind == "W" for kind, _ in bs.ops)
    assert len(bs.ops) == 5, "排空 ERR、读三前置项、查写前 ERR 后才决定不动作"


def test_cell_switch_off_never_writes_even_if_protocol_text_looks_connected():
    bs = _FakeBs(switch="0", status="CONNected")

    result = _run(bs)

    assert result.success is False
    assert not any(kind == "W" for kind, _ in bs.ops)
    assert len(bs.ops) == 5


@pytest.mark.parametrize("status", ["CONN", "CONNECTED", "CONNected"])
def test_only_explicit_connected_status_tokens_allow_probe(status):
    bs = _FakeBs(status=status)

    result = _run(bs)

    assert any(kind == "W" for kind, _ in bs.ops)
    assert result.extra["coverage"]["band"]["covered"] is True


@pytest.mark.parametrize("band", [
    "", "-113,Undefined header", "N78 extra", "N0", "N1000",
    "1", "78", "255", "256", "78 79", "+78",
])
def test_invalid_band_readback_never_becomes_a_write_argument(band):
    """错误文本/越界值/带空格回复绝不能被直接拼进写命令。"""
    bs = _FakeBs(band=band)

    result = _run(bs)

    assert result.success is False
    assert not any(kind == "W" for kind, _ in bs.ops)
    assert len(bs.ops) == 5


@pytest.mark.parametrize("band", ["N1", "N78", "N255", "N999"])
def test_only_n_prefixed_production_shape_is_accepted(band):
    bs = _FakeBs(band=band)

    _run(bs)

    writes = [cmd for kind, cmd in bs.ops if kind == "W"]
    assert len(writes) == 1
    assert writes[0].endswith(" " + band)


@pytest.mark.parametrize("cell", ["CELL0", "CELL15", "CELL999", "CELL-1"])
def test_cell_outside_manual_range_is_refused_without_scpi(cell):
    bs = _FakeBs()

    result = _run(bs, {"cell": cell})

    assert result.success is False
    assert bs.ops == []


@pytest.mark.parametrize("cell", ["CELL1", "CELL14"])
def test_cell_manual_range_boundaries_are_allowed(cell):
    bs = _FakeBs()
    default = UxmLteNrIratProfile.PRIMARY_CELL
    if cell != default:
        bs._responses = {
            key.replace(default, cell): values
            for key, values in bs._responses.items()
        }

    result = _run(bs, {"cell": cell})

    assert any(kind == "W" for kind, _ in bs.ops)
    assert result.extra["cell"] == cell


def test_immediate_protocol_degradation_marks_execution_incomplete():
    bs = _FakeBs(status="CONNected", status_after="ON")

    result = _run(bs)

    assert result.success is False
    assert result.extra["execution"]["remained_connected"] is False
    assert result.extra["execution"]["completed"] is False


def test_initial_stale_errors_are_boundedly_drained_before_preflight():
    bs = _FakeBs(err=[
        '-200,"stale one"', '-221,"stale two"', '0,"No error"',
        '0,"No error"', '0,"No error"',
    ])

    result = _run(bs, {"stability_window_s": 1, "poll_interval_s": 1})

    assert any(kind == "W" for kind, _ in bs.ops)
    assert result.extra["initial_error_queue"]["cleared"] is True
    assert result.extra["initial_error_queue"]["raw"] == [
        '-200,"stale one"', '-221,"stale two"', '0,"No error"',
    ]
    assert result.extra["prewrite_error_baseline"]["raw"] == '0,"No error"'


def test_initial_error_queue_that_never_reaches_zero_is_bounded_and_never_writes():
    bs = _FakeBs(err=['-200,"still stale"'] * 10)

    result = _run(bs)

    err_queries = [cmd for kind, cmd in bs.ops
                   if kind == "Q" and cmd == UxmLteNrIratProfile.ERR]
    assert len(err_queries) == seq._MAX_INITIAL_ERR_DRAIN
    assert not any(kind == "W" for kind, _ in bs.ops)
    assert all(cmd == UxmLteNrIratProfile.ERR for _, cmd in bs.ops)
    assert result.extra["initial_error_queue"]["cleared"] is False


def test_prewrite_error_baseline_must_be_clean_on_its_first_read():
    bs = _FakeBs(err=[
        '0,"No error"', '-113,"preflight query error"', '0,"No error"',
    ])

    result = _run(bs)

    assert not any(kind == "W" for kind, _ in bs.ops)
    assert result.extra["prewrite_error_baseline"] == {
        "raw": '-113,"preflight query error"',
        "code": -113,
        "clean": False,
    }
    assert "写前" in result.summary


def test_postwrite_error_is_attributed_to_the_single_band_write():
    bs = _FakeBs(err=[
        '0,"No error"', '0,"No error"', '-222,"write rejected"',
    ])

    result = _run(bs, {"stability_window_s": 1, "poll_interval_s": 1})

    writes = [cmd for kind, cmd in bs.ops if kind == "W"]
    assert len(writes) == 1
    assert result.extra["initial_error_queue"]["cleared"] is True
    assert result.extra["prewrite_error_baseline"]["clean"] is True
    assert result.extra["execution"]["error_code"] == -222
    assert result.extra["observations"]["after_error_queue"] == '-222,"write rejected"'
    assert result.extra["execution"]["completed"] is False


def test_connected_then_delayed_off_is_detected_inside_stability_window():
    bs = _FakeBs(status_sequence=["CONN", "CONN", "OFF"])

    result = _run(bs, {"stability_window_s": 5, "poll_interval_s": 1})

    window = result.extra["observation_window"]
    assert window["planned_samples"] == 6
    assert window["completed_samples"] == 2
    assert [sample["raw"] for sample in window["samples"]] == ["CONN", "OFF"]
    assert window["disconnection_observed"] is True
    assert window["stable"] is False
    assert result.extra["execution"]["completed"] is False
    assert result.extra["coverage"]["band"]["covered"] is False


def test_status_query_failure_never_counts_as_stable_or_covered():
    # 第 1 次 status 是动作前；第 3 次是稳定窗口的第 2 个样本。
    bs = _FakeBs(status="CONN", raise_on_status_call=3)

    result = _run(bs, {"stability_window_s": 2, "poll_interval_s": 1})

    window = result.extra["observation_window"]
    assert window["completed_samples"] == 2
    assert window["samples"][-1]["raw"] is None
    assert window["samples"][-1]["query_ok"] is False
    assert window["stable"] is False
    assert result.extra["execution"]["completed"] is False
    assert result.extra["coverage"]["band"]["covered"] is False


def test_postwrite_band_mismatch_never_counts_as_complete_or_covered():
    bs = _FakeBs(band_sequence=["N78", "N77"])

    result = _run(bs, {"stability_window_s": 2, "poll_interval_s": 1})

    assert result.extra["observations"]["before_band"] == "N78"
    assert result.extra["observations"]["after_band"] == "N77"
    assert result.extra["execution"]["band_unchanged"] is False
    assert result.extra["execution"]["completed"] is False
    assert result.extra["coverage"]["band"]["covered"] is False


@pytest.mark.parametrize("postwrite_band", ["", TimeoutError("band timeout")])
def test_postwrite_band_missing_or_query_failure_never_counts_as_covered(
    postwrite_band,
):
    if isinstance(postwrite_band, BaseException):
        bs = _FakeBs(raise_on_band_call=2)
    else:
        bs = _FakeBs(band_sequence=["N78", postwrite_band])

    result = _run(bs, {"stability_window_s": 2, "poll_interval_s": 1})

    assert result.extra["execution"]["completed"] is False
    assert result.extra["coverage"]["band"]["covered"] is False
    postwrite_step = next(
        step for step in result.steps if step.label == "动作后：BAND 回读"
    )
    assert postwrite_step.success is False


def test_write_exception_returns_failed_action_without_postwrite_coverage():
    bs = _FakeBs(raise_on_write=RuntimeError("write exploded"))

    result = _run(bs)

    assert result.success is False
    assert result.extra["coverage"]["band"]["covered"] is False
    assert "execution" not in result.extra
    action = next(step for step in result.steps if step.label.startswith("动作："))
    assert action.success is False
    assert "write exploded" in action.detail
    assert not any(step.label.startswith("动作后：") for step in result.steps)


def test_write_cancellation_propagates_instead_of_becoming_a_failed_result():
    bs = _FakeBs(raise_on_write=asyncio.CancelledError())
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}

    async def _exercise():
        with pytest.raises(asyncio.CancelledError):
            await seq.run(MagicMock(), hal, {}, log=lambda *_: None)

    asyncio.run(_exercise())


def test_err_query_delay_is_reflected_in_first_status_elapsed(fake_clock):
    bs = _FakeBs(status="CONN", clock=fake_clock, err_delay_s=0.4)

    result = _run(bs, {"stability_window_s": 2, "poll_interval_s": 1})

    window = result.extra["observation_window"]
    assert window["samples"][0]["actual_elapsed_s"] == pytest.approx(0.4)
    assert [sample["actual_elapsed_s"] for sample in window["samples"]] == pytest.approx(
        [0.4, 1.0, 2.0]
    )
    assert window["gap_limit_s"] == pytest.approx(1.05)
    assert window["max_gap_s"] == pytest.approx(1.0)
    assert window["blind_window_exceeded"] is False
    assert window["stable"] is True
    assert "ERR" in window["limitation"]


@pytest.mark.parametrize("err_delay,window_s", [(1.2, 2), (7.6, 5)])
def test_err_blind_window_cannot_be_hidden_by_instant_catch_up_samples(
    fake_clock, err_delay, window_s,
):
    bs = _FakeBs(status="CONN", clock=fake_clock, err_delay_s=err_delay)

    result = _run(bs, {
        "stability_window_s": window_s,
        "poll_interval_s": 1,
    })

    window = result.extra["observation_window"]
    assert window["completed_samples"] == window["planned_samples"]
    assert window["actual_elapsed_s"] >= window_s
    assert window["max_gap_s"] == pytest.approx(err_delay)
    assert window["gap_limit_s"] == pytest.approx(1.05)
    assert window["blind_window_exceeded"] is True
    assert window["stable"] is False
    assert result.extra["execution"]["completed"] is False
    assert result.extra["coverage"]["band"]["covered"] is False


def test_adjacent_sample_gap_over_interval_tolerance_is_not_stable(
    monkeypatch, fake_clock,
):
    async def _oversleep(seconds):
        fake_clock.advance(seconds + 0.2)
    monkeypatch.setattr(seq.asyncio, "sleep", _oversleep)
    bs = _FakeBs(status="CONN")

    result = _run(bs, {"stability_window_s": 2, "poll_interval_s": 1})

    window = result.extra["observation_window"]
    assert window["max_gap_s"] == pytest.approx(1.2)
    assert window["blind_window_exceeded"] is True
    assert window["stable"] is False
    assert result.extra["execution"]["completed"] is False


def test_planned_samples_without_actual_window_elapsed_are_not_complete(
    monkeypatch,
):
    async def _sleep_without_advancing(_seconds):
        return None
    monkeypatch.setattr(seq.asyncio, "sleep", _sleep_without_advancing)
    bs = _FakeBs(status="CONN")

    result = _run(bs, {"stability_window_s": 2, "poll_interval_s": 1})

    window = result.extra["observation_window"]
    assert window["completed_samples"] == window["planned_samples"] == 3
    assert window["actual_elapsed_s"] == 0
    assert window["stable"] is False
    assert result.extra["execution"]["completed"] is False
    assert result.extra["coverage"]["band"]["covered"] is False


@pytest.mark.parametrize("params", [
    {"stability_window_s": 0, "poll_interval_s": 1},
    {"stability_window_s": 31, "poll_interval_s": 1},
    {"stability_window_s": float("nan"), "poll_interval_s": 1},
    {"stability_window_s": float("inf"), "poll_interval_s": 1},
    {"stability_window_s": 5, "poll_interval_s": 0},
    {"stability_window_s": 5, "poll_interval_s": 6},
    {"stability_window_s": 1, "poll_interval_s": 2},
    {"stability_window_s": 30, "poll_interval_s": 0.1},
    {"stability_window_s": True, "poll_interval_s": 1},
])
def test_invalid_stability_window_is_refused_before_scpi(params):
    bs = _FakeBs()

    result = _run(bs, params)

    assert result.success is False
    assert "参数" in result.summary
    assert bs.ops == []


def test_wrong_dialect_is_refused_without_any_scpi_io():
    bs = _FakeBs(profile=Uxm5GNRTestAppProfile)

    result = _run(bs)

    assert result.success is False
    assert "LTE_NR_IRAT" in result.summary
    assert bs.ops == []


@pytest.mark.parametrize("classification", ["unverified", "onsite-observed"])
def test_non_confirmed_evidence_can_never_formally_green(classification):
    """变异：把 unverified/onsite-observed 放进绿色白名单会红。"""
    assert seq._evidence_allows_formal_green(
        classification=classification,
        scope="LTE_NR_IRAT",
    ) is False


def test_manual_scope_mismatch_can_never_formally_green():
    assert seq._evidence_allows_formal_green(
        classification="confirmed",
        scope="manual_scope_mismatch",
    ) is False
