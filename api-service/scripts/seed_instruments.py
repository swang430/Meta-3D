"""
Instrument Registry Seeder (PostgreSQL)

为 MIMO-First 系统注册全部仪器类别、可选型号和默认连接配置。
填充后前端"设备管理"页面将立刻显示内容。

使用方法:
    cd /Users/Simon/Tools/MIMO-First/api-service
    .venv/bin/python scripts/seed_instruments.py
"""

import uuid
from datetime import datetime
from sqlalchemy import create_engine, text

PG_URL = "postgresql://meta3d:meta3d_password@localhost:5432/meta3d_ota"
NOW = datetime.utcnow()


def uid():
    return str(uuid.uuid4())


# ============================================================
# 仪器类别定义
# ============================================================
CATEGORIES = [
    {
        "key": "channelEmulator",
        "name": "信道仿真器",
        "name_en": "Channel Emulator",
        "icon": "IconWaveSine",
        "order": 1,
        "description": "MIMO OTA 信道仿真器，用于多径衰落、多普勒频移等射频信道效应的实时仿真。",
        "models": [
            {
                "vendor": "Keysight",
                "model": "PROPSIM F64",
                "full_name": "Keysight PROPSIM F64 Channel Emulator",
                "capabilities": {
                    "channels": 64,
                    "bandwidth_mhz": 200,
                    "frequency_range_ghz": [0.35, 6.0],
                    "interfaces": ["LAN", "GPIB"],
                    "max_paths_per_channel": 24,
                    "fading_profiles": ["3GPP CDL", "WINNER II", "Custom ASC"],
                    "mimo_config": "up to 8x8 full",
                    "dynamic_range_db": 50,
                },
                "is_default": True,
            },
            {
                "vendor": "Keysight",
                "model": "PROPSIM F32",
                "full_name": "Keysight PROPSIM F32 Channel Emulator",
                "capabilities": {
                    "channels": 32,
                    "bandwidth_mhz": 160,
                    "frequency_range_ghz": [0.35, 6.0],
                    "interfaces": ["LAN", "GPIB"],
                    "max_paths_per_channel": 24,
                    "fading_profiles": ["3GPP CDL", "WINNER II", "Custom ASC"],
                    "mimo_config": "up to 4x4 full",
                    "dynamic_range_db": 50,
                },
            },
            {
                "vendor": "Spirent",
                "model": "VR5",
                "full_name": "Spirent Vertex VR5 Channel Emulator",
                "capabilities": {
                    "channels": 16,
                    "bandwidth_mhz": 160,
                    "frequency_range_ghz": [0.4, 6.0],
                    "interfaces": ["LAN"],
                    "max_paths_per_channel": 48,
                    "fading_profiles": ["3GPP CDL", "SCME", "Custom"],
                    "mimo_config": "up to 8x8 partial",
                },
            },
            {
                "vendor": "R&S",
                "model": "CMW-AE FE200",
                "full_name": "Rohde & Schwarz CMW-AE FE200 Fading Extension",
                "capabilities": {
                    "channels": 16,
                    "bandwidth_mhz": 200,
                    "frequency_range_ghz": [0.35, 6.0],
                    "interfaces": ["LAN"],
                    "fading_profiles": ["3GPP CDL", "WINNER II"],
                    "mimo_config": "up to 4x4",
                },
            },
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.21::inst0::INSTR",
            "controller_ip": "192.168.100.21",
            "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
    {
        "key": "baseStation",
        "name": "基站仿真器",
        "name_en": "Base Station Emulator",
        "icon": "IconAntenna",
        "order": 2,
        "description": "5G NR / LTE 基站仿真器，产生标准 3GPP 下行信号，支持多小区配置。",
        "models": [
            {
                "vendor": "Keysight",
                "model": "UXM 5G E7515B",
                "full_name": "Keysight UXM 5G Wireless Test Platform",
                "capabilities": {
                    "technology": ["5G NR FR1", "5G NR FR2", "LTE", "LTE-A"],
                    "frequency_range_ghz": [0.4, 6.0],
                    "max_bandwidth_mhz": 100,
                    "mimo_layers": 4,
                    "max_tx_power_dbm": 23,
                    "interfaces": ["LAN", "GPIB"],
                    "modulation": ["QPSK", "16QAM", "64QAM", "256QAM"],
                },
                "is_default": True,
            },
            {
                "vendor": "R&S",
                "model": "CMW500",
                "full_name": "Rohde & Schwarz CMW500 Wideband Radio Communication Tester",
                "capabilities": {
                    "technology": ["5G NR FR1", "LTE", "LTE-A", "WCDMA"],
                    "frequency_range_ghz": [0.07, 6.0],
                    "max_bandwidth_mhz": 100,
                    "mimo_layers": 4,
                    "max_tx_power_dbm": 27,
                    "interfaces": ["LAN", "GPIB", "USB"],
                },
            },
            {
                "vendor": "R&S",
                "model": "CMX500",
                "full_name": "Rohde & Schwarz CMX500 5G One-Box Signaling Tester",
                "capabilities": {
                    "technology": ["5G NR FR1", "5G NR FR2", "LTE-A Pro"],
                    "frequency_range_ghz": [0.4, 6.0],
                    "max_bandwidth_mhz": 200,
                    "mimo_layers": 8,
                    "interfaces": ["LAN"],
                },
            },
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.22::inst0::INSTR",
            "controller_ip": "192.168.100.22",
            "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
    {
        "key": "signalAnalyzer",
        "name": "信号分析仪",
        "name_en": "Signal Analyzer",
        "icon": "IconChartLine",
        "order": 3,
        "description": "频谱/信号分析仪，用于 RSRP/SINR/EVM 等射频指标测量和频谱监控。",
        "models": [
            {
                "vendor": "R&S",
                "model": "FSW43",
                "full_name": "Rohde & Schwarz FSW43 Signal and Spectrum Analyzer",
                "capabilities": {
                    "frequency_range_ghz": [0.002, 43.5],
                    "analysis_bandwidth_mhz": 800,
                    "danl_dbm_hz": -168,
                    "phase_noise_dbc_hz": -137,
                    "interfaces": ["LAN", "GPIB", "USB"],
                    "measurements": ["Spectrum", "5G NR", "LTE", "EVM", "ACLR"],
                },
                "is_default": True,
            },
            {
                "vendor": "Keysight",
                "model": "N9040B UXA",
                "full_name": "Keysight N9040B UXA Signal Analyzer",
                "capabilities": {
                    "frequency_range_ghz": [0.003, 50],
                    "analysis_bandwidth_mhz": 510,
                    "danl_dbm_hz": -171,
                    "interfaces": ["LAN", "GPIB", "USB"],
                    "measurements": ["Spectrum", "5G NR", "EVM"],
                },
            },
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.23::inst0::INSTR",
            "controller_ip": "192.168.100.23",
            "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
    {
        "key": "positioner",
        "name": "DUT 转台",
        "name_en": "DUT Positioner / Turntable",
        "icon": "IconRotate360",
        "order": 4,
        "description": "DUT 定位转台系统，用于控制被测设备的方位角和俯仰角旋转。",
        "models": [
            {
                "vendor": "Orbit/FR",
                "model": "FR 5060",
                "full_name": "Orbit/FR Model 5060 Dual-Axis Positioner",
                "capabilities": {
                    "axes": 2,
                    "azimuth_range_deg": [0, 360],
                    "elevation_range_deg": [-90, 90],
                    "max_speed_deg_s": 10,
                    "positioning_accuracy_deg": 0.05,
                    "max_payload_kg": 500,
                    "interfaces": ["RS-232", "LAN"],
                },
                "is_default": True,
            },
            {
                "vendor": "Diamond Engineering",
                "model": "D6050",
                "full_name": "Diamond Engineering D6050 Vehicle Turntable",
                "capabilities": {
                    "axes": 1,
                    "azimuth_range_deg": [0, 360],
                    "max_speed_deg_s": 5,
                    "positioning_accuracy_deg": 0.1,
                    "max_payload_kg": 3000,
                    "interfaces": ["RS-232"],
                },
            },
        ],
        "connection": {
            "endpoint": "192.168.100.24:4001",
            "controller_ip": "192.168.100.24",
            "port": 4001,
            "protocol": "TCP/Modbus",
        },
    },
    {
        "key": "vna",
        "name": "矢量网络分析仪",
        "name_en": "Vector Network Analyzer",
        "icon": "IconTopologyComplex",
        "order": 5,
        "description": "矢量网络分析仪(VNA)，用于校准路径的 S 参数测量、相位一致性校准。",
        "models": [
            {
                "vendor": "Keysight",
                "model": "N5227B PNA",
                "full_name": "Keysight N5227B PNA Microwave Network Analyzer",
                "capabilities": {
                    "frequency_range_ghz": [0.01, 67],
                    "ports": 4,
                    "dynamic_range_db": 145,
                    "trace_noise_db": 0.004,
                    "if_bandwidth_hz": [1, 15e6],
                    "interfaces": ["LAN", "GPIB", "USB"],
                },
                "is_default": True,
            },
            {
                "vendor": "R&S",
                "model": "ZNB40",
                "full_name": "Rohde & Schwarz ZNB40 Vector Network Analyzer",
                "capabilities": {
                    "frequency_range_ghz": [0.009, 40],
                    "ports": 4,
                    "dynamic_range_db": 140,
                    "interfaces": ["LAN", "GPIB", "USB"],
                },
            },
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.25::inst0::INSTR",
            "controller_ip": "192.168.100.25",
            "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
    {
        "key": "rfSwitch",
        "name": "射频开关矩阵",
        "name_en": "RF Switch Matrix",
        "icon": "IconSwitchHorizontal",
        "order": 6,
        "description": "射频开关矩阵，用于信道仿真器输出到各探头天线的信号路由。",
        "models": [
            {
                "vendor": "Keysight",
                "model": "U3022AE06",
                "full_name": "Keysight U3022AE06 RF Switch Matrix",
                "capabilities": {
                    "ports_in": 8,
                    "ports_out": 32,
                    "frequency_range_ghz": [0, 6],
                    "insertion_loss_db": 3.5,
                    "isolation_db": 80,
                    "switching_speed_ms": 15,
                    "interfaces": ["LAN", "GPIB"],
                },
                "is_default": True,
            },
            {
                "vendor": "Mini-Circuits",
                "model": "RC-8SP16T-A18",
                "full_name": "Mini-Circuits RC-8SP16T-A18 Switch Matrix",
                "capabilities": {
                    "ports_in": 8,
                    "ports_out": 16,
                    "frequency_range_ghz": [0, 18],
                    "insertion_loss_db": 4.0,
                    "isolation_db": 70,
                    "interfaces": ["USB", "LAN"],
                },
            },
        ],
        "connection": {
            "endpoint": "TCPIP0::192.168.100.26::inst0::INSTR",
            "controller_ip": "192.168.100.26",
            "port": 5025,
            "protocol": "VISA/SCPI",
        },
    },
]


def main():
    import json

    print("=" * 60)
    print("  Instrument Registry Seeder (PostgreSQL)")
    print(f"  Target DB: {PG_URL.split('@')[1]}")
    print(f"  Timestamp: {NOW.isoformat()}")
    print("=" * 60)

    engine = create_engine(PG_URL)

    with engine.begin() as conn:
        # 检查是否已有数据
        existing = conn.execute(text("SELECT COUNT(*) FROM instrument_categories")).fetchone()[0]
        if existing > 0:
            print(f"\n⚠️  已存在 {existing} 个仪器类别。先清除旧数据...")
            conn.execute(text("DELETE FROM instrument_connections"))
            conn.execute(text("DELETE FROM instrument_models"))
            conn.execute(text("UPDATE instrument_categories SET selected_model_id = NULL"))
            conn.execute(text("DELETE FROM instrument_categories"))
            print("   → 旧数据已清除")

        for cat_def in CATEGORIES:
            cat_id = uid()

            # 1. 创建类别
            conn.execute(text("""
                INSERT INTO instrument_categories 
                    (id, category_key, category_name, category_name_en, 
                     description, icon, display_order, is_active)
                VALUES (:id, :key, :name, :name_en, :desc, :icon, :order, true)
            """), {
                "id": cat_id,
                "key": cat_def["key"],
                "name": cat_def["name"],
                "name_en": cat_def["name_en"],
                "desc": cat_def["description"],
                "icon": cat_def["icon"],
                "order": cat_def["order"],
            })

            # 2. 创建型号
            default_model_id = None
            for i, model_def in enumerate(cat_def["models"]):
                model_id = uid()
                conn.execute(text("""
                    INSERT INTO instrument_models
                        (id, category_id, vendor, model, full_name,
                         capabilities, display_order, is_available)
                    VALUES (:id, :cat_id, :vendor, :model, :full_name,
                            :caps, :order, true)
                """), {
                    "id": model_id,
                    "cat_id": cat_id,
                    "vendor": model_def["vendor"],
                    "model": model_def["model"],
                    "full_name": model_def["full_name"],
                    "caps": json.dumps(model_def["capabilities"]),
                    "order": i,
                })

                if model_def.get("is_default"):
                    default_model_id = model_id

            # 3. 设置默认选中型号
            if default_model_id:
                conn.execute(text("""
                    UPDATE instrument_categories 
                    SET selected_model_id = :mid WHERE id = :cid
                """), {"mid": default_model_id, "cid": cat_id})

            # 4. 创建连接配置
            conn_def = cat_def["connection"]
            conn.execute(text("""
                INSERT INTO instrument_connections
                    (id, category_id, endpoint, controller_ip, port, protocol,
                     status, created_by, notes)
                VALUES (:id, :cat_id, :endpoint, :ip, :port, :proto,
                        'disconnected', 'SYSTEM_SEED', '初始化默认配置，连接真实硬件后请更新IP')
            """), {
                "id": uid(),
                "cat_id": cat_id,
                "endpoint": conn_def["endpoint"],
                "ip": conn_def["controller_ip"],
                "port": conn_def["port"],
                "proto": conn_def["protocol"],
            })

            model_count = len(cat_def["models"])
            default_label = next(
                (m["model"] for m in cat_def["models"] if m.get("is_default")),
                "none"
            )
            print(f"  [{cat_def['order']}] {cat_def['name']} ({cat_def['key']})")
            print(f"      {model_count} 型号, 默认: {default_label}")
            print(f"      连接: {conn_def['endpoint']} ({conn_def['protocol']})")

    print(f"\n✅ 已注册 {len(CATEGORIES)} 个仪器类别！")
    print('   前端"设备管理"页面现在应该能看到完整的仪器列表了。')


if __name__ == "__main__":
    main()
