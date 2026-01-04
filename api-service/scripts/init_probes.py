"""Initialize 32 dual-polarized probes"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from app.db.database import SessionLocal, init_db
from app.models.probe import Probe

def init_probes():
    """
    Initialize MPAC 32-probe array
    
    Layout matches the 'Three Ring' configuration in Frontend:
    - Ring 1 (Upper): 8 positions * 1 pol/each? No, typically probes are dual-polarized physically,
      but let's see how we count them.
      
      If we want 32 *Probes* (entries in DB), and they are dual-polarized (V/H), 
      that means 16 *Physical Positions*.
      
      However, the previous script loop did:
      `for pol in ["V", "H"]: ... probes.append(...)`
      
      So:
      - Previous Ring 1: 4 pos * 2 pol = 8 probes
      - Previous Ring 2: 8 pos * 2 pol = 16 probes
      - Total = 24 probes.
      
      To get 32 probes (16 positions):
      We need 8 + 16 + 8 = 32 probes?
      No, 8 probes (4 pos) + 16 probes (8 pos) + 8 probes (4 pos) = 32.
      
      So the layout should be:
      - Ring 1 (Upper, El=45): 4 positions (0, 90, 180, 270)
      - Ring 2 (Middle, El=0): 8 positions (0, 45, 90...)
      - Ring 3 (Lower, El=-45): 4 positions (0, 90, 180, 270)
      
      Total Positions: 4 + 8 + 4 = 16.
      Total Probes (V+H): 16 * 2 = 32.
    """
    print("Initializing database...")
    init_db()

    db = SessionLocal()

    print("Clearing existing probes...")
    db.query(Probe).delete()

    probes = []
    probe_number = 1
    
    # Configuration
    # We use a 3-ring layout to achieve 32 probes (16 positions)
    # Ring 1 (Upper): 4 positions
    # Ring 2 (Middle): 8 positions
    # Ring 3 (Lower): 4 positions
    
    rings_config = [
        {"ring_id": 1, "elevation": 45,  "count": 4, "radius": 1.5},
        {"ring_id": 2, "elevation": 0,   "count": 8, "radius": 2.0},
        {"ring_id": 3, "elevation": -45, "count": 4, "radius": 1.5}
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
                    calibration_status="unknown"
                ))
                probe_number += 1

    print(f"Generated {len(probes)} probes objects in memory.")
    
    # Safety check
    if len(probes) != 32:
        print(f"⚠️ Warning: Expected 32 probes, generated {len(probes)}")
    
    db.add_all(probes)
    db.commit()

    actual_count = db.query(Probe).count()
    print(f"✅ Successfully initialized {actual_count} probes")

    db.close()

if __name__ == "__main__":
    init_probes()