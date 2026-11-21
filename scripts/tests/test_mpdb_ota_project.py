"""以真实四发两收 MPDB 回归工作台的两套探头 ASC 输出。"""

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.mpdb_workbench import generate_ota
from scripts.mpdb_playback import inspect_timing, resolve_playback


@unittest.skipUnless(
    os.getenv("IMT_MPDB_TEST_ARCHIVE"), "需要指定四发两收原始 MPDB 压缩包"
)
class ProbeProjectTest(unittest.TestCase):
    def test_physical_clock_can_generate_without_receiver_positions(self):
        archive = Path(os.environ["IMT_MPDB_TEST_ARCHIVE"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            variant = root / "no-positions.zip"
            repacked = io.BytesIO()
            with zipfile.ZipFile(archive) as original, zipfile.ZipFile(
                io.BytesIO(original.read("R0B0S0D.mpdb"))
            ) as db, zipfile.ZipFile(repacked, "w") as changed:
                desc = json.loads(db.read("mpdb.json"))
                removed = {s["entry"] for s in desc["records"]["LINK"].pop("RX_ANT_POSITION")["shards"]}
                desc["meta"]["rtSampleIntervalSeconds"] = 0.02
                for name in db.namelist():
                    if name not in removed and name != "mpdb.json":
                        changed.writestr(name, db.read(name))
                changed.writestr("mpdb.json", json.dumps(desc))
            with zipfile.ZipFile(variant,"w") as outer:
                outer.writestr("R0B0S0D.mpdb", repacked.getvalue())
            with zipfile.ZipFile(repacked) as db:
                timing = inspect_timing(db, json.loads(db.read("mpdb.json")))
            playback = resolve_playback(timing,None,None,"standard")
            generate_ota(variant, root/"project", playback)
            report=json.loads((root/"project/dynamic/manifest.json").read_text())
            self.assertEqual(report["segment_average_speeds_m_s"],[None]*37)
            self.assertEqual(report["header"]["cir_count"],int(0.74 * playback["rate_hz"])+1)
            self.assertEqual(len(report["links"]),128)

    def test_same_constant_speed_preserves_upstream_complex_coefficients(self):
        from mimo_ota_simulator.imt_dynamic_probe import generate as upstream

        archive = Path(os.environ["IMT_MPDB_TEST_ARCHIVE"])
        with zipfile.ZipFile(archive) as outer:
            with zipfile.ZipFile(io.BytesIO(outer.read("R0B0S0D.mpdb"))) as db:
                timing = inspect_timing(db, json.loads(db.read("mpdb.json")))
        playback = resolve_playback(timing, 100, None, "standard")
        geometry = (
            Path(os.environ["CHANNEL_ENGINE_PATH"])
            / "examples/imt_16probe_geometry.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_ota(archive, root / "new", playback)
            upstream(
                archive, geometry, root / "new/baseline", root / "reference", 100, playback["rate_hz"]
            )
            read = lambda path: json.loads(path.read_text())["links"]
            self.assertEqual(
                read(root / "new/dynamic/manifest.json"),
                read(root / "reference/manifest.json"),
            )

    def test_generates_and_reads_back_source_and_dynamic_project(self):
        archive = Path(os.environ["IMT_MPDB_TEST_ARCHIVE"])
        with zipfile.ZipFile(archive) as raw:
            inner = raw.read("R0B0S0D.mpdb")
            source_digest = hashlib.sha256(inner).hexdigest()
            with zipfile.ZipFile(io.BytesIO(inner)) as db:
                timing = inspect_timing(db, json.loads(db.read("mpdb.json")))
        segments = [0.04, 0.06] * 18 + [0.04]
        playback = resolve_playback(timing, None, segments, "standard")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "project"
            generate_ota(archive, output, playback)
            for name, frames in (("baseline", 38), ("dynamic", int(1.84 * playback["rate_hz"])+1)):
                folder = output / name
                manifest = json.loads((folder / "manifest.json").read_text())
                self.assertEqual(manifest["source_sha256"], source_digest)
                if name == "baseline":
                    self.assertEqual(manifest["rate_source"], "source_frame_viewer_placeholder")
                if name == "dynamic":
                    self.assertEqual(manifest["source_times_s"][:3], [0, 0.04, 0.1])
                    self.assertEqual(
                        manifest["time_source"], "operator_segment_durations"
                    )
                self.assertEqual(manifest["header"]["cir_count"], frames)
                self.assertEqual(len(list(folder.glob("*.asc"))), 128)
                self.assertEqual(len({link["file"] for link in manifest["links"]}), 128)
                for link in manifest["links"]:
                    data = (folder / link["file"]).read_bytes()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), link["sha256"])
                    self.assertEqual(len(data.splitlines()) - 12, frames)
