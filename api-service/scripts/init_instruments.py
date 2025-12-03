"""Initialize instrument categories and models"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal, init_db
from app.models.instrument import InstrumentCategory, InstrumentModel

def init_instruments():
    """Initialize instrument catalog"""
    print("Initializing database...")
    init_db()

    db = SessionLocal()

    print("Clearing existing instruments...")
    db.query(InstrumentModel).delete()
    db.query(InstrumentCategory).delete()

    # 1. Channel Emulator
    print("Creating Channel Emulator category...")
    channel_cat = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
        category_name_en="Channel Emulator",
        description="用于模拟无线信道环境的MIMO信道仿真器",
        display_order=1
    )
    db.add(channel_cat)
    db.flush()

    db.add_all([
        InstrumentModel(
            category_id=channel_cat.id,
            vendor="Keysight",
            model="PROPSIM F64",
            full_name="Keysight PROPSIM F64 Channel Emulator",
            capabilities={
                "channels": 64,
                "bandwidth_mhz": 200,
                "frequency_range_ghz": [0.4, 6.0],
                "interfaces": ["LAN", "USB"]
            },
            display_order=1
        ),
        InstrumentModel(
            category_id=channel_cat.id,
            vendor="Spirent",
            model="VR5",
            full_name="Spirent VR5 Channel Emulator",
            capabilities={
                "channels": 32,
                "bandwidth_mhz": 100,
                "frequency_range_ghz": [0.7, 6.0],
                "interfaces": ["LAN"]
            },
            display_order=2
        )
    ])

    # 2. Base Station Emulator
    print("Creating Base Station category...")
    bs_cat = InstrumentCategory(
        category_key="baseStation",
        category_name="基站仿真器",
        category_name_en="Base Station Emulator",
        description="用于模拟5G/LTE基站的测试仪表",
        display_order=2
    )
    db.add(bs_cat)
    db.flush()

    db.add(InstrumentModel(
        category_id=bs_cat.id,
        vendor="Anritsu",
        model="MT8000A",
        full_name="Anritsu MT8000A Radio Communication Tester",
        capabilities={
            "bands": ["n77", "n78", "n79"],
            "max_bandwidth_mhz": 100,
            "technologies": ["5G NR", "LTE"]
        },
        display_order=1
    ))

    # 3. Turntable
    print("Creating Turntable category...")
    turntable_cat = InstrumentCategory(
        category_key="turntable",
        category_name="转台",
        category_name_en="Turntable/Positioner",
        description="用于旋转被测设备的转台系统",
        display_order=3
    )
    db.add(turntable_cat)
    db.flush()

    db.add(InstrumentModel(
        category_id=turntable_cat.id,
        vendor="CATR",
        model="AZ-EL Positioner",
        full_name="CATR AZ-EL Dual-Axis Positioner",
        capabilities={
            "axes": 2,
            "azimuth_range_deg": [0, 360],
            "elevation_range_deg": [-90, 90],
            "accuracy_deg": 0.1
        },
        display_order=1
    ))

    # 4. VNA
    print("Creating VNA category...")
    vna_cat = InstrumentCategory(
        category_key="vna",
        category_name="矢量网络分析仪",
        category_name_en="Vector Network Analyzer",
        description="用于S参数测量和射频分析",
        display_order=4
    )
    db.add(vna_cat)
    db.flush()

    db.add(InstrumentModel(
        category_id=vna_cat.id,
        vendor="Keysight",
        model="N5227B",
        full_name="Keysight N5227B PNA Microwave Network Analyzer",
        capabilities={
            "frequency_range_ghz": [0.01, 67],
            "ports": 4,
            "dynamic_range_db": 120
        },
        display_order=1
    ))

    db.commit()

    cat_count = db.query(InstrumentCategory).count()
    model_count = db.query(InstrumentModel).count()
    print(f"✅ Successfully initialized {cat_count} categories and {model_count} models")

    db.close()

if __name__ == "__main__":
    init_instruments()
