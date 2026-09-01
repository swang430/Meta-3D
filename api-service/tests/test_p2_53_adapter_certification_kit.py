"""P2-53：三方（uxm / cmw500 / certfake）跑同一套 adapter 认证模板。

- 模板与第三 adapter 夹具在 ``tests/base_station_certification_kit.py``；
- uxm / cmw500 的既有认证测试**原样保留**（G5/G6 精神），本文件是收敛入口；
- ``certfake`` 走完全套模板 = 「HAL/manifest/计划/MEASURE 原生窗口只需五件套」的
  行为证明；正式 binding 与 evidence 封闭枚举另登记平台缺口；泄漏门
  （本文件末）确保 certfake 永不进入生产代码。
"""

from __future__ import annotations

from tests.base_station_mock_factory import registered_mock_base_station

import itertools
from pathlib import Path

import pytest

from app.hal.base_station import (
    BaseStationRequestedConfig,
    MockBaseStation,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from tests.base_station_certification_kit import (
    AdapterCertificationSubject,
    CERTFAKE_SAMPLE_PROFILE,
    CertFakeAdapterProfile,
    CertFakeBaseStationDriver,
    ScriptedScpiSession,
    certify_attach_stage_truth,
    certify_attach_timeout_returns_receipt,
    certify_cancellation_propagates,
    certify_common_consumer_native_window,
    certify_error_queue_consultation,
    certify_execution_plan_neutrality,
    certify_fake_transport_exchange_provenance,
    certify_measurement_window_contract,
    certify_metric_registry_trust,
    certify_partial_readback_receipt,
    certify_registration_gate,
    certify_release_token_boundary,
    certify_safe_idle_boundary,
    certify_simulated_exclusion,
)
from tests.test_p1_73b_cmw_state_machine import (
    _StateDriver,
    _complete_config_responses,
    _requested_config as _cmw_requested_config,
)
from tests.test_p1_73b_cmw_extended_bler_window import _WindowDriver
from tests.test_uxm_cell_config_orchestration import (
    _requested_nr_config as _uxm_requested_config,
    wire_echo_visa,
)


# ═══════════════════════════════════════════════════════════════════
# uxm subject（fake 形态收编自 test_p02 / test_p2_47 / test_p2_52 / P1-19）
# ═══════════════════════════════════════════════════════════════════

_UXM_BASE_REPLIES = {
    "*OPC?": "1",
    "SYSTem:ERRor?": '0,"No error"',
}


def _uxm_driver(replies: dict[str, str]) -> RealUxmDriver:
    driver = RealUxmDriver("uxm-kit", {"ip": "192.0.2.1", "uxm_profile": "irat"})
    driver._visa_session = ScriptedScpiSession({**_UXM_BASE_REPLIES, **replies})
    return driver


def _uxm_window_driver() -> RealUxmDriver:
    # test_p2_52:354 成因门形态：只桩最底层 _do_*，wire 记账走真实传输模板。
    driver = RealUxmDriver("uxm-kit", {"ip": "192.0.2.1", "uxm_profile": "irat"})
    driver._visa_session = object()
    driver._do_write = lambda cmd: None
    driver._do_query = lambda cmd: "0"
    return driver


def _uxm_partial_driver() -> RealUxmDriver:
    driver = RealUxmDriver("uxm-kit", {"ip": "10.0.0.2", "uxm_profile": "irat"})
    wire_echo_visa(driver)
    return driver


def _uxm_rejected_driver() -> RealUxmDriver:
    # cell_active=True 让编排走 ON 态 APPLY 分支（P0-2 D2），APPLY 后必查
    # 错误队列（uxm_base_station.py L2339）；ERR 恒 -113 = 仪器拒绝形态。
    driver = RealUxmDriver("uxm-kit", {"ip": "10.0.0.2", "uxm_profile": "irat"})
    wire_echo_visa(
        driver,
        cell_active=True,
        overrides={"SYSTem:ERRor": '-113,"Undefined header"'},
    )
    return driver


def _uxm_release_driver() -> RealUxmDriver:
    from app.hal.base import InstrumentStatus

    driver = _uxm_driver({"BSE:STATus:NR5G": "OFF"})
    driver._session_token = "kit-uxm-session"
    driver._status = InstrumentStatus.CONNECTED
    return driver


def _uxm_recorded_queries(driver) -> list:
    session = driver._visa_session
    query = getattr(session, "query", None)
    if hasattr(query, "call_args_list"):
        # wire_echo_visa 的 MagicMock 会把 .queried 自动生成为空可迭代 mock，
        # 必须先认 mock 的调用记录，否则真实查询记录被空 mock 挡住。
        return [call.args[0] for call in query.call_args_list]
    return list(session.queried)


def _uxm_subject() -> AdapterCertificationSubject:
    return AdapterCertificationSubject(
        label="uxm",
        model_name="UXM 5G E7515B",
        driver_class=RealUxmDriver,
        profile_model=None,
        sample_profile=None,
        error_queue_command="SYSTem:ERRor?",
        sleep_patch_target="app.hal.uxm_base_station.asyncio.sleep",
        expect_attach_formally_confirmed=False,
        expect_window_formally_confirmed=False,
        requested_config=_uxm_requested_config(),
        build_offline_driver=lambda: _uxm_driver({"BSE:STATus:NR5G": "IDLE"}),
        build_attach_ready_driver=lambda: _uxm_driver(
            {"BSE:STATus:NR5G": "CONNected"}
        ),
        build_attach_never_ready_driver=lambda: _uxm_driver(
            {"BSE:STATus:NR5G": "IDLE"}
        ),
        build_cancelled_attach_driver=lambda: _uxm_driver(
            {"BSE:STATus:NR5G": "IDLE"}
        ),
        build_window_driver=_uxm_window_driver,
        build_partial_config_driver=_uxm_partial_driver,
        build_rejected_config_driver=_uxm_rejected_driver,
        build_safe_idle_driver=lambda confirmed: _uxm_driver(
            {"BSE:STATus:NR5G": "OFF" if confirmed else "GARBAGE"}
        ),
        build_release_driver=_uxm_release_driver,
        build_simulated_driver=lambda: registered_mock_base_station(
            "mock-uxm", {"model": "UXM 5G E7515B"}
        ),
        transport_probe=lambda driver: driver.get_cell_state(),
        get_recorded_queries=_uxm_recorded_queries,
    )


# ═══════════════════════════════════════════════════════════════════
# cmw500 subject（fake 形态收编自 test_p1_73b / test_p2_47 / test_p1_73c）
# ═══════════════════════════════════════════════════════════════════


def _cmw_attach_driver(states) -> _StateDriver:
    iterator = iter(states)

    class _AttachDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            if command in {
                "SOURce:LTE:SIGN1:CELL:STATe:ALL?",
                "FETCh:LTE:SIGN1:PSWitched:STATe?",
            }:
                self.queries.append(command)
                return next(iterator)
            return super()._do_query(command)

    return _AttachDriver({"*OPC?": "1", "SYSTem:ERRor:ALL?": '0,"No error"'})


def _cmw_rejected_driver() -> _StateDriver:
    errors = itertools.chain(
        ['0,"No error"'], itertools.repeat('-221,"Settings conflict"')
    )

    class _RejectedConfigDriver(_StateDriver):
        def _do_query(self, command: str) -> str:
            if command == "SYSTem:ERRor:ALL?":
                self.queries.append(command)
                return next(errors)
            return super()._do_query(command)

    return _RejectedConfigDriver(
        {
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
            "*OPC?": "1",
        }
    )


def _cmw_release_driver() -> _StateDriver:
    driver = _StateDriver(
        {
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
            "*OPC?": "1",
            "SYSTem:ERRor:ALL?": '0,"No error"',
        }
    )
    driver._session_token = "kit-cmw-session"
    return driver


def _cmw_subject() -> AdapterCertificationSubject:
    return AdapterCertificationSubject(
        label="cmw500",
        model_name="CMW500",
        driver_class=RealCmw500Driver,
        profile_model=RealCmw500Driver.adapter_profile_model,
        sample_profile={
            "schema_version": 1,
            "adapter": "cmw500",
            "lte_2x2_internal_route": {
                "pcc_bb_board": "BB1",
                "rx_connector": "RF1C",
                "rx_converter": "RX1",
                "tx1_connector": "RF1C",
                "tx1_converter": "TX1",
                "tx2_connector": "RF2C",
                "tx2_converter": "TX2",
            },
        },
        error_queue_command="SYSTem:ERRor:ALL?",
        sleep_patch_target="app.hal.cmw500_base_station.asyncio.sleep",
        expect_attach_formally_confirmed=True,
        expect_window_formally_confirmed=True,
        requested_config=_cmw_requested_config(),
        build_offline_driver=lambda: _StateDriver(
            {
                "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
                "*OPC?": "1",
                "SYSTem:ERRor:ALL?": '0,"No error"',
            }
        ),
        build_attach_ready_driver=lambda: _cmw_attach_driver(
            ["ON,ADJ", "ATT", "CEST"]
        ),
        # cell ON 但 PS 停在 ATTached、永不 CESTablished → 轮询 + sleep 到超时
        build_attach_never_ready_driver=lambda: _cmw_attach_driver(
            itertools.cycle(["ON,ADJ", "ATT"])
        ),
        build_cancelled_attach_driver=lambda: _cmw_attach_driver(
            ["ON,ADJ", "OFF,ADJ", "OFF,ADJ"]
        ),
        build_window_driver=lambda: _WindowDriver(
            states=["OFF", "RUN", "RUN", "RDY", "OFF"]
        ),
        build_partial_config_driver=lambda: _StateDriver(
            _complete_config_responses()
        ),
        build_rejected_config_driver=_cmw_rejected_driver,
        build_safe_idle_driver=lambda confirmed: _StateDriver(
            {
                "SOURce:LTE:SIGN1:CELL:STATe:ALL?": (
                    "OFF,ADJ" if confirmed else "UNKNOWN,ADJ"
                ),
                "*OPC?": "1",
                "SYSTem:ERRor:ALL?": '0,"No error"',
            }
        ),
        build_release_driver=_cmw_release_driver,
        build_simulated_driver=lambda: registered_mock_base_station(
            "mock-cmw", {"model": "CMW500"}
        ),
        transport_probe=lambda driver: driver.get_cell_state(),
        get_recorded_queries=lambda driver: list(driver.queries),
    )


# ═══════════════════════════════════════════════════════════════════
# certfake subject（第三 adapter：全部构造器由夹具自带）
# ═══════════════════════════════════════════════════════════════════


def _certfake_requested_config() -> BaseStationRequestedConfig:
    return BaseStationRequestedConfig(
        radio_technology="nr5g",
        channel_kind="nr_arfcn",
        frequency_mhz=3500.0,
        bandwidth_mhz=100.0,
        band="n78",
        duplex="tdd",
        nr_arfcn=632628,
        lte_dl_earfcn=None,
        lte_transmission_mode=None,
        subcarrier_spacing_khz=30,
        mimo_layers=2,
        downlink_power_dbm=-50.0,
    )


def _certfake(**kwargs) -> CertFakeBaseStationDriver:
    return CertFakeBaseStationDriver("certfake-kit", {"ip": "192.0.2.99"}, **kwargs)


def _certfake_subject() -> AdapterCertificationSubject:
    return AdapterCertificationSubject(
        label="certfake",
        model_name="CERTFAKE-3000",
        driver_class=CertFakeBaseStationDriver,
        profile_model=CertFakeAdapterProfile,
        sample_profile=dict(CERTFAKE_SAMPLE_PROFILE),
        error_queue_command="SYST:ERR?",
        sleep_patch_target="tests.base_station_certification_kit.asyncio.sleep",
        expect_attach_formally_confirmed=True,
        expect_window_formally_confirmed=True,
        requested_config=_certfake_requested_config(),
        build_offline_driver=lambda: _certfake(),
        build_attach_ready_driver=lambda: _certfake(),
        build_attach_never_ready_driver=lambda: _certfake(
            attach_script=("IDLE",)
        ),
        build_cancelled_attach_driver=lambda: _certfake(
            attach_script=("IDLE",)
        ),
        build_window_driver=lambda: _certfake(),
        build_partial_config_driver=lambda: _certfake(),
        build_rejected_config_driver=lambda: _certfake(
            reject_writes=("CERT:CONF:BWIDth",)
        ),
        build_safe_idle_driver=lambda confirmed: _certfake(
            cell_state_reply="OFF" if confirmed else "GARBAGE"
        ),
        build_release_driver=lambda: _certfake(),
        build_simulated_driver=lambda: _certfake(simulated=True),
        transport_probe=lambda driver: driver.get_cell_state(),
        get_recorded_queries=lambda driver: list(driver.queries),
    )


_SUBJECT_FACTORIES = {
    "uxm": _uxm_subject,
    "cmw500": _cmw_subject,
    "certfake": _certfake_subject,
}


@pytest.fixture(params=sorted(_SUBJECT_FACTORIES), ids=sorted(_SUBJECT_FACTORIES))
def subject(request) -> AdapterCertificationSubject:
    return _SUBJECT_FACTORIES[request.param]()


# ═══════════════════════════════════════════════════════════════════
# 十类维度 × 三 adapter
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dimension_01_fake_transport(subject):
    await certify_fake_transport_exchange_provenance(subject)


@pytest.mark.asyncio
async def test_dimension_02_partial_readback(subject):
    await certify_partial_readback_receipt(subject)


@pytest.mark.asyncio
async def test_dimension_03_error_queue(subject):
    await certify_error_queue_consultation(subject)


@pytest.mark.asyncio
async def test_dimension_04a_attach_timeout(subject):
    await certify_attach_timeout_returns_receipt(subject)


@pytest.mark.asyncio
async def test_dimension_04b_cancellation(subject):
    await certify_cancellation_propagates(subject)


@pytest.mark.asyncio
async def test_dimension_05_attach_stages(subject):
    await certify_attach_stage_truth(subject)


@pytest.mark.asyncio
async def test_dimension_06_measurement_window(subject):
    await certify_measurement_window_contract(subject)


def test_dimension_07_per_metric_trust(subject):
    certify_metric_registry_trust(subject)


@pytest.mark.asyncio
async def test_dimension_08_safe_idle(subject):
    await certify_safe_idle_boundary(subject)


@pytest.mark.asyncio
async def test_dimension_09_release(subject):
    await certify_release_token_boundary(subject)


@pytest.mark.asyncio
async def test_dimension_10_simulated_exclusion(subject):
    await certify_simulated_exclusion(subject)


def test_five_piece_registration_gate(subject):
    certify_registration_gate(subject)


def test_five_piece_execution_plan_neutrality(subject):
    certify_execution_plan_neutrality(subject)


@pytest.mark.asyncio
async def test_zero_change_common_consumer_native_window(subject):
    await certify_common_consumer_native_window(subject)


# ═══════════════════════════════════════════════════════════════════
# 判定器自测：模板必须能抓「做坏的 fixture」（照 rule_gates 自测形态）
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_kit_catches_a_window_whose_wire_rejects_the_clear_boundary():
    """clear 写被拒 → 窗口不得 formally_confirmed → 模板必红。"""

    broken = _certfake_subject()
    object.__setattr__(
        broken,
        "build_window_driver",
        lambda: _certfake(reject_writes=("CERT:MEAS:CLEar",)),
    )
    with pytest.raises(AssertionError, match="formally_confirmed"):
        await certify_measurement_window_contract(broken)


@pytest.mark.asyncio
async def test_kit_catches_an_attach_that_never_reaches_a_milestone():
    """attach 恒不达标却当 ready 场景交卷 → 模板必红。"""

    broken = _certfake_subject()
    object.__setattr__(
        broken,
        "build_attach_ready_driver",
        lambda: _certfake(attach_script=("IDLE",)),
    )
    with pytest.raises(AssertionError):
        await certify_attach_stage_truth(broken)


@pytest.mark.asyncio
async def test_kit_catches_an_adapter_that_skips_the_error_queue():
    """操作后从不读错误队列的 adapter → 错误队列模板必红。"""

    class _NoErrorQueueDriver(CertFakeBaseStationDriver):
        def _drain_wire_errors(self) -> list:
            return []

    broken = _certfake_subject()
    object.__setattr__(
        broken,
        "build_rejected_config_driver",
        lambda: _NoErrorQueueDriver(
            "certfake-noerr",
            {"ip": "192.0.2.99"},
            reject_writes=("CERT:CONF:BWIDth",),
        ),
    )
    with pytest.raises(AssertionError, match="错误队列"):
        await certify_error_queue_consultation(broken)


# ═══════════════════════════════════════════════════════════════════
# 零修改共同消费者的不变量门：certfake 永不泄漏进生产代码
# ═══════════════════════════════════════════════════════════════════


def test_certfake_never_leaks_into_production_code():
    """第三 adapter 是测试域夹具；生产代码出现 certfake 即为共同消费者被改。

    若某天必须在 app/ 里提及 certfake 才能让认证通过，那就是条目明令的
    「必须修改共同消费者」情形 —— 应停下登记平台缺口，而不是放行本门。
    """

    app_root = Path(__file__).resolve().parents[1] / "app"
    offenders = sorted(
        str(path.relative_to(app_root))
        for path in app_root.rglob("*.py")
        if "certfake" in path.read_text(encoding="utf-8").lower()
    )
    assert offenders == []
