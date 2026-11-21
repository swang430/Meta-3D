"""以真实四发两收 MPDB 回归工作台的两套探头 ASC 输出。"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.mpdb_workbench import generate_ota


@unittest.skipUnless(os.getenv("IMT_MPDB_TEST_ARCHIVE"), "需要指定四发两收原始 MPDB 压缩包")
class ProbeProjectTest(unittest.TestCase):
    def test_generates_and_reads_back_source_and_dynamic_project(self):
        archive = Path(os.environ["IMT_MPDB_TEST_ARCHIVE"])
        with zipfile.ZipFile(archive) as raw:
            source_digest = hashlib.sha256(raw.read("R0B0S0D.mpdb")).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "project"
            generate_ota(archive, output, speed=5, rate=171.18765176762867)
            for name, frames in (("baseline", 38), ("dynamic", 6195)):
                folder = output / name
                manifest = json.loads((folder / "manifest.json").read_text())
                self.assertEqual(manifest["source_sha256"], source_digest)
                self.assertEqual(manifest["header"]["cir_count"], frames)
                self.assertEqual(len(list(folder.glob("*.asc"))), 128)
                self.assertEqual(len({link["file"] for link in manifest["links"]}), 128)
                for link in manifest["links"]:
                    data = (folder / link["file"]).read_bytes()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), link["sha256"])
                    self.assertEqual(len(data.splitlines()) - 12, frames)
