"""P1-51：真实仪表地址必须来自显式配置，缺配置在外部 I/O 前失败。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.aerotech_positioner import RealAerotechDriver
from app.hal.base import InstrumentStatus, resolve_configured_instrument_host
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.driver_registry import DriverRegistry
from app.hal.ets_positioner import RealEtsEmcenterDriver
from app.hal.keysight_ena import RealKeysightEnaDriver
from app.hal.keysight_mxg import RealKeysightMxgDriver
from app.hal.keysight_x_series_sa import RealKeysightXSeriesSaDriver
from app.hal.propsim_f64 import PropsimF64Controller, RealPropsimF64Driver
from app.hal.propsim_fs16 import RealPropsimFs16Driver
from app.hal.rf_switch import EtslSwitchDriver
from app.hal.rs_fsva import RealRsFsvaDriver
from app.hal.rs_fsw import RealRsFswDriver
from app.hal.rs_smw200a import RealRsSmw200aDriver
from app.hal.rs_zna import RealRsZnaDriver
from app.hal.uxm_base_station import RealUxmDriver
from app.models.instrument import InstrumentConnection
from app.services.bootstrap import run_all
from app.services.bootstrap.instruments import instruments_seeder
from app.services.instrument_hal_service import preflight_target


REAL_DRIVER_CASES = [
    (RealPropsimF64Driver, "ip_address"),
    (RealPropsimFs16Driver, "ip_address"),
    (RealUxmDriver, "ip_address"),
    (RealCmw500Driver, "ip_address"),
    (RealEtsEmcenterDriver, "ip_address"),
    (RealAerotechDriver, "ip_address"),
    (RealKeysightEnaDriver, "ip_address"),
    (RealRsZnaDriver, "ip_address"),
    (RealKeysightMxgDriver, "ip_address"),
    (RealRsSmw200aDriver, "ip_address"),
    (RealRsFswDriver, "ip_address"),
    (RealRsFsvaDriver, "ip_address"),
    (RealKeysightXSeriesSaDriver, "ip_address"),
    (EtslSwitchDriver, "_ip"),
]


@pytest.mark.parametrize(("driver_class", "host_attribute"), REAL_DRIVER_CASES)
@pytest.mark.asyncio
async def test_real_drivers_fail_before_io_when_address_is_missing(
    driver_class,
    host_attribute,
):
    driver = driver_class("missing-address", {})

    assert getattr(driver, host_attribute) == "", (
        f"{driver_class.__name__} 仍在空配置下生成猜测地址"
    )
    assert await driver.connect() is False
    assert driver.status is InstrumentStatus.ERROR
    assert "未配置连接地址" in (driver.last_error or "")


def test_explicit_endpoint_shapes_resolve_without_guessing():
    assert resolve_configured_instrument_host({"ip": "10.20.30.40"}) == "10.20.30.40"
    assert resolve_configured_instrument_host(
        {"endpoint": "TCPIP0::uxm-lab.local::hislip2::INSTR"}
    ) == "uxm-lab.local"
    assert resolve_configured_instrument_host(
        {"endpoint": "192.168.1.131:8000"}
    ) == "192.168.1.131"
    assert resolve_configured_instrument_host({}) == ""


@pytest.mark.parametrize(
    ("driver_class", "config", "expected_resource"),
    [
        (
            RealUxmDriver,
            {"endpoint": "uxm-lab.local:6000", "protocol": "TCPIP"},
            "TCPIP::uxm-lab.local::6000::SOCKET",
        ),
        (
            RealCmw500Driver,
            {"endpoint": "cmw-lab.local:5025"},
            "TCPIP::cmw-lab.local::hislip0::INSTR",
        ),
        (
            RealUxmDriver,
            {"endpoint": "TCPIP0::uxm-lab.local::hislip2::INSTR"},
            "TCPIP0::uxm-lab.local::hislip2::INSTR",
        ),
    ],
)
@pytest.mark.asyncio
async def test_uxm_cmw_normalize_supported_endpoint_shapes(
    driver_class,
    config,
    expected_resource,
):
    rm = MagicMock()
    rm.open_resource.side_effect = RuntimeError("stop after resource capture")
    with patch("pyvisa.ResourceManager", return_value=rm):
        assert await driver_class("endpoint-shape", config).connect() is False
    assert rm.open_resource.call_args.args[0] == expected_resource


@pytest.mark.parametrize("driver_class", [RealUxmDriver, RealCmw500Driver])
@pytest.mark.asyncio
async def test_uxm_cmw_reject_conflicting_structured_and_resource_hosts_before_io(
    driver_class,
):
    driver = driver_class(
        "conflicting-addresses",
        {
            "controller_ip": "10.20.30.40",
            "endpoint": "TCPIP0::10.20.30.99::hislip2::INSTR",
        },
    )
    with patch("pyvisa.ResourceManager") as resource_manager:
        assert await driver.connect() is False
    resource_manager.assert_not_called()
    assert driver.status is InstrumentStatus.ERROR
    assert "冲突" in (driver.last_error or "")


@pytest.mark.parametrize("driver_class", [RealUxmDriver, RealCmw500Driver])
@pytest.mark.asyncio
async def test_uxm_cmw_reject_conflicting_explicit_resource_ports_before_io(
    driver_class,
):
    driver = driver_class(
        "conflicting-resource-ports",
        {
            "visa_resource": "TCPIP0::10.20.30.40::5025::SOCKET",
            "endpoint": "TCPIP0::10.20.30.40::3334::SOCKET",
            "port": 3334,
        },
    )
    with patch("pyvisa.ResourceManager") as resource_manager:
        assert await driver.connect() is False
    resource_manager.assert_not_called()
    assert "端口冲突" in (driver.last_error or "")


@pytest.mark.parametrize("driver_class", [RealUxmDriver, RealCmw500Driver])
@pytest.mark.asyncio
async def test_uxm_cmw_blank_endpoint_fails_before_resource_manager(driver_class):
    driver = driver_class("blank-address", {"endpoint": "   "})
    with patch("pyvisa.ResourceManager") as resource_manager:
        assert await driver.connect() is False
    resource_manager.assert_not_called()
    assert "未配置连接地址" in (driver.last_error or "")


def test_registry_auto_requires_an_explicit_address():
    registry = DriverRegistry()
    registry.set_mode("auto")

    mock_driver = registry.register(
        "channel_emulator",
        "no-address",
        {},
    )
    real_driver = registry.register(
        "channel_emulator",
        "endpoint-only",
        {"endpoint": "TCPIP0::10.20.30.40::3334::SOCKET"},
    )

    assert mock_driver.driver_source == "mock"
    assert isinstance(real_driver, RealPropsimF64Driver)
    assert real_driver.ip_address == "10.20.30.40"


def test_registry_does_not_hide_conflicting_explicit_addresses_with_mock():
    registry = DriverRegistry()
    registry.set_mode("auto")

    driver = registry.register(
        "base_station",
        "conflicting-base-station",
        {
            "controller_ip": "10.20.30.40",
            "endpoint": "TCPIP0::10.20.30.99::hislip2::INSTR",
        },
    )

    assert isinstance(driver, RealUxmDriver)


def test_readiness_preflight_does_not_probe_a_conflicting_address_source():
    connection = SimpleNamespace(
        controller_ip="10.20.30.40",
        port=5025,
        endpoint="TCPIP0::10.20.30.99::hislip2::INSTR",
    )

    assert preflight_target(connection) is None


def test_fresh_bootstrap_does_not_seed_guessed_addresses():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        run_all(db, [instruments_seeder])
        connections = db.query(InstrumentConnection).all()
        assert len(connections) == 7
        assert all(conn.controller_ip is None for conn in connections)
        assert all(conn.endpoint is None for conn in connections)
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_bootstrap_preserves_existing_operator_address():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        run_all(db, [instruments_seeder])
        conn = db.query(InstrumentConnection).first()
        conn.controller_ip = "10.99.0.8"
        conn.endpoint = "TCPIP0::10.99.0.8::3334::SOCKET"
        db.commit()

        run_all(db, [instruments_seeder], force=True)
        db.refresh(conn)
        assert conn.controller_ip == "10.99.0.8"
        assert conn.endpoint == "TCPIP0::10.99.0.8::3334::SOCKET"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_legacy_f64_controller_requires_an_explicit_address():
    with pytest.raises(TypeError):
        PropsimF64Controller()
