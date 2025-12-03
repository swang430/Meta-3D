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
