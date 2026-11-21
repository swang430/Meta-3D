import tempfile
import unittest
from pathlib import Path
from scripts.imt_conducted import build

HEADER = """***** Header *****
2 CIRs
1 Taps/CIR
2565000000 Carrier_Frequency
Route_Open
CIRUpdateRate_Unlocked
CarrierFrequency_Unlocked
5 Delay_Resolution
2 Sample_Density
171 CIR_Update_Rate
***** Tap data *****
Delay Re Im
"""

class ConductedTest(unittest.TestCase):
    def test_build_and_reject_bad_last_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for tx in range(4):
                for rx in range(2):
                    path = root / f"R0B0S0D_TX{tx}_RX{rx}_H.asc"
                    path.write_text(HEADER + "20 1 0\n20 0 1\n")
            result = build(root, root / "ok")
            self.assertEqual(len(result["links"]), 8)
            self.assertEqual((root / "ok" / path.name).read_bytes(), path.read_bytes())
            for bad in (HEADER + "20 nan 0\n20 0 1\n", HEADER + "20 1 0\n",
                        HEADER.replace("5 Delay", "7 Delay") + "20 1 0\n20 0 1\n",
                        HEADER.replace("171 CIR", "172 CIR") + "20 1 0\n20 0 1\n"):
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    build(root, root / "failed")
                self.assertFalse((root / "failed").exists())
