"""Initialize test sequence library with sample data"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.test_plan import TestSequence
import uuid

def init_sequences():
    """Add sample test sequences"""
    db: Session = SessionLocal()

    try:
        # Check if sequences already exist
        existing = db.query(TestSequence).count()
        if existing > 0:
            print(f"Sequences already exist ({existing} found). Skipping initialization.")
            return

        sequences = [
            {
                "name": "基础仪器配置",
                "description": "配置信道仿真器和信号分析仪的基本参数",
                "category": "Instrument Setup",
                "steps": [
                    {
                        "step_number": 1,
                        "name": "连接信道仿真器",
                        "type": "connect_instrument",
                        "parameters": {"instrument_type": "channel_emulator"}
                    },
                    {
                        "step_number": 2,
                        "name": "设置工作频率",
                        "type": "configure_frequency",
                        "parameters": {"frequency_mhz": 2400, "bandwidth_mhz": 20}
                    }
                ],
                "parameters": {"frequency_mhz": {"type": "number", "default": 2400}},
                "default_values": {"frequency_mhz": 2400},
                "is_public": True,
                "usage_count": 15,
                "created_by": "system"
            },
            {
                "name": "TRP测量序列",
                "description": "完整的TRP（总辐射功率）测量流程",
                "category": "Measurement",
                "steps": [
                    {
                        "step_number": 1,
                        "name": "设置测量频率",
                        "type": "configure_frequency",
                        "parameters": {"frequency_mhz": 2400}
                    },
                    {
                        "step_number": 2,
                        "name": "开始TRP测量",
                        "type": "run_measurement",
                        "parameters": {"measurement_type": "TRP", "theta_step": 15, "phi_step": 30}
                    },
                    {
                        "step_number": 3,
                        "name": "保存测量结果",
                        "type": "save_results",
                        "parameters": {"result_type": "TRP"}
                    }
                ],
                "parameters": {
                    "frequency_mhz": {"type": "number", "default": 2400},
                    "theta_step": {"type": "number", "default": 15},
                    "phi_step": {"type": "number", "default": 30}
                },
                "default_values": {"frequency_mhz": 2400, "theta_step": 15, "phi_step": 30},
                "is_public": True,
                "usage_count": 42,
                "created_by": "system"
            },
            {
                "name": "TIS测量序列",
                "description": "完整的TIS（总全向灵敏度）测量流程",
                "category": "Measurement",
                "steps": [
                    {
                        "step_number": 1,
                        "name": "配置基站仿真器",
                        "type": "configure_instrument",
                        "parameters": {"instrument_type": "base_station", "tx_power_dbm": -70}
                    },
                    {
                        "step_number": 2,
                        "name": "开始TIS测量",
                        "type": "run_measurement",
                        "parameters": {"measurement_type": "TIS", "target_throughput_mbps": 10}
                    }
                ],
                "parameters": {
                    "tx_power_dbm": {"type": "number", "default": -70},
                    "target_throughput_mbps": {"type": "number", "default": 10}
                },
                "default_values": {"tx_power_dbm": -70, "target_throughput_mbps": 10},
                "is_public": True,
                "usage_count": 38,
                "created_by": "system"
            },
            {
                "name": "MIMO信道模型配置",
                "description": "配置多径MIMO信道模型",
                "category": "Channel Model",
                "steps": [
                    {
                        "step_number": 1,
                        "name": "选择信道模型",
                        "type": "select_channel_model",
                        "parameters": {"model": "SCME_UMa"}
                    },
                    {
                        "step_number": 2,
                        "name": "设置多普勒频移",
                        "type": "configure_doppler",
                        "parameters": {"speed_kmh": 30}
                    },
                    {
                        "step_number": 3,
                        "name": "配置空间相关性",
                        "type": "configure_correlation",
                        "parameters": {"correlation_matrix": "low"}
                    }
                ],
                "parameters": {
                    "model": {"type": "string", "default": "SCME_UMa"},
                    "speed_kmh": {"type": "number", "default": 30}
                },
                "default_values": {"model": "SCME_UMa", "speed_kmh": 30},
                "is_public": True,
                "usage_count": 23,
                "created_by": "system"
            },
            {
                "name": "快速探头校准",
                "description": "对选定探头进行快速校准检查",
                "category": "Calibration",
                "steps": [
                    {
                        "step_number": 1,
                        "name": "选择校准探头",
                        "type": "select_probes",
                        "parameters": {"probe_count": 8}
                    },
                    {
                        "step_number": 2,
                        "name": "运行校准测试",
                        "type": "run_calibration",
                        "parameters": {"calibration_type": "quick"}
                    }
                ],
                "parameters": {"probe_count": {"type": "number", "default": 8}},
                "default_values": {"probe_count": 8},
                "is_public": True,
                "usage_count": 18,
                "created_by": "system"
            },
            {
                "name": "5G NR测试配置",
                "description": "配置5G NR测试环境",
                "category": "5G NR",
                "steps": [
                    {
                        "step_number": 1,
                        "name": "设置5G频段",
                        "type": "configure_frequency",
                        "parameters": {"frequency_mhz": 3500, "bandwidth_mhz": 100}
                    },
                    {
                        "step_number": 2,
                        "name": "配置波束成形",
                        "type": "configure_beamforming",
                        "parameters": {"beams": 8, "codebook": "Type1"}
                    }
                ],
                "parameters": {
                    "frequency_mhz": {"type": "number", "default": 3500},
                    "beams": {"type": "number", "default": 8}
                },
                "default_values": {"frequency_mhz": 3500, "beams": 8},
                "is_public": True,
                "usage_count": 31,
                "created_by": "system"
            },
            # ========== Virtual Road Test Sequences (8 steps) ==========
            {
                "name": "Configure Digital Twin Environment",
                "description": "加载数字孪生环境配置，包括射线跟踪信道、干扰源和移动散射体",
                "category": "Road Test - Step 0",
                "steps": [
                    {"step_number": 1, "name": "加载环境配置", "type": "load_environment", "parameters": {}},
                    {"step_number": 2, "name": "配置信道模型", "type": "configure_channel_model", "parameters": {}},
                    {"step_number": 3, "name": "设置干扰源", "type": "configure_interference", "parameters": {}},
                    {"step_number": 4, "name": "配置散射体", "type": "configure_scatterers", "parameters": {}}
                ],
                "parameters": {
                    "channel_model_type": {"type": "string", "default": "3gpp-statistical"},
                    "scenario": {"type": "string", "default": "UMa"},
                    "los_condition": {"type": "string", "default": "auto"},
                    "interference_enabled": {"type": "boolean", "default": False},
                    "scatterers_enabled": {"type": "boolean", "default": False}
                },
                "default_values": {
                    "channel_model_type": "3gpp-statistical",
                    "scenario": "UMa",
                    "los_condition": "auto"
                },
                "is_public": True,
                "usage_count": 0,
                "created_by": "system"
            },
            {
                "name": "Initialize OTA Chamber (MPAC)",
                "description": "初始化OTA暗室设备，验证探头阵列连接，校准转台位置",
                "category": "Road Test - Step 1",
                "steps": [
                    {"step_number": 1, "name": "连接暗室", "type": "connect_chamber", "parameters": {}},
                    {"step_number": 2, "name": "校准探头", "type": "calibrate_probes", "parameters": {}},
                    {"step_number": 3, "name": "转台归位", "type": "home_positioner", "parameters": {}}
                ],
                "parameters": {
                    "chamber_id": {"type": "string", "default": "MPAC-1"},
                    "verify_connections": {"type": "boolean", "default": True},
                    "calibrate_position_table": {"type": "boolean", "default": True}
                },
                "default_values": {"chamber_id": "MPAC-1"},
                "is_public": True,
                "usage_count": 0,
                "created_by": "system"
            },
            {
                "name": "Configure Network",
                "description": "配置核心网和传输网参数，不涉及无线接入层",
                "category": "Road Test - Step 2",
                "steps": [
                    {"step_number": 1, "name": "配置核心网", "type": "configure_core_network", "parameters": {}},
                    {"step_number": 2, "name": "验证信号", "type": "verify_signal", "parameters": {}}
                ],
                "parameters": {
                    "frequency_mhz": {"type": "number", "default": 3500},
                    "bandwidth_mhz": {"type": "number", "default": 100},
                    "technology": {"type": "string", "default": "5G NR"}
                },
                "default_values": {"frequency_mhz": 3500, "bandwidth_mhz": 100, "technology": "5G NR"},
                "is_public": True,
                "usage_count": 0,
                "created_by": "system"
            },
            {
                "name": "Setup Base Stations and Channel Model",
                "description": "配置基站发射参数、天线阵列和MIMO模式",
                "category": "Road Test - Step 3",
                "steps": [
                    {"step_number": 1, "name": "配置基站参数", "type": "configure_base_stations", "parameters": {}},
                    {"step_number": 2, "name": "设置天线阵列", "type": "configure_antenna_array", "parameters": {}},
                    {"step_number": 3, "name": "验证覆盖", "type": "verify_coverage", "parameters": {}}
                ],
                "parameters": {
                    "channel_model": {"type": "string", "default": "UMa"},
                    "num_base_stations": {"type": "number", "default": 3}
                },
                "default_values": {"channel_model": "UMa", "num_base_stations": 3},
                "is_public": True,
                "usage_count": 0,
                "created_by": "system"
            },
            {
                "name": "Configure OTA Mapper",
                "description": "将数字孪生信道映射为探头权重，实现信道仿真",
                "category": "Road Test - Step 4",
                "steps": [
                    {"step_number": 1, "name": "加载路径文件", "type": "load_route", "parameters": {}},
                    {"step_number": 2, "name": "配置映射参数", "type": "configure_mapping", "parameters": {}}
                ],
                "parameters": {
                    "route_type": {"type": "string", "default": "urban"},
                    "update_rate_hz": {"type": "number", "default": 10},
                    "enable_handover": {"type": "boolean", "default": True}
                },
                "default_values": {"route_type": "urban", "update_rate_hz": 10},
                "is_public": True,
                "usage_count": 0,
                "created_by": "system"
            },
            {
                "name": "Execute Route Test",
                "description": "按预定义路径执行测试，实时采集性能数据",
                "category": "Road Test - Step 5",
                "steps": [
                    {"step_number": 1, "name": "开始路径回放", "type": "start_route", "parameters": {}},
                    {"step_number": 2, "name": "采集KPI数据", "type": "collect_kpis", "parameters": {}},
                    {"step_number": 3, "name": "实时监控", "type": "monitor_execution", "parameters": {}}
                ],
                "parameters": {
                    "monitor_kpis": {"type": "boolean", "default": True},
                    "log_interval_s": {"type": "number", "default": 1},
                    "auto_screenshot": {"type": "boolean", "default": True}
                },
                "default_values": {"monitor_kpis": True, "log_interval_s": 1},
                "is_public": True,
                "usage_count": 0,
                "created_by": "system"
            },
            {
                "name": "Validate KPIs and Performance Metrics",
                "description": "验证测试结果是否满足KPI阈值要求",
                "category": "Road Test - Step 6",
                "steps": [
                    {"step_number": 1, "name": "阈值检查", "type": "check_thresholds", "parameters": {}},
                    {"step_number": 2, "name": "统计分析", "type": "analyze_statistics", "parameters": {}},
                    {"step_number": 3, "name": "生成趋势图", "type": "generate_plots", "parameters": {}}
                ],
                "parameters": {
                    "min_throughput_mbps": {"type": "number", "default": 50},
                    "max_latency_ms": {"type": "number", "default": 50},
                    "min_rsrp_dbm": {"type": "number", "default": -110},
                    "generate_plots": {"type": "boolean", "default": True}
                },
                "default_values": {"min_throughput_mbps": 50, "max_latency_ms": 50, "generate_plots": True},
                "is_public": True,
                "usage_count": 0,
                "created_by": "system"
            },
            {
                "name": "Generate Test Report",
                "description": "生成测试报告，包含结果摘要、图表和建议",
                "category": "Road Test - Step 7",
                "steps": [
                    {"step_number": 1, "name": "生成报告", "type": "generate_report", "parameters": {}},
                    {"step_number": 2, "name": "添加附件", "type": "add_attachments", "parameters": {}}
                ],
                "parameters": {
                    "report_format": {"type": "string", "default": "PDF"},
                    "include_raw_data": {"type": "boolean", "default": False},
                    "include_screenshots": {"type": "boolean", "default": True},
                    "include_recommendations": {"type": "boolean", "default": True}
                },
                "default_values": {"report_format": "PDF", "include_screenshots": True},
                "is_public": True,
                "usage_count": 0,
                "created_by": "system"
            }
        ]

        for seq_data in sequences:
            sequence = TestSequence(**seq_data)
            db.add(sequence)

        db.commit()
        print(f"Successfully added {len(sequences)} test sequences")

        # Print summary
        for seq in sequences:
            print(f"  - {seq['name']} ({seq['category']}) - {len(seq['steps'])} steps")

    except Exception as e:
        print(f"Error initializing sequences: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_sequences()
