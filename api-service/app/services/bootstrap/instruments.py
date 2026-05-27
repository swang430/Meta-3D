"""Seed the canonical instrument catalog: 7 categories + their models.

Migrated from ``scripts/seed_instruments.py`` which used raw SQL +
hardcoded PG URL + wipe-and-reseed. The bootstrap version uses ORM
against the session (DB-agnostic) and is idempotent per natural key:

- ``InstrumentCategory`` keyed by ``category_key``
- ``InstrumentModel`` keyed by ``(category_id, model)``
- ``InstrumentConnection`` keyed by ``category_id`` (one default
  connection row per category)

Operator-modified rows (e.g. an IP address set after seed) are
preserved across re-runs.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.services.bootstrap import SeedResult, Seeder

logger = logging.getLogger(__name__)


_CATEGORIES: list[dict] = [
    {
        "key": "channelEmulator",
        "name": "信道仿真器",
        "name_en": "Channel Emulator",
        "icon": "IconWaveSine",
        "order": 1,
        "usage_phase": ["test"],
        "description": "MIMO OTA 信道仿真器，用于多径衰落、多普勒频移等射频信道效应的实时仿真。",
        "models": [
            {"vendor": "Keysight", "model": "PROPSIM F64",
             "full_name": "Keysight PROPSIM F64 Channel Emulator",
             "capabilities": {"channels": 64, "bandwidth_mhz": 200,
                              "frequency_range_ghz": [0.35, 6.0],
                              "interfaces": ["LAN", "GPIB"],
                              "max_paths_per_channel": 24,
                              "fading_profiles": ["3GPP CDL", "WINNER II", "Custom ASC"],
                              "mimo_config": "up to 8x8 full",
                              "dynamic_range_db": 50},
             "is_default": True},
            {"vendor": "Keysight", "model": "PROPSIM F32",
             "full_name": "Keysight PROPSIM F32 Channel Emulator",
             "capabilities": {"channels": 32, "bandwidth_mhz": 160,
                              "frequency_range_ghz": [0.35, 6.0],
                              "interfaces": ["LAN", "GPIB"],
                              "max_paths_per_channel": 24,
                              "fading_profiles": ["3GPP CDL", "WINNER II", "Custom ASC"],
                              "mimo_config": "up to 4x4 full", "dynamic_range_db": 50}},
            {"vendor": "Keysight", "model": "PROPSIM FS16",
             "full_name": "Keysight PROPSIM FS16 Channel Emulator (F8820A)",
             "capabilities": {"channels": 4, "bandwidth_mhz": 100,
                              "frequency_range_ghz": [0.003, 6.0],
                              "interfaces": ["LAN"],
                              "fading_profiles": ["Playback (file-based, .smu)"],
                              "mimo_config": "up to 2x2",
                              "scpi_dialect": "FS-series (different from F64)",
                              "driver_status": "MVP — connect/identify/state only; channel loading + path-loss not yet wired"}},
            {"vendor": "Spirent", "model": "VR5",
             "full_name": "Spirent Vertex VR5 Channel Emulator",
             "capabilities": {"channels": 16, "bandwidth_mhz": 160,
                              "frequency_range_ghz": [0.4, 6.0],
                              "interfaces": ["LAN"], "max_paths_per_channel": 48,
                              "fading_profiles": ["3GPP CDL", "SCME", "Custom"],
                              "mimo_config": "up to 8x8 partial"}},
            {"vendor": "KSW", "model": "KCE-8064A",
             "full_name": "坤恒顺维 KCE-8064A 多通道信道仿真器",
             "capabilities": {"channels": 64, "bandwidth_mhz": 160,
                              "frequency_range_ghz": [0.4, 6.0],
                              "interfaces": ["LAN"], "max_paths_per_channel": 24,
                              "fading_profiles": ["3GPP CDL", "3GPP TDL", "WINNER II"],
                              "mimo_config": "up to 8x8 full", "dynamic_range_db": 45}},
        ],
        "connection": {
            # PROPSIM F64 走 raw SOCKET, ATE/SCPI 端口硬件固定 3334 (非 5025/INSTR)。
            # [现场 2026-05-27 实测; 详见 propsim_f64.py 顶注 + roadmap P0-8]
            "endpoint": "TCPIP0::192.168.100.21::3334::SOCKET",
            "controller_ip": "192.168.100.21", "port": 3334,
            "protocol": "VISA/SCPI (raw SOCKET)",
        },
    },
    {
        "key": "baseStation",
        "name": "基站仿真器",
        "name_en": "Base Station Emulator",
        "icon": "IconAntenna",
        "order": 2,
        "usage_phase": ["test"],
        "description": "5G NR / LTE 基站仿真器，产生标准 3GPP 下行信号，支持多小区配置。",
        "models": [
            {"vendor": "Keysight", "model": "UXM 5G E7515B",
             "full_name": "Keysight UXM 5G Wireless Test Platform",
             "capabilities": {"technology": ["5G NR FR1", "5G NR FR2", "LTE", "LTE-A"],
                              "frequency_range_ghz": [0.4, 6.0],
                              "max_bandwidth_mhz": 100, "mimo_layers": 4,
                              "max_tx_power_dbm": 23, "interfaces": ["LAN", "GPIB"],
                              "modulation": ["QPSK", "16QAM", "64QAM", "256QAM"]},
             "is_default": True},
            {"vendor": "R&S", "model": "CMW500",
             "full_name": "Rohde & Schwarz CMW500 Wideband Radio Communication Tester",
             "capabilities": {"technology": ["LTE", "LTE-A"],
                              "frequency_range_ghz": [0.45, 6.0],
                              "max_bandwidth_mhz": 20, "mimo_layers": 4,
                              "max_tx_power_dbm": 27,
                              "interfaces": ["LAN", "GPIB", "USB"],
                              "modulation": ["QPSK", "16QAM", "64QAM", "256QAM"]}},
            {"vendor": "R&S", "model": "CMX500",
             "full_name": "Rohde & Schwarz CMX500 5G One-Box Signaling Tester (驱动待开发)",
             "capabilities": {"technology": ["5G NR FR1", "5G NR FR2", "LTE-A Pro"],
                              "frequency_range_ghz": [0.4, 6.0],
                              "max_bandwidth_mhz": 200, "mimo_layers": 8,
                              "interfaces": ["LAN"],
                              "driver_status": "not_implemented",
                              "driver_notes": "等 R&S CMX500 SCPI 手册到位再开工"}},
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.22::inst0::INSTR",
            "controller_ip": "192.168.100.22", "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
    {
        "key": "signalAnalyzer",
        "name": "信号分析仪",
        "name_en": "Signal Analyzer",
        "icon": "IconChartLine",
        "order": 3,
        "usage_phase": ["calibration", "test"],
        "description": "频谱/信号分析仪，用于 RSRP/SINR/EVM 等射频指标测量和频谱监控。",
        "models": [
            {"vendor": "R&S", "model": "FSW43",
             "full_name": "Rohde & Schwarz FSW43 Signal and Spectrum Analyzer",
             "capabilities": {"frequency_range_ghz": [0.002, 43.5],
                              "analysis_bandwidth_mhz": 800, "danl_dbm_hz": -168,
                              "phase_noise_dbc_hz": -137,
                              "interfaces": ["LAN", "GPIB", "USB"],
                              "measurements": ["Spectrum", "5G NR", "LTE", "EVM", "ACLR"]},
             "is_default": True},
            {"vendor": "Keysight", "model": "N9020B MXA",
             "full_name": "Keysight N9020B MXA Signal Analyzer (X-Series)",
             "capabilities": {"frequency_range_ghz": [0.01, 26.5],
                              "analysis_bandwidth_mhz": 160, "danl_dbm_hz": -166,
                              "interfaces": ["LAN", "GPIB"],
                              "measurements": ["Spectrum", "5G NR", "EVM"]}},
            {"vendor": "R&S", "model": "FSVA3000",
             "full_name": "Rohde & Schwarz FSVA3000 Signal and Spectrum Analyzer",
             "capabilities": {"frequency_range_ghz": [0.01, 44],
                              "analysis_bandwidth_mhz": 200, "danl_dbm_hz": -167,
                              "phase_noise_dbc_hz": -140,
                              "interfaces": ["LAN", "GPIB", "USB"],
                              "measurements": ["Spectrum", "5G NR", "LTE", "EVM", "ACLR", "Channel Power"]}},
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.23::inst0::INSTR",
            "controller_ip": "192.168.100.23", "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
    {
        "key": "positioner",
        "name": "DUT 转台",
        "name_en": "DUT Positioner / Turntable",
        "icon": "IconRotate360",
        "order": 4,
        "usage_phase": ["calibration", "test"],
        "description": "DUT 定位转台系统，用于控制被测设备的方位角和俯仰角旋转。",
        "models": [
            {"vendor": "ETS-Lindgren", "model": "EMCenter",
             "full_name": "ETS-Lindgren EMCenter Modular RF Platform",
             "capabilities": {"axes": 2, "azimuth_range_deg": [0, 360],
                              "elevation_range_deg": [-90, 90], "interfaces": ["LAN"]},
             "is_default": True},
            {"vendor": "Orbit/FR", "model": "FR 5060",
             "full_name": "Orbit/FR Model 5060 Dual-Axis Positioner",
             "capabilities": {"axes": 2, "azimuth_range_deg": [0, 360],
                              "elevation_range_deg": [-90, 90], "max_speed_deg_s": 10,
                              "positioning_accuracy_deg": 0.05, "max_payload_kg": 500,
                              "interfaces": ["RS-232", "LAN"]}},
            {"vendor": "Diamond Engineering", "model": "D6050",
             "full_name": "Diamond Engineering D6050 Vehicle Turntable",
             "capabilities": {"axes": 1, "azimuth_range_deg": [0, 360],
                              "max_speed_deg_s": 5, "positioning_accuracy_deg": 0.1,
                              "max_payload_kg": 3000, "interfaces": ["RS-232"]}},
            {"vendor": "Aerotech", "model": "A3200",
             "full_name": "Aerotech A3200 Multi-Axis Motion Controller",
             "capabilities": {"axes": 2, "azimuth_range_deg": [0, 360],
                              "elevation_range_deg": [-90, 90], "max_speed_deg_s": 20,
                              "positioning_accuracy_deg": 0.01, "max_payload_kg": 2000,
                              "protocol": "AeroBasic/TCP",
                              "interfaces": ["LAN", "RS-232"]}},
        ],
        "connection": {
            "endpoint": "192.168.100.24:4001",
            "controller_ip": "192.168.100.24", "port": 4001,
            "protocol": "TCP/Modbus",
        },
    },
    {
        "key": "vna",
        "name": "矢量网络分析仪",
        "name_en": "Vector Network Analyzer",
        "icon": "IconTopologyComplex",
        "order": 5,
        "usage_phase": ["calibration"],
        "description": "矢量网络分析仪(VNA)，用于校准路径的 S 参数测量、相位一致性校准。",
        "models": [
            {"vendor": "Keysight", "model": "E5071C ENA",
             "full_name": "Keysight E5071C ENA Vector Network Analyzer",
             "capabilities": {"frequency_range_ghz": [0.009, 20], "ports": 4,
                              "dynamic_range_db": 123, "interfaces": ["LAN", "GPIB"]},
             "is_default": True},
            {"vendor": "Keysight", "model": "N5227B PNA",
             "full_name": "Keysight N5227B PNA Microwave Network Analyzer",
             "capabilities": {"frequency_range_ghz": [0.01, 67], "ports": 4,
                              "dynamic_range_db": 145, "trace_noise_db": 0.004,
                              "if_bandwidth_hz": [1, 15e6],
                              "interfaces": ["LAN", "GPIB", "USB"]}},
            {"vendor": "R&S", "model": "ZNB40",
             "full_name": "Rohde & Schwarz ZNB40 Vector Network Analyzer",
             "capabilities": {"frequency_range_ghz": [0.009, 40], "ports": 4,
                              "dynamic_range_db": 140,
                              "interfaces": ["LAN", "GPIB", "USB"]}},
            {"vendor": "R&S", "model": "ZNA67",
             "full_name": "Rohde & Schwarz ZNA67 Vector Network Analyzer",
             "capabilities": {"frequency_range_ghz": [0.01, 67], "ports": 4,
                              "dynamic_range_db": 145, "trace_noise_db": 0.002,
                              "if_bandwidth_hz": [1, 30e6],
                              "interfaces": ["LAN", "GPIB", "USB"], "time_domain": True}},
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.25::inst0::INSTR",
            "controller_ip": "192.168.100.25", "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
    {
        "key": "rfSwitch",
        "name": "射频开关矩阵",
        "name_en": "RF Switch Matrix",
        "icon": "IconSwitchHorizontal",
        "order": 6,
        "usage_phase": ["calibration", "test"],
        "description": "射频开关矩阵，用于信道仿真器输出到各探头天线的信号路由。",
        "models": [
            {"vendor": "ETS-Lindgren", "model": "EMCenter Switch",
             "full_name": "ETS-Lindgren EMCenter RF Switch / Relay",
             "capabilities": {"slots": 7, "relay_types": ["SPDT", "SP6T"],
                              "interfaces": ["LAN", "Serial"]},
             "is_default": True},
            {"vendor": "Keysight", "model": "U3022AE06",
             "full_name": "Keysight U3022AE06 RF Switch Matrix",
             "capabilities": {"ports_in": 8, "ports_out": 32,
                              "frequency_range_ghz": [0, 6],
                              "insertion_loss_db": 3.5, "isolation_db": 80,
                              "switching_speed_ms": 15,
                              "interfaces": ["LAN", "GPIB"]}},
            {"vendor": "Mini-Circuits", "model": "RC-8SP16T-A18",
             "full_name": "Mini-Circuits RC-8SP16T-A18 Switch Matrix",
             "capabilities": {"ports_in": 8, "ports_out": 16,
                              "frequency_range_ghz": [0, 18],
                              "insertion_loss_db": 4.0, "isolation_db": 70,
                              "interfaces": ["USB", "LAN"]}},
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.26::inst0::INSTR",
            "controller_ip": "192.168.100.26", "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
    {
        "key": "vectorSignalGenerator",
        "name": "矢量信号发生器",
        "name_en": "Vector Signal Generator",
        "icon": "IconWaveSquare",
        "order": 7,
        "usage_phase": ["calibration", "test"],
        "description": "矢量信号发生器(VSG)，产生调制射频信号，用于校准参考信号注入和信道仿真器旁路测试。",
        "models": [
            {"vendor": "R&S", "model": "SMW200A",
             "full_name": "Rohde & Schwarz SMW200A Vector Signal Generator",
             "capabilities": {"frequency_range_ghz": [0.1, 44],
                              "max_output_power_dbm": 18,
                              "modulation_bandwidth_mhz": 2000,
                              "phase_noise_dbc_hz": -139,
                              "interfaces": ["LAN", "GPIB", "USB"],
                              "standards": ["5G NR", "LTE", "WLAN", "Custom IQ"],
                              "baseband_generators": 2},
             "is_default": True},
            {"vendor": "Keysight", "model": "N5182B MXG",
             "full_name": "Keysight N5182B MXG X-Series Signal Generator",
             "capabilities": {"frequency_range_ghz": [0.009, 6],
                              "max_output_power_dbm": 20,
                              "modulation_bandwidth_mhz": 160,
                              "interfaces": ["LAN", "GPIB", "USB"],
                              "standards": ["5G NR", "LTE", "WLAN"]}},
            {"vendor": "Keysight", "model": "E8267D PSG",
             "full_name": "Keysight E8267D PSG Vector Signal Generator",
             "capabilities": {"frequency_range_ghz": [0.25, 44],
                              "max_output_power_dbm": 17,
                              "modulation_bandwidth_mhz": 2000,
                              "interfaces": ["LAN", "GPIB"],
                              "standards": ["5G NR", "LTE", "Radar", "Custom IQ"]}},
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.27::inst0::INSTR",
            "controller_ip": "192.168.100.27", "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
]


def _seed(db: Session) -> SeedResult:
    inserted = 0
    skipped = 0
    for cat_def in _CATEGORIES:
        category = (
            db.query(InstrumentCategory)
            .filter(InstrumentCategory.category_key == cat_def["key"])
            .first()
        )
        if category is None:
            category = InstrumentCategory(
                category_key=cat_def["key"],
                category_name=cat_def["name"],
                category_name_en=cat_def["name_en"],
                description=cat_def["description"],
                icon=cat_def["icon"],
                display_order=cat_def["order"],
                usage_phase=cat_def.get("usage_phase", ["calibration", "test"]),
                driver_mode=cat_def.get("driver_mode", "auto"),
                is_active=True,
            )
            db.add(category)
            db.flush()  # populate category.id
            inserted += 1
        else:
            skipped += 1

        default_model_id = None
        for i, model_def in enumerate(cat_def["models"]):
            existing_model = (
                db.query(InstrumentModel)
                .filter(
                    InstrumentModel.category_id == category.id,
                    InstrumentModel.model == model_def["model"],
                )
                .first()
            )
            if existing_model is None:
                new_model = InstrumentModel(
                    category_id=category.id,
                    vendor=model_def["vendor"],
                    model=model_def["model"],
                    full_name=model_def["full_name"],
                    capabilities=model_def["capabilities"],
                    display_order=i,
                    is_available=True,
                )
                db.add(new_model)
                db.flush()
                inserted += 1
                if model_def.get("is_default"):
                    default_model_id = new_model.id
            else:
                skipped += 1
                if model_def.get("is_default") and category.selected_model_id is None:
                    default_model_id = existing_model.id

        if default_model_id is not None and category.selected_model_id is None:
            category.selected_model_id = default_model_id

        conn_def = cat_def["connection"]
        existing_conn = (
            db.query(InstrumentConnection)
            .filter(InstrumentConnection.category_id == category.id)
            .first()
        )
        if existing_conn is None:
            db.add(InstrumentConnection(
                category_id=category.id,
                endpoint=conn_def["endpoint"],
                controller_ip=conn_def["controller_ip"],
                port=conn_def["port"],
                protocol=conn_def["protocol"],
                status="disconnected",
                created_by="system",
                notes="初始化默认配置，连接真实硬件后请更新IP",
            ))
            inserted += 1
        else:
            skipped += 1

    db.flush()
    if inserted:
        logger.info("[instruments] seeded %d category/model/connection rows", inserted)
    return SeedResult(inserted=inserted, skipped=skipped)


instruments_seeder = Seeder(
    name="instruments",
    version=1,
    description=f"{len(_CATEGORIES)} instrument categories + their model catalog + default connections",
    run=_seed,
)
