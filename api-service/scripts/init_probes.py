"""Initialize 32 dual-polarized probes"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal, init_db
from app.models.probe import Probe

def init_probes():
    """Initialize MPAC 32-probe array"""
    print("Initializing database...")
    init_db()

    db = SessionLocal()

    print("Clearing existing probes...")
    db.query(Probe).delete()

    probes = []
    probe_number = 1

    # Ring 1: 4 positions (0°, 90°, 180°, 270°)
    print("Creating Ring 1 probes...")
    for azimuth in [0, 90, 180, 270]:
        for pol in ["V", "H"]:
            probes.append(Probe(
                probe_number=probe_number,
                name=f"Probe {probe_number}-{pol}",
                ring=1,
                polarization=pol,
                position={"azimuth": azimuth, "elevation": 0, "radius": 1.5},
                is_active=True,
                is_connected=False,
                status="idle",
                calibration_status="unknown"
            ))
            probe_number += 1

    # Ring 2: 8 positions (45° increments)
    print("Creating Ring 2 probes...")
    for azimuth in range(0, 360, 45):
        for pol in ["V", "H"]:
            if probe_number > 32:
                break
            probes.append(Probe(
                probe_number=probe_number,
                name=f"Probe {probe_number}-{pol}",
                ring=2,
                polarization=pol,
                position={"azimuth": azimuth, "elevation": 0, "radius": 2.0},
                is_active=True,
                is_connected=False,
                status="idle",
                calibration_status="unknown"
            ))
            probe_number += 1

    db.add_all(probes[:32])  # Ensure exactly 32 probes
    db.commit()

    actual_count = db.query(Probe).count()
    print(f"✅ Successfully initialized {actual_count} probes")

    db.close()

if __name__ == "__main__":
    init_probes()
