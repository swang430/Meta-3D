"""Initialize 32 dual-polarized probes with default chamber configuration"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal, init_db
from app.models.probe import Probe
from app.models.chamber import ChamberConfiguration, create_chamber_from_preset

def init_probes():
    """
    Initialize MPAC 32-probe array with default chamber configuration

    Layout: Three Ring configuration
    - Ring 1 (Upper, El=45): 4 positions (0, 90, 180, 270)
    - Ring 2 (Middle, El=0): 8 positions (0, 45, 90...)
    - Ring 3 (Lower, El=-45): 4 positions (0, 90, 180, 270)

    Total Positions: 4 + 8 + 4 = 16.
    Total Probes (V+H): 16 * 2 = 32.
    """
    print("Initializing database...")
    init_db()

    db = SessionLocal()

    # === Step 1: 创建或获取默认暗室配置 ===
    print("Checking for existing chamber configuration...")
    default_chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.is_active == True
    ).first()

    if not default_chamber:
        print("Creating default chamber configuration (Type C - 大型单向暗室)...")
        default_chamber = create_chamber_from_preset(
            preset_type="type_c",
            name="默认车载 MIMO OTA 暗室"
        )
        default_chamber.is_active = True
        db.add(default_chamber)
        db.commit()
        db.refresh(default_chamber)
        print(f"✅ Created chamber: {default_chamber.name} (ID: {default_chamber.id})")
    else:
        print(f"✅ Using existing chamber: {default_chamber.name} (ID: {default_chamber.id})")

    chamber_id = default_chamber.id

    # === Step 2: 初始化探头 ===
    print("Clearing existing probes...")
    db.query(Probe).delete()

    probes = []
    probe_number = 1

    # Configuration: 3-ring layout for 32 probes (16 positions)
    rings_config = [
        {"ring_id": 1, "elevation": 45,  "count": 4, "radius": default_chamber.chamber_radius_m},
        {"ring_id": 2, "elevation": 0,   "count": 8, "radius": default_chamber.chamber_radius_m},
        {"ring_id": 3, "elevation": -45, "count": 4, "radius": default_chamber.chamber_radius_m}
    ]

    for ring in rings_config:
        print(f"Creating Ring {ring['ring_id']} ({ring['count']} positions)...")
        step = 360 / ring['count']

        for i in range(ring['count']):
            azimuth = i * step

            # Create Dual-Polarized Probes for this position
            for pol in ["V", "H"]:
                probes.append(Probe(
                    probe_number=probe_number,
                    name=f"Probe {probe_number}-{pol}",
                    ring=ring['ring_id'],
                    polarization=pol,
                    position={
                        "azimuth": azimuth,
                        "elevation": ring['elevation'],
                        "radius": ring['radius']
                    },
                    is_active=True,
                    is_connected=False,
                    status="idle",
                    calibration_status="unknown",
                    chamber_config_id=chamber_id
                ))
                probe_number += 1

    print(f"Generated {len(probes)} probes objects in memory.")

    # Safety check
    if len(probes) != 32:
        print(f"⚠️ Warning: Expected 32 probes, generated {len(probes)}")

    db.add_all(probes)
    db.commit()

    actual_count = db.query(Probe).count()
    linked_count = db.query(Probe).filter(Probe.chamber_config_id == chamber_id).count()
    print(f"✅ Successfully initialized {actual_count} probes")
    print(f"✅ {linked_count} probes linked to chamber '{default_chamber.name}'")

    db.close()

if __name__ == "__main__":
    init_probes()